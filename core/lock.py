from __future__ import annotations

import os
from pathlib import Path


class LockError(Exception):
    pass


class FileLock:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.fd = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(self.fd, str(os.getpid()).encode('utf-8'))

    def release(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink(missing_ok=True)
        except Exception:
            pass
