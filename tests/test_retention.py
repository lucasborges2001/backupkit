from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from core.artifact import sha256_file
from core.backup import build_backup_basename
from core.retention import RetentionManager, RetentionPolicy
from core.result import ArtifactMetadata


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.tempdir.name)
        self.project = 'test-project'
        self.resource = 'test-resource'

    def tearDown(self):
        self.tempdir.cleanup()

    def create_fake_run(self, timestamp: str, status: str = 'OK'):
        artifact_path = self.output_dir / build_backup_basename(
            self.project,
            self.resource,
            timestamp,
        )
        artifact_path.write_bytes(f'fake content {timestamp}'.encode('utf-8'))

        meta = ArtifactMetadata.from_values(
            path=artifact_path.resolve(),
            size_bytes=artifact_path.stat().st_size,
            sha256=sha256_file(artifact_path),
            timestamp=timestamp,
            engine='mysql',
            resource=self.resource,
            project=self.project,
            duration_sec=1.0,
            status=status,
        )
        meta_path = artifact_path.with_suffix(artifact_path.suffix + '.metadata.json')
        meta.metadata_path = str(meta_path.resolve())
        meta_path.write_text(json.dumps(meta.as_dict()), encoding='utf-8')

        prefix = artifact_path.name[:-len(f'{timestamp}.sql.gz')]
        report_path = self.output_dir / f'{prefix}{timestamp}__backup-report.json'
        report_path.write_text(json.dumps({
            'report_version': 2,
            'final_status': status,
        }), encoding='utf-8')
        return artifact_path, meta_path, report_path

    def test_discovery_finds_and_verifies_all_files_in_run(self):
        ts = '20260406T120000Z'
        artifact, metadata, report = self.create_fake_run(ts)
        manager = RetentionManager(RetentionPolicy(enabled=True))
        runs = manager.discover_runs(self.output_dir, self.project, self.resource)

        self.assertEqual(len(runs), 1)
        self.assertTrue(runs[0].is_valid_backup)
        self.assertEqual(len(runs[0].files), 3)
        self.assertIn(artifact, runs[0].files)
        self.assertIn(metadata, runs[0].files)
        self.assertIn(report, runs[0].files)

    def test_keep_success_limit(self):
        self.create_fake_run('20260401T120000Z')
        self.create_fake_run('20260402T120000Z')
        self.create_fake_run('20260403T120000Z')
        policy = RetentionPolicy(enabled=True, keep_success=2, protect_last_known_valid=False, require_verified_newer_backup=False)
        manager = RetentionManager(policy)
        decisions = manager.decide(manager.discover_runs(self.output_dir, self.project, self.resource))

        self.assertEqual(decisions[0].action, 'KEEP')
        self.assertEqual(decisions[1].action, 'KEEP')
        self.assertEqual(decisions[2].action, 'DELETE')

    def test_protect_last_known_valid(self):
        self.create_fake_run('20260401T120000Z', 'OK')
        self.create_fake_run('20260402T120000Z', 'ERROR')
        self.create_fake_run('20260403T120000Z', 'ERROR')
        policy = RetentionPolicy(enabled=True, keep_success=0, keep_non_success=1, protect_last_known_valid=True, require_verified_newer_backup=False)
        manager = RetentionManager(policy)
        actions = {
            decision.run.timestamp: decision.action
            for decision in manager.decide(manager.discover_runs(self.output_dir, self.project, self.resource))
        }

        self.assertEqual(actions['20260403T120000Z'], 'KEEP')
        self.assertEqual(actions['20260402T120000Z'], 'KEEP')
        self.assertEqual(actions['20260401T120000Z'], 'PROTECT')

    def test_dry_run_defaults_to_true_and_does_not_delete(self):
        self.create_fake_run('20260401T120000Z')
        self.create_fake_run('20260402T120000Z')
        policy = RetentionPolicy(enabled=True, keep_success=1, protect_last_known_valid=False)
        self.assertTrue(policy.dry_run)
        manager = RetentionManager(policy)
        execution = manager.execute(manager.decide(manager.discover_runs(self.output_dir, self.project, self.resource)))

        self.assertEqual(len(execution['deleted']), 0)
        self.assertEqual(len(execution['skipped_deletions']), 1)

    def test_execution_deletes_verified_old_files(self):
        old_artifact, old_meta, _ = self.create_fake_run('20260401T120000Z')
        self.create_fake_run('20260402T120000Z')
        policy = RetentionPolicy(enabled=True, keep_success=1, dry_run=False, protect_last_known_valid=False)
        manager = RetentionManager(policy)
        execution = manager.execute(manager.decide(manager.discover_runs(self.output_dir, self.project, self.resource)))

        self.assertEqual(len(execution['deleted']), 1)
        self.assertFalse(old_artifact.exists())
        self.assertFalse(old_meta.exists())

    def test_insufficient_evidence_does_not_delete(self):
        orphan = self.output_dir / f'{self.project}__{self.resource}__20260401T120000Z.sql.gz'
        orphan.write_text('orphan', encoding='utf-8')
        self.create_fake_run('20260402T120000Z')
        policy = RetentionPolicy(enabled=True, keep_success=1, keep_non_success=0, protect_last_known_valid=False)
        manager = RetentionManager(policy)
        by_timestamp = {
            decision.run.timestamp: decision
            for decision in manager.decide(manager.discover_runs(self.output_dir, self.project, self.resource))
        }

        self.assertEqual(by_timestamp['20260401T120000Z'].action, 'KEEP')
        self.assertIn('metadata missing/corrupt', by_timestamp['20260401T120000Z'].reason)

    def test_tampered_artifact_is_never_deleted(self):
        old_artifact, _, _ = self.create_fake_run('20260401T120000Z')
        self.create_fake_run('20260402T120000Z')
        old_artifact.write_text('tampered', encoding='utf-8')
        policy = RetentionPolicy(enabled=True, keep_success=1, keep_non_success=0, dry_run=False, protect_last_known_valid=False)
        manager = RetentionManager(policy)
        old = {
            decision.run.timestamp: decision
            for decision in manager.decide(manager.discover_runs(self.output_dir, self.project, self.resource))
        }['20260401T120000Z']

        self.assertEqual(old.action, 'KEEP')
        self.assertIn('verification failed', old.reason)
        self.assertTrue(old_artifact.exists())

    def test_verified_newer_backup_is_required_before_delete(self):
        self.create_fake_run('20260401T120000Z')
        policy = RetentionPolicy(enabled=True, keep_success=0, protect_last_known_valid=False, require_verified_newer_backup=True, dry_run=False)
        manager = RetentionManager(policy)
        decision = manager.decide(manager.discover_runs(self.output_dir, self.project, self.resource))[0]

        self.assertEqual(decision.action, 'KEEP')
        self.assertIn('no newer verified backup', decision.reason)

    def test_minimum_age_blocks_deletion(self):
        self.create_fake_run('20260401T120000Z')
        self.create_fake_run('20260402T120000Z')
        policy = RetentionPolicy(enabled=True, keep_success=1, minimum_age_days=100000, protect_last_known_valid=False, dry_run=False)
        manager = RetentionManager(policy)
        old = {
            decision.run.timestamp: decision
            for decision in manager.decide(manager.discover_runs(self.output_dir, self.project, self.resource))
        }['20260401T120000Z']

        self.assertEqual(old.action, 'KEEP')
        self.assertIn('minimum_age_days', old.reason)

    @unittest.skipIf(os.name == 'nt', 'symlink semantics differ on Windows CI')
    def test_symlink_artifact_fails_closed(self):
        old_artifact, _, _ = self.create_fake_run('20260401T120000Z')
        new_artifact, _, _ = self.create_fake_run('20260402T120000Z')
        old_artifact.unlink()
        old_artifact.symlink_to(new_artifact)
        policy = RetentionPolicy(enabled=True, keep_success=1, keep_non_success=0, protect_last_known_valid=False, dry_run=False)
        manager = RetentionManager(policy)
        old = {
            decision.run.timestamp: decision
            for decision in manager.decide(manager.discover_runs(self.output_dir, self.project, self.resource))
        }['20260401T120000Z']

        self.assertEqual(old.action, 'KEEP')
        self.assertTrue(old_artifact.is_symlink())


if __name__ == '__main__':
    unittest.main()
