from __future__ import annotations

import errno
import os
from pathlib import Path

from core.fs import ensure_private_directory

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None


class LockError(Exception):
    pass


class FileLock:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.fd: int | None = None

    def acquire(self):
        parent = ensure_private_directory(self.path.parent)
        self.path = parent / self.path.name
        if self.path.is_symlink():
            raise LockError(f'lock symlink is not allowed: {self.path}')

        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise LockError(f'lock symlink is not allowed: {self.path}') from exc
            raise
        try:
            if hasattr(os, 'fchmod'):
                os.fchmod(fd, 0o600)

            if fcntl is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise FileExistsError(str(self.path)) from exc
            elif msvcrt is not None:  # pragma: no cover - Windows
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b'0')
                os.lseek(fd, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise FileExistsError(str(self.path)) from exc
                    raise
            else:  # pragma: no cover
                raise LockError('No advisory file-lock backend available')

            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, str(os.getpid()).encode('utf-8'))
            os.fsync(fd)
            self.fd = fd
        except Exception:
            os.close(fd)
            raise

    def release(self):
        if self.fd is None:
            return
        fd = self.fd
        self.fd = None
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            elif msvcrt is not None:  # pragma: no cover - Windows
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)
