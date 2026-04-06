from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from core.cli import run_backup, run_restore_test


FAKE_MYSQL = r'''#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

state_path = Path(os.environ['FAKE_MYSQL_STATE'])
if state_path.exists():
    state = json.loads(state_path.read_text(encoding='utf-8'))
else:
    state = {'databases': {}}

def save():
    state_path.write_text(json.dumps(state), encoding='utf-8')

def ensure_db(name):
    state['databases'].setdefault(name, {'tables': {}})

args = sys.argv[1:]
sql = ''
db = None
i = 0
while i < len(args):
    arg = args[i]
    if arg in {'-h', '--host', '-P', '--port', '-u', '--user', '-D', '-e'}:
        if i + 1 < len(args):
            value = args[i + 1]
            if arg == '-D':
                db = value
            elif arg == '-e':
                sql = value
        i += 2
        continue
    if arg in {'-N', '-B'}:
        i += 1
        continue
    if not arg.startswith('-'):
        db = arg
    i += 1

if sql:
    sql_clean = sql.strip()
    m = re.search(r'CREATE DATABASE `?([a-zA-Z0-9_]+)`?', sql_clean, re.I)
    if m:
        ensure_db(m.group(1))
        save()
        sys.exit(0)
    m = re.search(r'DROP DATABASE IF EXISTS `?([a-zA-Z0-9_]+)`?', sql_clean, re.I)
    if m:
        state['databases'].pop(m.group(1), None)
        save()
        sys.exit(0)
    m = re.search(r"SHOW TABLES LIKE '([^']+)'", sql_clean, re.I)
    if m:
        table = m.group(1)
        if db and table in state['databases'].get(db, {}).get('tables', {}):
            sys.stdout.write(table + '\n')
        sys.exit(0)
    if 'SELECT 1' in sql_clean.upper():
        sys.stdout.write('1\n')
        sys.exit(0)
    m = re.search(r'SELECT COUNT\(\*\) FROM ([a-zA-Z0-9_]+)', sql_clean, re.I)
    if m:
        table = m.group(1)
        rows = state['databases'].get(db, {}).get('tables', {}).get(table, [])
        sys.stdout.write(str(len(rows)) + '\n')
        sys.exit(0)
    sys.exit(0)

if not db:
    sys.exit(0)
ensure_db(db)
content = sys.stdin.buffer.read().decode('utf-8', errors='replace')
for table in re.findall(r'CREATE TABLE `?([a-zA-Z0-9_]+)`?', content, re.IGNORECASE):
    state['databases'][db]['tables'].setdefault(table, [])
for table, values in re.findall(r'INSERT INTO `?([a-zA-Z0-9_]+)`?.*?VALUES\s*\((.*?)\)', content, re.IGNORECASE | re.DOTALL):
    state['databases'][db]['tables'].setdefault(table, []).append(values)
save()
sys.exit(0)
'''


class RestoreTestCommandTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.bin_dir = self.root / 'bin'
        self.bin_dir.mkdir()
        self.output_dir = self.root / 'output'
        self.lock_dir = self.root / 'locks'
        self.backup_policy_path = self.root / 'backup.policy.yml'
        self.restore_policy_path = self.root / 'restore.policy.yml'
        self.env_path = self.root / '.env.backup'
        self.state_path = self.root / 'mysql_state.json'
        
        mysqldump_name = 'mysqldump.bat' if os.name == 'nt' else 'mysqldump'
        mysql_name = 'mysql.bat' if os.name == 'nt' else 'mysql'
        gzip_name = 'gzip.bat' if os.name == 'nt' else 'gzip'
        self.mysqldump_path = self.bin_dir / mysqldump_name
        self.mysql_path = self.bin_dir / mysql_name
        self.gzip_path = self.bin_dir / gzip_name

        if os.name == 'nt':
            # Create a separate python script for the complex mock
            mysql_py = self.bin_dir / 'mysql_logic.py'
            mysql_py.write_text(FAKE_MYSQL, encoding='utf-8')

            self.mysqldump_path.write_text(
                '@echo off\n'
                'python -c "import sys; sys.stdout.write(\'-- sample dump\\nCREATE TABLE users (id int);\\nINSERT INTO users VALUES (1);\\nCREATE TABLE orders (id int);\\nINSERT INTO orders VALUES (9);\\n\')"\n',
                encoding='utf-8',
            )
            self.mysql_path.write_text(
                f'@echo off\n'
                f'set "RAW_ARGS=%*"\n'
                f'echo %RAW_ARGS% | findstr /I "SELECT.1" >nul && ( echo 1 & exit /b 0 )\n'
                f'set FAKE_MYSQL_STATE={self.state_path}\n'
                f'python "%~dp0mysql_logic.py" %*\n',
                encoding='utf-8',
            )
            self.gzip_path.write_text(
                '@echo off\nexit /b 0\n',
                encoding='utf-8',
            )
        else:
            self.mysqldump_path.write_text(
                '#!/usr/bin/env python3\n'
                'import sys\n'
                'sys.stdout.write("-- sample dump\\nCREATE TABLE users (id int);\\nINSERT INTO users VALUES (1);\\nCREATE TABLE orders (id int);\\nINSERT INTO orders VALUES (9);\\n")\n',
                encoding='utf-8',
            )
            self.mysql_path.write_text(FAKE_MYSQL, encoding='utf-8')
            self.gzip_path.write_text(
                '#!/usr/bin/env python3\nimport sys\nimport gzip\n# Simple mock gzip\n',
                encoding='utf-8',
            )
        self.mysqldump_path.chmod(self.mysqldump_path.stat().st_mode | stat.S_IEXEC)
        self.mysql_path.chmod(self.mysql_path.stat().st_mode | stat.S_IEXEC)
        if hasattr(self, 'gzip_path'):
            self.gzip_path.chmod(self.gzip_path.stat().st_mode | stat.S_IEXEC)

        self.env_path.write_text('MYSQL_PASSWORD="secret"\n', encoding='utf-8')
        self.backup_policy_path.write_text(textwrap.dedent(f'''
            project:
              name: cargadores

            resource:
              name: mysql-main
              type: mysql
              connection:
                host: 127.0.0.1
                port: 3306
                database: app
                username: root

            artifact:
              output_dir: {self.output_dir}

            runtime:
              lock_dir: {self.lock_dir}

            prechecks:
              require_free_space_mb: 1
              warn_free_space_below_mb: 2
              connectivity_timeout_sec: 1
              require_tools:
                - mysql_query_client
                - mysql_dump_client
                - gzip_provider
                - hash_provider

            notifications:
              telegram:
                enabled: false
        '''), encoding='utf-8')

    def tearDown(self):
        self.tempdir.cleanup()

    def _env(self):
        original_path = os.environ.get('PATH', '')
        return {
            'PATH': f'{self.bin_dir}{os.pathsep}{original_path}',
            'FAKE_MYSQL_STATE': str(self.state_path),
        }

    def _run_backup(self):
        args = argparse.Namespace(env=str(self.env_path), policy=str(self.backup_policy_path))
        with patch.dict(os.environ, self._env(), clear=False):
            with patch('adapters.mysql.adapter.tcp_connectivity', return_value=True):
                code = run_backup(args)
        self.assertEqual(code, 0)
        report = json.loads((self.output_dir / 'backup-report.json').read_text(encoding='utf-8'))
        return report['artifact']['path'], report['artifact']['metadata_path']

    def test_restore_test_restores_and_cleans_up(self):
        artifact_path, metadata_path = self._run_backup()
        self.restore_policy_path.write_text(textwrap.dedent(f'''
            project:
              name: cargadores

            resource:
              name: mysql-main
              type: mysql
              connection:
                host: 127.0.0.1
                port: 3306
                username: root

            artifact:
              output_dir: {self.output_dir}
              path: {artifact_path}
              metadata_path: {metadata_path}

            restore_test:
              database_prefix: bkrt
              smoke_queries:
                - SELECT 1;
                - SELECT COUNT(*) FROM users;

            runtime:
              lock_dir: {self.lock_dir}

            prechecks:
              require_free_space_mb: 1
              warn_free_space_below_mb: 2
              connectivity_timeout_sec: 1
              require_tools:
                - mysql_query_client
                - gzip_provider
                - hash_provider

            notifications:
              telegram:
                enabled: false
        '''), encoding='utf-8')

        args = argparse.Namespace(env=str(self.env_path), policy=str(self.restore_policy_path))
        with patch.dict(os.environ, self._env(), clear=False):
            with patch('adapters.mysql.adapter.tcp_connectivity', return_value=True):
                code = run_restore_test(args)

        self.assertEqual(code, 0)
        report = json.loads((self.output_dir / 'restore-test-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['command'], 'restore-test')
        self.assertEqual(report['status'], 'OK')
        self.assertTrue(report['restore_test']['cleanup_attempted'])
        self.assertTrue(report['restore_test']['cleanup_succeeded'])
        checks = report['checks']
        ids = [c['id'] for c in checks]
        self.assertIn('adapter.mysql.restore.create_db', ids)
        self.assertIn('adapter.mysql.restore.import', ids)
        self.assertIn('adapter.mysql.restore.smoke_query', ids)
        self.assertIn('adapter.mysql.restore.cleanup', ids)
        state = json.loads(self.state_path.read_text(encoding='utf-8'))
        self.assertEqual(state['databases'], {})

    def test_restore_test_fails_when_critical_table_missing(self):
        artifact_path, metadata_path = self._run_backup()
        self.restore_policy_path.write_text(textwrap.dedent(f'''
            project:
              name: cargadores

            resource:
              name: mysql-main
              type: mysql
              connection:
                host: 127.0.0.1
                port: 3306
                username: root

            artifact:
              output_dir: {self.output_dir}
              path: {artifact_path}
              metadata_path: {metadata_path}

            restore_test:
              critical_tables:
                - users
                - missing_table

            runtime:
              lock_dir: {self.lock_dir}

            prechecks:
              require_free_space_mb: 1
              connectivity_timeout_sec: 1
              require_tools:
                - mysql_query_client
                - gzip_provider
                - hash_provider

            notifications:
              telegram:
                enabled: false
        '''), encoding='utf-8')

        args = argparse.Namespace(env=str(self.env_path), policy=str(self.restore_policy_path))
        with patch.dict(os.environ, self._env(), clear=False):
            with patch('adapters.mysql.adapter.tcp_connectivity', return_value=True):
                code = run_restore_test(args)

        self.assertEqual(code, 2)
        report = json.loads((self.output_dir / 'restore-test-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'ERROR')
        self.assertTrue(report['restore_test']['cleanup_succeeded'])
        failures = [c for c in report['checks'] if c['id'] == 'adapter.mysql.restore.critical_table' and c['status'] == 'ERROR']
        self.assertTrue(any('missing_table' in c['message'] for c in failures))

    def test_restore_test_runs_sql_validators_and_reports_results(self):
        artifact_path, metadata_path = self._run_backup()
        self.restore_policy_path.write_text(textwrap.dedent(f'''
            project:
              name: cargadores

            resource:
              name: mysql-main
              type: mysql
              connection:
                host: 127.0.0.1
                port: 3306
                username: root

            artifact:
              output_dir: {self.output_dir}
              path: {artifact_path}
              metadata_path: {metadata_path}

            restore_test:
              validators:
                - id: users_non_zero
                  sql: SELECT COUNT(*) FROM users;
                  expected:
                    rule: non_zero
                  severity: error
                - id: users_equals_one
                  sql: SELECT COUNT(*) FROM users;
                  expected:
                    rule: equals
                    value: 1
                  severity: error
                - id: orders_less_than_two
                  sql: SELECT COUNT(*) FROM orders;
                  expected:
                    rule: less_than
                    value: 2
                  severity: warning
                - id: missing_table_zero
                  sql: SELECT COUNT(*) FROM missing_table;
                  expected:
                    rule: zero
                  severity: warning

            runtime:
              lock_dir: {self.lock_dir}

            prechecks:
              require_free_space_mb: 1
              connectivity_timeout_sec: 1
              require_tools:
                - mysql_query_client
                - gzip_provider
                - hash_provider

            notifications:
              telegram:
                enabled: false
        '''), encoding='utf-8')

        args = argparse.Namespace(env=str(self.env_path), policy=str(self.restore_policy_path))
        with patch.dict(os.environ, self._env(), clear=False):
            with patch('adapters.mysql.adapter.tcp_connectivity', return_value=True):
                code = run_restore_test(args)

        self.assertEqual(code, 0)
        report = json.loads((self.output_dir / 'restore-test-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'OK')
        validator_results = report['restore_test']['validator_results']
        self.assertEqual(len(validator_results), 4)
        by_id = {item['id']: item for item in validator_results}
        self.assertEqual(by_id['users_non_zero']['status'], 'OK')
        self.assertEqual(by_id['users_non_zero']['actual_value'], 1)
        self.assertEqual(by_id['users_equals_one']['status'], 'OK')
        self.assertEqual(by_id['orders_less_than_two']['status'], 'OK')
        self.assertEqual(by_id['missing_table_zero']['status'], 'OK')
        self.assertEqual(report['restore_test']['validators_summary']['total'], 4)
        self.assertEqual(report['restore_test']['validators_summary']['error'], 0)
        self.assertEqual(report['restore_test']['validators_summary']['warn'], 0)

    def test_restore_test_rejects_invalid_validator_config(self):
        artifact_path, metadata_path = self._run_backup()
        self.restore_policy_path.write_text(textwrap.dedent(f'''
            project:
              name: cargadores

            resource:
              name: mysql-main
              type: mysql
              connection:
                host: 127.0.0.1
                port: 3306
                username: root

            artifact:
              output_dir: {self.output_dir}
              path: {artifact_path}
              metadata_path: {metadata_path}

            restore_test:
              validators:
                - id: invalid_missing_value
                  sql: SELECT COUNT(*) FROM users;
                  expected:
                    rule: greater_than
                  severity: error

            runtime:
              lock_dir: {self.lock_dir}

            prechecks:
              require_free_space_mb: 1
              connectivity_timeout_sec: 1
              require_tools:
                - mysql_query_client
                - gzip_provider
                - hash_provider

            notifications:
              telegram:
                enabled: false
        '''), encoding='utf-8')

        args = argparse.Namespace(env=str(self.env_path), policy=str(self.restore_policy_path))
        with patch.dict(os.environ, self._env(), clear=False):
            with patch('adapters.mysql.adapter.tcp_connectivity', return_value=True):
                code = run_restore_test(args)

        self.assertEqual(code, 2)
        report = json.loads((self.output_dir / 'restore-test-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'ERROR')
        config_errors = [c for c in report['checks'] if c['id'] == 'core.config.required']
        self.assertTrue(any('restore_test.validators(valid)' in c['message'] for c in config_errors))

    def test_restore_test_validator_warning_degrades_to_warn_not_error(self):
        artifact_path, metadata_path = self._run_backup()
        self.restore_policy_path.write_text(textwrap.dedent(f'''
            project:
              name: cargadores

            resource:
              name: mysql-main
              type: mysql
              connection:
                host: 127.0.0.1
                port: 3306
                username: root

            artifact:
              output_dir: {self.output_dir}
              path: {artifact_path}
              metadata_path: {metadata_path}

            restore_test:
              validators:
                - id: users_should_be_zero
                  sql: SELECT COUNT(*) FROM users;
                  expected:
                    rule: zero
                  severity: warning

            runtime:
              lock_dir: {self.lock_dir}

            prechecks:
              require_free_space_mb: 1
              connectivity_timeout_sec: 1
              require_tools:
                - mysql_query_client
                - gzip_provider
                - hash_provider

            notifications:
              telegram:
                enabled: false
        '''), encoding='utf-8')

        args = argparse.Namespace(env=str(self.env_path), policy=str(self.restore_policy_path))
        with patch.dict(os.environ, self._env(), clear=False):
            with patch('adapters.mysql.adapter.tcp_connectivity', return_value=True):
                code = run_restore_test(args)

        self.assertEqual(code, 1)
        report = json.loads((self.output_dir / 'restore-test-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'WARN')
        validator_results = report['restore_test']['validator_results']
        self.assertEqual(len(validator_results), 1)
        self.assertEqual(validator_results[0]['status'], 'WARN')
        validator_checks = [c for c in report['checks'] if c['id'] == 'adapter.mysql.restore.validator']
        self.assertTrue(any(c['status'] == 'WARN' for c in validator_checks))


if __name__ == '__main__':
    unittest.main()
