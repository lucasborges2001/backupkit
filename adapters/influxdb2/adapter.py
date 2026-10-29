from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone

from adapters.filesystem.adapter import _inventory, _make_archive, _scan_archive
from core.artifact import ArtifactVerifier
from core.backup import (build_artifact_metadata, build_backup_basename,
                         utc_timestamp_slug, write_artifact_metadata)
from core.config import deep_get
from core.fs import publish_new_file
from core.result import CheckResult

SAFE_HOSTS = frozenset(("http://127.0.0.1:8086", "http://influxdb:8086"))
ORG = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


class InfluxDB2Adapter:
    """Native InfluxDB 2 backup capture, never a live restore."""
    name = "influxdb2"

    @staticmethod
    def _inputs(config: dict) -> tuple[str, str, str, str]:
        host = deep_get(config["policy"], "resource.connection.host")
        org = deep_get(config["policy"], "resource.connection.org")
        token = config["env"].get("INFLUX_TOKEN", "")
        executable = shutil.which("influx")
        if host not in SAFE_HOSTS:
            raise ValueError("Influx host must be private service or loopback")
        if not isinstance(org, str) or not ORG.fullmatch(org):
            raise ValueError("Influx org is missing or invalid")
        if not token:
            raise ValueError("Private INFLUX_TOKEN is required")
        if not executable:
            raise ValueError("influx CLI missing")
        return executable, host, org, token

    @staticmethod
    def run_prechecks(config: dict, report):
        try:
            InfluxDB2Adapter._inputs(config)
            report.add(CheckResult("adapter.influxdb2.config", "OK", "blocking",
                                   "Native Influx CLI and private credentials present"))
        except (ValueError, OSError) as exc:
            report.add(CheckResult("adapter.influxdb2.config", "ERROR", "blocking",
                                   str(exc)))

    @staticmethod
    def run_backup(config: dict, report):
        InfluxDB2Adapter.run_prechecks(config, report)
        if report.has_errors():
            return None
        cli, host, org, token = InfluxDB2Adapter._inputs(config)
        output = Path(deep_get(config["policy"], "artifact.output_dir"))
        filename = build_backup_basename(report.project, report.resource,
                                         utc_timestamp_slug()).replace(".sql.gz", ".tar.gz")
        final = output / filename
        temp_file = None
        published = False
        try:
            if final.exists() or final.is_symlink():
                raise ValueError("Backup collision")
            with tempfile.TemporaryDirectory(prefix=".backupkit-influx-", dir=output) as scratch:
                work = Path(scratch)
                work.chmod(0o700)
                native = work / "native"
                native.mkdir(mode=0o700)
                environment = {
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOME": str(work),
                    "INFLUX_TOKEN": token,
                }
                result = subprocess.run(
                    [cli, "backup", "--host", host, "--org", org, str(native)],
                    env=environment, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, check=False, timeout=900,
                )
                if result.returncode:
                    raise ValueError("Native Influx backup failed")
                files = _inventory(native)
                with tempfile.NamedTemporaryFile(prefix=".influx-", suffix=".part",
                                                 dir=output, delete=False) as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    temp_file = Path(stream.name)
                _make_archive(native, temp_file, files)
                if _scan_archive(temp_file) != len(files):
                    raise ValueError("Influx archive inventory mismatch")
                publish_new_file(temp_file, final, mode=0o600)
                temp_file = None
                published = True
            metadata = build_artifact_metadata(
                artifact_path=final, engine=InfluxDB2Adapter.name,
                project=report.project, resource=report.resource,
                started_at=report.started_at, finished_at=datetime.now(timezone.utc),
                status="OK",
            )
            write_artifact_metadata(metadata)
            report.set_artifact(metadata)
            report.add(CheckResult("adapter.influxdb2.backup", "OK", "blocking",
                                   "Native backup archived with checksum; restore not proven",
                                   {"files": len(files)}))
            return metadata
        except (OSError, ValueError, tarfile.TarError, subprocess.TimeoutExpired) as exc:
            if published:
                final.unlink(missing_ok=True)
                final.with_suffix(final.suffix + ".metadata.json").unlink(missing_ok=True)
            report.add(CheckResult("adapter.influxdb2.backup", "ERROR", "blocking",
                                   "Influx backup failed: " + type(exc).__name__))
            return None
        finally:
            if temp_file is not None:
                temp_file.unlink(missing_ok=True)

    @staticmethod
    def run_verify_artifact(config: dict, report):
        artifact = ArtifactVerifier.verify(config, report, expected_engine=InfluxDB2Adapter.name)
        if report.has_errors() or artifact.artifact_path is None:
            return None
        try:
            files = _scan_archive(artifact.artifact_path)
            report.add(CheckResult("adapter.influxdb2.archive", "OK", "blocking",
                                   "Native capture container verified", {"files": files}))
        except (OSError, ValueError, tarfile.TarError):
            report.add(CheckResult("adapter.influxdb2.archive", "ERROR", "blocking",
                                   "Native capture archive invalid"))
        return artifact

    @staticmethod
    def run_restore_test(config: dict, report):
        InfluxDB2Adapter.run_verify_artifact(config, report)
        report.add(CheckResult("adapter.influxdb2.restore", "ERROR", "blocking",
                               "Restore requires a separately provisioned isolated InfluxDB 2 engine; "
                               "no influx restore was executed"))
        return None
