from __future__ import annotations

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from core.cli import run_backup, run_restore_test, run_verify_artifact
from core.precheck import validate_required_config
from core.result import RunReport

TOKEN = "fixture-token-not-a-real-secret"


class InfluxBackupContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="backupkit-influx-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "out"
        self.policy = {
            "project": {"name": "centrologistico"},
            "resource": {"name": "timeseries", "type": "influxdb2",
                         "connection": {"host": "http://influxdb:8086", "org": "centrologistico"}},
            "artifact": {"output_dir": str(self.output)},
            "runtime": {"lock_dir": str(self.root / "locks")},
            "prechecks": {"require_free_space_mb": 0, "require_tools": []},
            "retention": {"enabled": False},
        }
        self.config = {"env": {"INFLUX_TOKEN": TOKEN}, "policy": self.policy}
        self.args = SimpleNamespace(env="fixture", policy="fixture")
        self.calls = []

    def fake_influx(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        self.assertEqual(command[1:5],
                         ["backup", "--host", "http://influxdb:8086", "--org"])
        self.assertNotIn(TOKEN, command)
        self.assertEqual(kwargs["env"]["INFLUX_TOKEN"], TOKEN)
        target = Path(command[-1])
        (target / "shard.dat").write_bytes(b"Influx fixture bytes")
        return subprocess.CompletedProcess(command, 0)

    def command(self, fn):
        with patch("core.cli.load_config", return_value=self.config), \
             patch("adapters.influxdb2.adapter.shutil.which", return_value="/usr/bin/influx"), \
             patch("adapters.influxdb2.adapter.subprocess.run", side_effect=self.fake_influx):
            return fn(self.args)

    def test_native_backup_artifact_verify_and_restore_fail_closed(self):
        self.assertEqual(self.command(run_backup), 0)
        self.assertEqual(len(self.calls), 1)
        artifacts = list(self.output.glob("*.tar.gz"))
        self.assertEqual(len(artifacts), 1)
        self.policy["artifact"]["path"] = str(artifacts[0])
        with tarfile.open(artifacts[0], "r:gz") as archive:
            self.assertEqual([x.name for x in archive.getmembers()], ["payload/shard.dat"])
        self.assertEqual(self.command(run_verify_artifact), 0)
        self.assertEqual(self.command(run_restore_test), 2)
        report = json.loads((self.output / "restore-test-report.json").read_text())
        self.assertEqual(report["final_status"], "ERROR")
        self.assertIn("isolated InfluxDB", report["final_summary"] if False else
                      str(report["phases"][0]["evidence"]["checks"]))
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn(TOKEN, json.dumps(report))

    def test_public_network_host_rejected_without_spawning_cli(self):
        self.policy["resource"]["connection"]["host"] = "http://192.168.1.90:8086"
        self.assertEqual(self.command(run_backup), 2)
        self.assertEqual(self.calls, [])

    def test_retention_rejected(self):
        self.policy["retention"]["enabled"] = True
        report = RunReport("centrologistico", "timeseries", "backup", resource_type="influxdb2")
        validate_required_config(self.config, report, "backup")
        self.assertTrue(report.has_errors())
        self.assertIn("retention.enabled", report.checks[0].message)


if __name__ == "__main__":
    unittest.main()
