from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from core.lock import FileLock


class FileLockTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / 'resource.lock'

    def tearDown(self):
        self.tempdir.cleanup()

    def test_second_holder_is_rejected_and_release_allows_reacquire(self):
        first = FileLock(self.path)
        second = FileLock(self.path)
        first.acquire()
        try:
            with self.assertRaises(FileExistsError):
                second.acquire()
        finally:
            first.release()

        self.assertTrue(self.path.exists())
        second.acquire()
        second.release()

    def test_stale_lock_file_does_not_block_without_active_holder(self):
        self.path.write_text('999999999', encoding='utf-8')
        lock = FileLock(self.path)
        lock.acquire()
        lock.release()

    @unittest.skipIf(os.name == 'nt', 'POSIX permission contract')
    def test_broad_lock_directory_is_rejected(self):
        broad = Path(self.tempdir.name) / 'broad'
        broad.mkdir()
        broad.chmod(0o755)
        lock = FileLock(broad / 'resource.lock')
        with self.assertRaises(Exception):
            lock.acquire()

    @unittest.skipIf(os.name == 'nt', 'symlink semantics differ on Windows CI')
    def test_lock_symlink_is_rejected(self):
        actual = Path(self.tempdir.name) / 'actual.lock'
        actual.write_text('not-a-lock', encoding='utf-8')
        self.path.symlink_to(actual)
        lock = FileLock(self.path)
        with self.assertRaises(Exception):
            lock.acquire()

    @unittest.skipIf(os.name == 'nt', 'POSIX permission contract')
    def test_lock_file_is_private(self):
        lock = FileLock(self.path)
        lock.acquire()
        try:
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        finally:
            lock.release()


if __name__ == '__main__':
    unittest.main()
