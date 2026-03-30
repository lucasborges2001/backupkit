from __future__ import annotations

import gzip
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from core.artifact import ArtifactVerifier
from core.backup import build_artifact_metadata, build_backup_basename, utc_timestamp_slug, write_artifact_metadata
from core.config import deep_get
from core.precheck import tcp_connectivity
from core.result import CheckResult
from core.tools import resolve_tool


class MySQLAdapter:
    name = 'mysql'

    @staticmethod
    def run_prechecks(config: dict, report):
        policy = config['policy']
        env = config['env']
        host = deep_get(policy, 'resource.connection.host')
        port = int(deep_get(policy, 'resource.connection.port', 3306))
        database = deep_get(policy, 'resource.connection.database')
        username = deep_get(policy, 'resource.connection.username')
        timeout = int(deep_get(policy, 'prechecks.connectivity_timeout_sec', 5))
        password = env.get('MYSQL_PASSWORD', '')

        try:
            tcp_connectivity(host, port, timeout)
            report.add(CheckResult('adapter.mysql.connectivity', 'OK', 'blocking', f'MySQL reachable at {host}:{port}'))
        except Exception as exc:
            report.add(CheckResult('adapter.mysql.connectivity', 'ERROR', 'blocking', f'MySQL not reachable at {host}:{port}: {exc}'))
            return

        mysql_bin = resolve_tool('mysql_query_client') or 'mysql'
        env_vars = os.environ.copy()
        if password:
            env_vars['MYSQL_PWD'] = password
        cmd = [mysql_bin, '-h', host, '-P', str(port), '-u', username, '-D', database, '-e', 'SELECT 1;']
        try:
            completed = subprocess.run(cmd, env=env_vars, capture_output=True, text=True, timeout=max(5, timeout))
            if completed.returncode != 0:
                stderr = (completed.stderr or completed.stdout or '').strip()
                report.add(CheckResult('adapter.mysql.auth', 'ERROR', 'blocking', f'MySQL auth/query failed: {stderr}'))
            else:
                report.add(CheckResult('adapter.mysql.auth', 'OK', 'blocking', 'MySQL auth and database query succeeded'))
        except Exception as exc:
            report.add(CheckResult('adapter.mysql.auth', 'ERROR', 'blocking', f'MySQL auth check failed: {exc}'))


    @staticmethod
    def run_verify_artifact(config: dict, report):
        return ArtifactVerifier.verify(config, report, expected_engine=MySQLAdapter.name)

    @staticmethod
    def run_backup(config: dict, report):
        MySQLAdapter.run_prechecks(config, report)
        if report.has_errors():
            return None

        policy = config['policy']
        env = config['env']
        output_dir = Path(deep_get(policy, 'artifact.output_dir'))
        host = deep_get(policy, 'resource.connection.host')
        port = int(deep_get(policy, 'resource.connection.port', 3306))
        database = deep_get(policy, 'resource.connection.database')
        username = deep_get(policy, 'resource.connection.username')
        password = env.get('MYSQL_PASSWORD', '')
        timestamp_slug = utc_timestamp_slug()
        final_path = output_dir / build_backup_basename(report.project, report.resource, timestamp_slug)
        temp_path = final_path.with_suffix(final_path.suffix + '.part')
        mysqldump_bin = resolve_tool('mysql_dump_client') or 'mysqldump'

        dump_cmd = [
            mysqldump_bin,
            '--host', host,
            '--port', str(port),
            '--user', username,
            '--single-transaction',
            '--quick',
            '--routines',
            '--triggers',
            '--events',
            '--databases', database,
        ]

        env_vars = os.environ.copy()
        if password:
            env_vars['MYSQL_PWD'] = password

        stderr_chunks: list[bytes] = []
        dump_process = None
        try:
            with temp_path.open('wb') as raw_output:
                with gzip.GzipFile(filename='', mode='wb', fileobj=raw_output, mtime=0) as gz_output:
                    dump_process = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env_vars)
                    assert dump_process.stdout is not None
                    for chunk in iter(lambda: dump_process.stdout.read(1024 * 1024), b''):
                        if chunk:
                            gz_output.write(chunk)
                    dump_process.stdout.close()
                    assert dump_process.stderr is not None
                    stderr_chunks = dump_process.stderr.read().splitlines()
                    dump_process.stderr.close()
                    return_code = dump_process.wait()
            if return_code != 0:
                stderr = b'\n'.join(stderr_chunks).decode('utf-8', errors='replace').strip()
                report.add(CheckResult('adapter.mysql.backup.dump', 'ERROR', 'blocking', f'MySQL dump failed: {stderr or "unknown error"}'))
                temp_path.unlink(missing_ok=True)
                return None
            if temp_path.stat().st_size == 0:
                report.add(CheckResult('adapter.mysql.backup.dump', 'ERROR', 'blocking', 'MySQL dump produced an empty gzip artifact'))
                temp_path.unlink(missing_ok=True)
                return None
            temp_path.replace(final_path)
            report.add(CheckResult('adapter.mysql.backup.dump', 'OK', 'blocking', f'MySQL dump + gzip completed: {final_path.name}', {'path': str(final_path)}))

            metadata = build_artifact_metadata(
                artifact_path=final_path,
                engine=MySQLAdapter.name,
                resource=report.resource,
                project=report.project,
                started_at=report.started_at,
                finished_at=datetime.now(timezone.utc),
                status='OK',
            )
            metadata_path = write_artifact_metadata(metadata)
            report.set_artifact(metadata)
            report.add(CheckResult('adapter.mysql.backup.sha256', 'OK', 'blocking', 'SHA256 calculated', {'sha256': metadata.sha256}))
            report.add(CheckResult('adapter.mysql.backup.metadata', 'OK', 'blocking', f'Artifact metadata written: {metadata_path}', {'metadata_path': str(metadata_path)}))
            return metadata
        except Exception as exc:
            if dump_process and dump_process.poll() is None:
                dump_process.kill()
            temp_path.unlink(missing_ok=True)
            report.add(CheckResult('adapter.mysql.backup.dump', 'ERROR', 'blocking', f'Backup execution failed: {exc}'))
            return None
