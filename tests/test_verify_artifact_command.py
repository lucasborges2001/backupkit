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
        self.mysqldump_path = self.bin_dir / ('mysqldump.bat' if os.name == 'nt' else 'mysqldump')
        self.mysql_path = self.bin_dir / ('mysql.bat' if os.name == 'nt' else 'mysql')
        self.gzip_path = self.bin_dir / ('gzip.bat' if os.name == 'nt' else 'gzip')

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
                'import sys\n'
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
        artifact = report['artifacts'][0]
        return Path(artifact['path']), Path(artifact['metadata_path'])

    def _write_verify_policy(self, artifact_path: Path, metadata_path: Path):
        self.verify_policy_path.write_text(textwrap.dedent(f'''
            project:
              name: cargadores

            resource:
              name: mysql-main
              type: mysql

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
                - gzip_provider
                - hash_provider

            notifications:
              telegram:
                enabled: false
        '''), encoding='utf-8')

    def test_verify_artifact_validates_existing_backup(self):
        artifact_path, metadata_path = self._run_backup()
        self._write_verify_policy(artifact_path, metadata_path)

        args = argparse.Namespace(env=str(self.env_path), policy=str(self.verify_policy_path))
        original_path = os.environ.get('PATH', '')
        with patch.dict(os.environ, {'PATH': f'{self.bin_dir}{os.pathsep}{original_path}'}):
            exit_code = run_verify_artifact(args)

        self.assertEqual(exit_code, 0)
        report = json.loads((self.output_dir / 'verify-artifact-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['metadata']['command'], 'verify-artifact')
        self.assertEqual(report['final_status'], 'OK')
        self.assertEqual(report['artifacts'][0]['path'], str(artifact_path))
        checks = {c['id']: c for c in report['phases'][0]['evidence']['checks']}
        self.assertEqual(checks['artifact.file.exists']['status'], 'OK')
        self.assertEqual(checks['artifact.gzip.valid']['status'], 'OK')
        self.assertEqual(checks['artifact.sha256.match']['status'], 'OK')
        self.assertEqual(checks['artifact.metadata.consistency']['status'], 'OK')
        self.assertNotIn('status', report)
        self.assertNotIn('artifact', report)
        self.assertNotIn('checks', report)

    def test_verify_artifact_detects_sha_mismatch(self):
        artifact_path, metadata_path = self._run_backup()
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        metadata['sha256'] = '0' * 64
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        self._write_verify_policy(artifact_path, metadata_path)

        args = argparse.Namespace(env=str(self.env_path), policy=str(self.verify_policy_path))
        original_path = os.environ.get('PATH', '')
        with patch.dict(os.environ, {'PATH': f'{self.bin_dir}{os.pathsep}{original_path}'}):
            exit_code = run_verify_artifact(args)

        self.assertEqual(exit_code, 2)
        report = json.loads((self.output_dir / 'verify-artifact-report.json').read_text(encoding='utf-8'))
        checks = {c['id']: c for c in report['phases'][0]['evidence']['checks']}
        self.assertEqual(checks['artifact.sha256.match']['status'], 'ERROR')
        self.assertEqual(report['final_status'], 'ERROR')

    def test_verify_artifact_rejects_removed_policy_aliases(self):
        self.verify_policy_path.write_text(textwrap.dedent(f'''
            project:
              name: cargadores

            resource:
              name: mysql-main
              type: mysql

            artifact:
              output_dir: {self.output_dir}
              verify_path: removed.sql.gz
              verify_metadata_path: removed.sql.gz.metadata.json

            runtime:
              lock_dir: {self.lock_dir}

            prechecks:
              require_free_space_mb: 1

            notifications:
              telegram:
                enabled: false
        '''), encoding='utf-8')

        args = argparse.Namespace(env=str(self.env_path), policy=str(self.verify_policy_path))
        exit_code = run_verify_artifact(args)

        self.assertEqual(exit_code, 2)
        report = json.loads((self.output_dir / 'verify-artifact-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['final_status'], 'ERROR')
        checks = {c['id']: c for c in report['phases'][0]['evidence']['checks']}
        self.assertEqual(checks['core.config.unsupported']['status'], 'ERROR')
        self.assertIn('artifact.verify_path', checks['core.config.unsupported']['message'])
        self.assertIn('artifact.verify_metadata_path', checks['core.config.unsupported']['message'])
        self.assertEqual(checks['core.config.required']['status'], 'ERROR')


if __name__ == '__main__':
    unittest.main()
