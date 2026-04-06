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
from core.restore import build_restore_database_name
from core.result import CheckResult
from core.sql_validators import load_validators_from_policy, evaluate_validator, normalize_scalar_result, ValidatorConfigError
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
        cmd = [mysql_bin, '-h', host, '-P', str(port), '-u', username]
        if database:
            cmd += ['-D', database]
        cmd += ['-e', 'SELECT 1;']
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
        timestamp_slug = report.timestamp_slug
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

    @staticmethod
    def run_restore_test(config: dict, report):
        verification = ArtifactVerifier.verify(config, report, expected_engine=MySQLAdapter.name)
        if report.has_errors() or verification.artifact_path is None:
            return None

        policy = config['policy']
        env = config['env']
        host = deep_get(policy, 'resource.connection.host')
        port = int(deep_get(policy, 'resource.connection.port', 3306))
        username = deep_get(policy, 'resource.connection.username')
        timeout = int(deep_get(policy, 'prechecks.connectivity_timeout_sec', 5))
        mysql_bin = resolve_tool('mysql_query_client') or 'mysql'
        password = env.get('MYSQL_PASSWORD', '')
        restore_cfg = deep_get(policy, 'restore_test', {}) or {}
        prefix = restore_cfg.get('database_prefix', 'bkrt')
        temp_database = build_restore_database_name(report.project, report.resource, prefix)
        critical_tables = restore_cfg.get('critical_tables', []) or []
        smoke_queries = restore_cfg.get('smoke_queries', []) or []
        validators = []
        try:
            validators = load_validators_from_policy(restore_cfg.get('validators'))
        except ValidatorConfigError as exc:
            report.add(CheckResult('adapter.mysql.restore.validators.config', 'ERROR', 'blocking', f'Invalid validator configuration: {exc}'))
            return None

        env_vars = os.environ.copy()
        if password:
            env_vars['MYSQL_PWD'] = password

        report.set_restore_test({
            'database': temp_database,
            'artifact_path': str(verification.artifact_path),
            'cleanup_attempted': False,
            'cleanup_succeeded': False,
            'critical_tables': critical_tables,
            'smoke_queries': smoke_queries,
            'validators': [validator.as_dict() for validator in validators],
            'validator_results': [],
        })

        def run_mysql(sql: str, *, database: str | None = None, timeout_sec: int | None = None):
            cmd = [mysql_bin, '-h', host, '-P', str(port), '-u', username]
            if database:
                cmd += ['-D', database]
            cmd += ['-N', '-B', '-e', sql]
            return subprocess.run(
                cmd,
                env=env_vars,
                capture_output=True,
                text=True,
                timeout=timeout_sec or max(10, timeout),
            )

        try:
            created = run_mysql(f"CREATE DATABASE `{temp_database}`;")
            if created.returncode != 0:
                stderr = (created.stderr or created.stdout or '').strip()
                report.add(CheckResult('adapter.mysql.restore.create_db', 'ERROR', 'blocking', f'Failed to create temporary database {temp_database}: {stderr}'))
                return None
            report.add(CheckResult('adapter.mysql.restore.create_db', 'OK', 'blocking', f'Temporary database created: {temp_database}', {'database': temp_database}))

            with gzip.open(verification.artifact_path, 'rb') as dump_stream:
                restore_cmd = [mysql_bin, '-h', host, '-P', str(port), '-u', username, temp_database]
                # Use input= instead of stdin= to ensure we pass decompressed data
                completed = subprocess.run(restore_cmd, env=env_vars, input=dump_stream.read(), capture_output=True, timeout=max(30, timeout))
            if completed.returncode != 0:
                if isinstance(completed.stderr, bytes):
                    stderr = (completed.stderr or completed.stdout or b'').decode('utf-8', errors='replace').strip()
                else:
                    stderr = (completed.stderr or completed.stdout or '').strip()
                report.add(CheckResult('adapter.mysql.restore.import', 'ERROR', 'blocking', f'Restore import failed: {stderr}'))
                return None
            report.add(CheckResult('adapter.mysql.restore.import', 'OK', 'blocking', f'Artifact restored into temporary database {temp_database}'))

            for table in critical_tables:
                table_name = str(table).strip()
                sql = f"SHOW TABLES LIKE '{table_name.replace("'", "''")}';"
                check = run_mysql(sql, database=temp_database)
                if check.returncode != 0:
                    stderr = (check.stderr or check.stdout or '').strip()
                    report.add(CheckResult('adapter.mysql.restore.critical_table', 'ERROR', 'blocking', f'Critical table check failed for {table_name}: {stderr}', {'table': table_name}))
                    continue
                if table_name not in (check.stdout or '').splitlines():
                    report.add(CheckResult('adapter.mysql.restore.critical_table', 'ERROR', 'blocking', f'Critical table missing after restore: {table_name}', {'table': table_name}))
                else:
                    report.add(CheckResult('adapter.mysql.restore.critical_table', 'OK', 'blocking', f'Critical table restored: {table_name}', {'table': table_name}))

            for index, sql in enumerate(smoke_queries, start=1):
                smoke = run_mysql(str(sql), database=temp_database)
                if smoke.returncode != 0:
                    stderr = (smoke.stderr or smoke.stdout or '').strip()
                    report.add(CheckResult('adapter.mysql.restore.smoke_query', 'ERROR', 'blocking', f'Smoke query {index} failed: {stderr}', {'index': index, 'sql': str(sql)}))
                else:
                    report.add(CheckResult('adapter.mysql.restore.smoke_query', 'OK', 'blocking', f'Smoke query {index} executed successfully', {'index': index, 'sql': str(sql), 'output': (smoke.stdout or '').strip()}))

            validator_results = []
            for validator in validators:
                validation = run_mysql(validator.sql, database=temp_database)
                if validation.returncode != 0:
                    stderr = (validation.stderr or validation.stdout or '').strip()
                    status = 'WARN' if validator.severity == 'warning' else 'ERROR'
                    level = 'warning' if validator.severity == 'warning' else 'blocking'
                    result = {
                        'id': validator.validator_id,
                        'description': validator.description,
                        'sql': validator.sql,
                        'expected': {'rule': validator.rule, **({'value': validator.expected_value} if validator.expected_value is not None else {})},
                        'severity': validator.severity,
                        'actual_value': None,
                        'status': status,
                        'message': f'validator query failed: {stderr}',
                    }
                    validator_results.append(result)
                    report.add(CheckResult('adapter.mysql.restore.validator', status, level, f'Validator {validator.validator_id} query failed: {stderr}', {'validator_id': validator.validator_id, 'sql': validator.sql}))
                    continue

                actual_value = normalize_scalar_result(validation.stdout or '')
                evaluation = evaluate_validator(validator, actual_value)
                validator_results.append(evaluation.as_dict())
                if evaluation.ok:
                    report.add(CheckResult('adapter.mysql.restore.validator', 'OK', 'blocking', f'Validator {validator.validator_id} passed', {'validator_id': validator.validator_id, 'sql': validator.sql, 'actual_value': actual_value, 'rule': validator.rule, 'expected_value': validator.expected_value}))
                else:
                    status = 'WARN' if validator.severity == 'warning' else 'ERROR'
                    level = 'warning' if validator.severity == 'warning' else 'blocking'
                    report.add(CheckResult('adapter.mysql.restore.validator', status, level, f'Validator {validator.validator_id} failed: {evaluation.message}', {'validator_id': validator.validator_id, 'sql': validator.sql, 'actual_value': actual_value, 'rule': validator.rule, 'expected_value': validator.expected_value}))

            restore_meta = report.restore_test or {}
            restore_meta['validator_results'] = validator_results
            restore_meta['validators_summary'] = {
                'total': len(validator_results),
                'ok': sum(1 for item in validator_results if item['status'] == 'OK'),
                'warn': sum(1 for item in validator_results if item['status'] == 'WARN'),
                'error': sum(1 for item in validator_results if item['status'] == 'ERROR'),
            }
            report.set_restore_test(restore_meta)
            return temp_database
        finally:
            cleanup = run_mysql(f"DROP DATABASE IF EXISTS `{temp_database}`;")
            restore_meta = report.restore_test or {}
            restore_meta['cleanup_attempted'] = True
            restore_meta['cleanup_succeeded'] = cleanup.returncode == 0
            report.set_restore_test(restore_meta)
            if cleanup.returncode != 0:
                stderr = (cleanup.stderr or cleanup.stdout or '').strip()
                report.add(CheckResult('adapter.mysql.restore.cleanup', 'WARN', 'warning', f'Cleanup failed for temporary database {temp_database}: {stderr}', {'database': temp_database}))
            else:
                report.add(CheckResult('adapter.mysql.restore.cleanup', 'OK', 'blocking', f'Temporary database dropped: {temp_database}', {'database': temp_database}))
