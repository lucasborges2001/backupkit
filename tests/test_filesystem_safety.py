from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from core.fs import FilesystemSafetyError, atomic_write_json, ensure_private_directory


class FilesystemSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    @unittest.skipIf(os.name == 'nt', 'POSIX permission contract')
    def test_private_directory_is_created_0700(self):
        path = self.root / 'private'
        resolved = ensure_private_directory(path)
        self.assertEqual(stat.S_IMODE(resolved.stat().st_mode), 0o700)

    @unittest.skipIf(os.name == 'nt', 'POSIX permission contract')
    def test_broad_directory_fails_closed(self):
        path = self.root / 'broad'
        path.mkdir()
        path.chmod(0o755)
        with self.assertRaises(FilesystemSafetyError):
            ensure_private_directory(path)

    @unittest.skipIf(os.name == 'nt', 'POSIX permission contract')
    def test_atomic_json_is_private_and_non_overwriting(self):
        directory = ensure_private_directory(self.root / 'private')
        target = directory / 'artifact.metadata.json'
        atomic_write_json(target, {'ok': True}, overwrite=False)

        self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'ok': True})
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        with self.assertRaises(FileExistsError):
            atomic_write_json(target, {'ok': False}, overwrite=False)

    @unittest.skipIf(os.name == 'nt', 'symlink semantics differ on Windows CI')
    def test_atomic_write_rejects_symlink_target(self):
        directory = ensure_private_directory(self.root / 'private')
        actual = directory / 'actual.json'
        actual.write_text('{}', encoding='utf-8')
        target = directory / 'target.json'
        target.symlink_to(actual)
        with self.assertRaises(FilesystemSafetyError):
            atomic_write_json(target, {'ok': True}, overwrite=True)


if __name__ == '__main__':
    unittest.main()
