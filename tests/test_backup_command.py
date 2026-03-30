from __future__ import annotations

import argparse
import gzip
import json
import os
import stat
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from core.cli import run_backup


class BackupCommandTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.bin_dir = self.root / 'bin'
        self.bin_dir.mkdir()
        self.output_dir = self.root / 'output'
        self.lock_dir = self.root / 'locks'
        self.policy_path = self.root / 'backup.policy.yml'
        self.env_path = self.root / '.env.backup'
        self.mysqldump_path = self.bin_dir / 'mysqldump'
        self.mysql_path = self.bin_dir / 'mysql'

        self.mysqldump_path.write_text(
            '#!/usr/bin/env python3\n'
            'import sys\n'
            'sys.stdout.write("-- sample dump\\nCREATE DATABASE IF NOT EXISTS `app`;\\n")\n',
            encoding='utf-8',
        )
        self.mysql_path.write_text(
            '#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n',
            encoding='utf-8',
        )
        self.mysqldump_path.chmod(self.mysqldump_path.stat().st_mode | stat.S_IEXEC)
        self.mysql_path.chmod(self.mysql_path.stat().st_mode | stat.S_IEXEC)

        self.env_path.write_text('MYSQL_PASSWORD="secret"\n', encoding='utf-8')
        self.policy_path.write_text(textwrap.dedent(f'''
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

    def test_run_backup_generates_gzip_metadata_and_report(self):
        args = argparse.Namespace(env=str(self.env_path), policy=str(self.policy_path))
        original_path = os.environ.get('PATH', '')
        with patch.dict(os.environ, {'PATH': f'{self.bin_dir}{os.pathsep}{original_path}'}):
            with patch('adapters.mysql.adapter.tcp_connectivity', return_value=True):
                exit_code = run_backup(args)

        self.assertEqual(exit_code, 0)

        backup_report = self.output_dir / 'backup-report.json'
        self.assertTrue(backup_report.exists())
        report = json.loads(backup_report.read_text(encoding='utf-8'))
        self.assertEqual(report['command'], 'backup')
        self.assertEqual(report['status'], 'OK')
        self.assertIn('artifact', report)

        artifact_path = Path(report['artifact']['path'])
        metadata_path = Path(report['artifact']['metadata_path'])
        self.assertTrue(artifact_path.exists())
        self.assertTrue(metadata_path.exists())
        self.assertTrue(artifact_path.name.endswith('.sql.gz'))

        with gzip.open(artifact_path, 'rt', encoding='utf-8') as fh:
            content = fh.read()
        self.assertIn('CREATE DATABASE IF NOT EXISTS `app`', content)

        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        self.assertEqual(metadata['engine'], 'mysql')
        self.assertEqual(metadata['project'], 'cargadores')
        self.assertEqual(metadata['resource'], 'mysql-main')
        self.assertEqual(metadata['status'], 'OK')
        self.assertEqual(metadata['path'], str(artifact_path))
        self.assertEqual(metadata['sha256'], report['artifact']['sha256'])


if __name__ == '__main__':
    unittest.main()
