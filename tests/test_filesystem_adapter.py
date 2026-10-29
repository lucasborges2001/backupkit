from __future__ import annotations

import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from core.cli import run_backup, run_verify_artifact, run_restore_test
from core.backup import build_artifact_metadata, write_artifact_metadata
from core.precheck import validate_required_config
from core.result import RunReport


class FilesystemAdapterContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="backupkit-fs-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "ingest"
        self.source.mkdir()
        (self.source / "day").mkdir()
        (self.source / "day/event.json").write_text('{"seq":1}', encoding="utf-8")
        self.output = self.root / "private-output"
        self.locks = self.root / "private-locks"
        self.policy = {
            "project": {"name": "centrologistico"},
            "resource": {"name": "ingest-state", "type": "filesystem",
                         "source_dir": str(self.source)},
            "artifact": {"output_dir": str(self.output)},
            "prechecks": {"require_free_space_mb": 0, "require_tools": []},
            "runtime": {"lock_dir": str(self.locks)},
            "retention": {"enabled": False},
        }
        self.config = {"env": {}, "policy": self.policy}
        self.args = SimpleNamespace(env="unused", policy="unused")

    def run_command(self, command):
        with patch("core.cli.load_config", return_value=self.config):
            return command(self.args)

    def test_backup_verify_restore_and_cleanup(self):
        self.assertEqual(self.run_command(run_backup), 0)
        artifacts = list(self.output.glob("*.tar.gz"))
        self.assertEqual(len(artifacts), 1)
        artifact = artifacts[0]
        self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
        self.policy["artifact"]["path"] = str(artifact)
        self.assertEqual(self.run_command(run_verify_artifact), 0)
        self.assertEqual(self.run_command(run_restore_test), 0)
        restore_report = json.loads((self.output / "restore-test-report.json").read_text())
        self.assertEqual(restore_report["final_status"], "OK")
        restored = restore_report["phases"][0]["evidence"]["restore_test"]
        self.assertEqual(restored["mode"], "temporary_filesystem")
        self.assertTrue(restored["cleanup_succeeded"])
        self.assertFalse(list(self.output.glob(".backupkit-restore-*")))
        self.assertEqual((self.source / "day/event.json").read_text(), '{"seq":1}')
        with tarfile.open(artifact, "r:gz") as tf:
            self.assertEqual([m.name for m in tf.getmembers()], ["payload/day/event.json"])

    def test_symlink_rejected_before_artifact(self):
        (self.source / "link").symlink_to(self.source / "day", target_is_directory=True)
        self.assertEqual(self.run_command(run_backup), 2)
        self.assertFalse(list(self.output.glob("*.tar.gz")))

    def test_output_below_source_is_rejected(self):
        self.policy["artifact"]["output_dir"] = str(self.source / "out")
        self.assertEqual(self.run_command(run_backup), 2)

    def test_empty_source_is_rejected(self):
        (self.source / "day/event.json").unlink()
        self.assertEqual(self.run_command(run_backup), 2)

    def test_retention_enabled_rejected(self):
        self.policy["retention"]["enabled"] = True
        report = RunReport(project="centrologistico", resource="ingest-state",
                           resource_type="filesystem", command="backup")
        validate_required_config(self.config, report, "backup")
        self.assertTrue(report.has_errors())
        self.assertIn("retention.enabled", report.checks[0].message)

    def test_malicious_tar_is_rejected_with_matching_sidecar(self):
        self.output.mkdir(mode=0o700)
        payload = self.output / "evil.tar.gz"
        with tarfile.open(payload, "w:gz") as tf:
            member = tarfile.TarInfo("payload/../outside.txt")
            value = b"wrong"
            member.size = len(value)
            tf.addfile(member, io.BytesIO(value))
        meta = build_artifact_metadata(
            artifact_path=payload, engine="filesystem",
            resource="ingest-state", project="centrologistico",
            started_at=RunReport("centrologistico", "ingest-state", "backup").started_at,
            finished_at=RunReport("centrologistico", "ingest-state", "backup").started_at,
            status="OK",
        )
        write_artifact_metadata(meta)
        self.policy["artifact"]["path"] = str(payload)
        self.assertEqual(self.run_command(run_verify_artifact), 2)
        self.assertEqual(self.run_command(run_restore_test), 2)
        self.assertFalse((self.root / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
