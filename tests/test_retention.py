from __future__ import annotations

import json
import unittest
from pathlib import Path
import tempfile
import shutil

from core.retention import RetentionPolicy, RetentionManager, LogicalRun, HousekeepingDecision
from core.result import ArtifactMetadata

class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.tempdir.name)
        self.project = "test-project"
        self.resource = "test-resource"

    def tearDown(self):
        self.tempdir.cleanup()

    def create_fake_run(self, timestamp: str, status: str = 'OK'):
        # Create artifact
        artifact_name = f"{self.project}__{self.resource}__{timestamp}.sql.gz"
        artifact_path = self.output_dir / artifact_name
        artifact_path.write_text("fake content")

        # Create metadata
        meta = ArtifactMetadata.from_values(
            path=artifact_path,
            size_bytes=100,
            sha256="fake-sha",
            timestamp=timestamp,
            engine="mysql",
            resource=self.resource,
            project=self.project,
            duration_sec=1.0,
            status=status
        )
        meta_path = artifact_path.with_suffix(artifact_path.suffix + '.metadata.json')
        meta_path.write_text(json.dumps(meta.as_dict()))
        
        # Create report
        report_name = f"{self.project}__{self.resource}__{timestamp}__backup-report.json"
        report_path = self.output_dir / report_name
        report_path.write_text(json.dumps({"status": status}))
        
        return artifact_path, meta_path, report_path

    def test_discovery_finds_all_files_in_run(self):
        ts = "20260406T120000Z"
        a, m, r = self.create_fake_run(ts)
        
        policy = RetentionPolicy(enabled=True)
        manager = RetentionManager(policy)
        runs = manager.discover_runs(self.output_dir, self.project, self.resource)
        
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].timestamp, ts)
        self.assertEqual(len(runs[0].files), 3)
        self.assertIn(a, runs[0].files)
        self.assertIn(m, runs[0].files)
        self.assertIn(r, runs[0].files)

    def test_keep_success_limit(self):
        # Create 3 success runs
        self.create_fake_run("20260401T120000Z", "OK")
        self.create_fake_run("20260402T120000Z", "OK")
        self.create_fake_run("20260403T120000Z", "OK")
        
        # Policy: keep only 2 success
        policy = RetentionPolicy(enabled=True, keep_success=2, protect_last_known_valid=False)
        manager = RetentionManager(policy)
        runs = manager.discover_runs(self.output_dir, self.project, self.resource)
        decisions = manager.decide(runs)
        
        # Runs are newest first: 03, 02, 01
        self.assertEqual(decisions[0].action, 'KEEP') # 03
        self.assertEqual(decisions[1].action, 'KEEP') # 02
        self.assertEqual(decisions[2].action, 'DELETE') # 01
        self.assertEqual(decisions[2].run.timestamp, "20260401T120000Z")

    def test_protect_last_known_valid(self):
        # Create 1 success (old) and 2 failures (newer)
        self.create_fake_run("20260401T120000Z", "OK") # Oldest but valid
        self.create_fake_run("20260402T120000Z", "ERROR")
        self.create_fake_run("20260403T120000Z", "ERROR")
        
        # Policy: keep 0 success (but protect last valid), keep 1 non-success
        policy = RetentionPolicy(enabled=True, keep_success=0, keep_non_success=1, protect_last_known_valid=True)
        manager = RetentionManager(policy)
        runs = manager.discover_runs(self.output_dir, self.project, self.resource)
        decisions = manager.decide(runs)
        
        # Sorted: 03 (ERROR), 02 (ERROR), 01 (OK)
        # 03 -> KEEP (within keep_non_success=1)
        # 02 -> DELETE (limit exceeded)
        # 01 -> PROTECT (last known valid)
        
        actions = {d.run.timestamp: d.action for d in decisions}
        self.assertEqual(actions["20260403T120000Z"], 'KEEP')
        self.assertEqual(actions["20260402T120000Z"], 'DELETE')
        self.assertEqual(actions["20260401T120000Z"], 'PROTECT')

    def test_dry_run_does_not_delete(self):
        self.create_fake_run("20260401T120000Z", "OK")
        self.create_fake_run("20260402T120000Z", "OK")
        
        policy = RetentionPolicy(enabled=True, keep_success=1, dry_run=True, protect_last_known_valid=False)
        manager = RetentionManager(policy)
        runs = manager.discover_runs(self.output_dir, self.project, self.resource)
        decisions = manager.decide(runs)
        execution = manager.execute(decisions)
        
        self.assertEqual(len(execution['deleted']), 0)
        self.assertEqual(len(execution['skipped_deletions']), 1)
        self.assertTrue((self.output_dir / f"{self.project}__{self.resource}__20260401T120000Z.sql.gz").exists())

    def test_execution_deletes_files(self):
        ts_to_delete = "20260401T120000Z"
        self.create_fake_run(ts_to_delete, "OK")
        self.create_fake_run("20260402T120000Z", "OK")
        
        policy = RetentionPolicy(enabled=True, keep_success=1, dry_run=False, protect_last_known_valid=False)
        manager = RetentionManager(policy)
        runs = manager.discover_runs(self.output_dir, self.project, self.resource)
        decisions = manager.decide(runs)
        execution = manager.execute(decisions)
        
        self.assertEqual(len(execution['deleted']), 1)
        self.assertFalse((self.output_dir / f"{self.project}__{self.resource}__{ts_to_delete}.sql.gz").exists())
        self.assertFalse((self.output_dir / f"{self.project}__{self.resource}__{ts_to_delete}.sql.gz.metadata.json").exists())

    def test_insufficient_evidence_does_not_delete(self):
        # Create a file that matches prefix but has NO metadata
        p = self.output_dir / f"{self.project}__{self.resource}__20260401T120000Z.orphaned.json"
        p.write_text("{}")
        
        self.create_fake_run("20260402T120000Z", "OK")
        
        policy = RetentionPolicy(enabled=True, keep_success=1, keep_non_success=0, protect_last_known_valid=False)
        manager = RetentionManager(policy)
        runs = manager.discover_runs(self.output_dir, self.project, self.resource)
        decisions = manager.decide(runs)
        
        # Newest is 02 (OK) -> KEEP
        # 01 (Unknown, no metadata) -> should be KEPT because of safety skip
        self.assertEqual(decisions[0].action, 'KEEP')
        self.assertEqual(decisions[1].action, 'KEEP')
        self.assertIn("metadata missing/corrupt", decisions[1].reason)

if __name__ == '__main__':
    unittest.main()
