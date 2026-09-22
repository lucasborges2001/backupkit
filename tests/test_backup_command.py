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
        self.dump_audit_path = self.root / 'dump-audit.json'

        mysqldump_name = 'mysqldump.bat' if os.name == 'nt' else 'mysqldump'
        mysql_name = 'mysql.bat' if os.name == 'nt' else 'mysql'
        gzip_name = 'gzip.bat' if os.name == 'nt' else 'gzip'
        self.mysqldump_path = self.bin_dir / mysqldump_name
        self.mysql_path = self.bin_dir / mysql_name
        self.gzip_path = self.bin_dir / gzip_name

        if os.name == 'nt':
            self.mysqldump_path.write_text(
                '@echo off\n'
                'python -c "import sys; sys.stdout.write(\'-- sample dump\\nCREATE DATABASE IF NOT EXISTS `app`;\\n\')"\n',
                encoding='utf-8',
            )
            self.mysql_path.write_text(
                '@echo off\nexit /b 0\n',
                encoding='utf-8',
            )
            self.gzip_path.write_text(
                '@echo off\nexit /b 0\n',
                encoding='utf-8',
            )
        else:
            self.mysqldump_path.write_text(
                '#!/usr/bin/env python3\n'
                'import json, os, sys\n'
                'audit = os.environ.get("FAKE_DUMP_AUDIT")\n'
                'defaults = [arg.split("=", 1)[1] for arg in sys.argv[1:] if arg.startswith("--defaults-extra-file=")]\n'
                'if audit:\n'
                '    exists = bool(defaults and os.path.isfile(defaults[0]))\n'
                '    payload = {"argv": sys.argv[1:], "mysql_pwd_present": "MYSQL_PWD" in os.environ, "defaults_exists": exists, "defaults_mode": oct(os.stat(defaults[0]).st_mode & 0o777) if exists else None, "defaults_path": defaults[0] if defaults else None}\n'
                '    open(audit, "w", encoding="utf-8").write(json.dumps(payload))\n'
                'sys.stdout.write("-- sample dump\\nCREATE DATABASE IF NOT EXISTS `app`;\\n")\n',
                encoding='utf-8',
            )
            self.mysql_path.write_text(
                '#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n',
                encoding='utf-8',
            )
            self.gzip_path.write_text(
                '#!/usr/bin/env python3\nimport sys\nimport gzip\n# Simple mock gzip\n',
                encoding='utf-8',
            )
        self.mysqldump_path.chmod(self.mysqldump_path.stat().st_mode | stat.S_IEXEC)
        self.mysql_path.chmod(self.mysql_path.stat().st_mode | stat.S_IEXEC)
        self.gzip_path.chmod(self.gzip_path.stat().st_mode | stat.S_IEXEC)

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

    def test_run_backup_generates_gzip_metadata_and_strict_report(self):
        args = argparse.Namespace(env=str(self.env_path), policy=str(self.policy_path))
        original_path = os.environ.get('PATH', '')
        with patch.dict(os.environ, {
            'PATH': f'{self.bin_dir}{os.pathsep}{original_path}',
            'FAKE_DUMP_AUDIT': str(self.dump_audit_path),
        }, clear=False):
            with patch('adapters.mysql.adapter.tcp_connectivity', return_value=True):
                exit_code = run_backup(args)

        self.assertEqual(exit_code, 0)

        backup_report = self.output_dir / 'backup-report.json'
        self.assertTrue(backup_report.exists())
        report = json.loads(backup_report.read_text(encoding='utf-8'))
        self.assertEqual(report['report_version'], 2)
        self.assertEqual(report['metadata']['command'], 'backup')
        self.assertEqual(report['final_status'], 'OK')
        self.assertEqual(len(report['artifacts']), 1)
        self.assertNotIn('status', report)
        self.assertNotIn('artifact', report)

        artifact = report['artifacts'][0]
        artifact_path = Path(artifact['path'])
        metadata_path = Path(artifact['metadata_path'])
        self.assertTrue(artifact_path.is_absolute())
        self.assertTrue(metadata_path.is_absolute())
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
        self.assertEqual(metadata['sha256'], artifact['sha256'])
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(self.output_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(artifact_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(metadata_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(backup_report.stat().st_mode), 0o600)

            audit = json.loads(self.dump_audit_path.read_text(encoding='utf-8'))
            self.assertFalse(audit['mysql_pwd_present'])
            self.assertTrue(audit['defaults_exists'])
            self.assertEqual(audit['defaults_mode'], '0o600')
            self.assertFalse(Path(audit['defaults_path']).exists())
            argv = audit['argv']
            self.assertTrue(any(arg.startswith('--defaults-extra-file=') for arg in argv))
            for flag in [
                '--single-transaction',
                '--quick',
                '--routines',
                '--triggers',
                '--events',
                '--hex-blob',
                '--no-tablespaces',
                '--set-gtid-purged=OFF',
            ]:
                self.assertIn(flag, argv)


if __name__ == '__main__':
    unittest.main()
