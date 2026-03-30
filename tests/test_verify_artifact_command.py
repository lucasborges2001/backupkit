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

from core.cli import run_backup, run_verify_artifact


class VerifyArtifactCommandTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.bin_dir = self.root / 'bin'
        self.bin_dir.mkdir()
        self.output_dir = self.root / 'output'
        self.lock_dir = self.root / 'locks'
        self.backup_policy_path = self.root / 'backup.policy.yml'
        self.verify_policy_path = self.root / 'verify.policy.yml'
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
        base_policy = textwrap.dedent(f'''
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
        ''')
        self.backup_policy_path.write_text(base_policy, encoding='utf-8')

    def tearDown(self):
        self.tempdir.cleanup()

    def _run_backup(self):
        args = argparse.Namespace(env=str(self.env_path), policy=str(self.backup_policy_path))
        original_path = os.environ.get('PATH', '')
        with patch.dict(os.environ, {'PATH': f'{self.bin_dir}{os.pathsep}{original_path}'}):
            with patch('adapters.mysql.adapter.tcp_connectivity', return_value=True):
                exit_code = run_backup(args)
        self.assertEqual(exit_code, 0)
        report = json.loads((self.output_dir / 'backup-report.json').read_text(encoding='utf-8'))
        return Path(report['artifact']['path']), Path(report['artifact']['metadata_path'])

    def test_verify_artifact_validates_existing_backup(self):
        artifact_path, metadata_path = self._run_backup()
        self.verify_policy_path.write_text(self.backup_policy_path.read_text(encoding='utf-8') + textwrap.dedent(f'''

            artifact:
              output_dir: {self.output_dir}
              path: {artifact_path}
              metadata_path: {metadata_path}
        '''), encoding='utf-8')
        # fix duplicated key by replacing final artifact block cleanly
        self.verify_policy_path.write_text(textwrap.dedent(f'''
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
              path: {artifact_path}
              metadata_path: {metadata_path}

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

        args = argparse.Namespace(env=str(self.env_path), policy=str(self.verify_policy_path))
        original_path = os.environ.get('PATH', '')
        with patch.dict(os.environ, {'PATH': f'{self.bin_dir}{os.pathsep}{original_path}'}):
            exit_code = run_verify_artifact(args)

        self.assertEqual(exit_code, 0)
        report = json.loads((self.output_dir / 'verify-artifact-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['command'], 'verify-artifact')
        self.assertEqual(report['status'], 'OK')
        self.assertEqual(report['artifact']['path'], str(artifact_path))
        checks = {c['id']: c for c in report['checks']}
        self.assertEqual(checks['artifact.file.exists']['status'], 'OK')
        self.assertEqual(checks['artifact.gzip.valid']['status'], 'OK')
        self.assertEqual(checks['artifact.sha256.match']['status'], 'OK')
        self.assertEqual(checks['artifact.metadata.consistency']['status'], 'OK')

    def test_verify_artifact_detects_sha_mismatch(self):
        artifact_path, metadata_path = self._run_backup()
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        metadata['sha256'] = '0' * 64
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')

        self.verify_policy_path.write_text(textwrap.dedent(f'''
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
              path: {artifact_path}
              metadata_path: {metadata_path}

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

        args = argparse.Namespace(env=str(self.env_path), policy=str(self.verify_policy_path))
        original_path = os.environ.get('PATH', '')
        with patch.dict(os.environ, {'PATH': f'{self.bin_dir}{os.pathsep}{original_path}'}):
            exit_code = run_verify_artifact(args)

        self.assertEqual(exit_code, 2)
        report = json.loads((self.output_dir / 'verify-artifact-report.json').read_text(encoding='utf-8'))
        checks = {c['id']: c for c in report['checks']}
        self.assertEqual(checks['artifact.sha256.match']['status'], 'ERROR')
        self.assertEqual(report['status'], 'ERROR')


if __name__ == '__main__':
    unittest.main()
