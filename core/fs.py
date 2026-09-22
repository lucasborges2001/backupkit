from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any


class FilesystemSafetyError(RuntimeError):
    pass


def ensure_private_directory(path: str | Path) -> Path:
    directory = Path(path).expanduser()
    if directory.exists() and directory.is_symlink():
        raise FilesystemSafetyError(f'directory symlink is not allowed: {directory}')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise FilesystemSafetyError(f'directory symlink is not allowed: {directory}')
    resolved = directory.resolve()
    if not resolved.is_dir():
        raise FilesystemSafetyError(f'path is not a directory: {resolved}')
    mode = stat.S_IMODE(resolved.stat().st_mode)
    if mode & 0o077:
        raise FilesystemSafetyError(
            f'directory permissions too broad: {resolved} mode={mode:03o}'
        )
    return resolved


def publish_new_file(temp_path: str | Path, final_path: str | Path, *, mode: int = 0o600) -> Path:
    source = Path(temp_path)
    target = Path(final_path).expanduser()
    parent = ensure_private_directory(target.parent)
    target = parent / target.name
    if target.exists() or target.is_symlink():
        raise FileExistsError(f'target already exists: {target}')
    os.link(source, target)
    os.chmod(target, mode)
    source.unlink(missing_ok=True)
    return target


def atomic_write_text(
    path: str | Path,
    content: str,
    *,
    overwrite: bool,
    mode: int = 0o600,
) -> Path:
    target = Path(path).expanduser()
    parent = ensure_private_directory(target.parent)
    target = parent / target.name
    if target.is_symlink():
        raise FilesystemSafetyError(f'target symlink is not allowed: {target}')
    if not overwrite and target.exists():
        raise FileExistsError(f'target already exists: {target}')

    fd, temp_name = tempfile.mkstemp(
        prefix=f'.{target.name}.',
        suffix='.partial',
        dir=parent,
    )
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            if target.is_symlink():
                raise FilesystemSafetyError(f'target symlink is not allowed: {target}')
            os.replace(temp_path, target)
            os.chmod(target, mode)
        else:
            publish_new_file(temp_path, target, mode=mode)
        return target
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_write_json(
    path: str | Path,
    payload: Any,
    *,
    overwrite: bool,
    mode: int = 0o600,
) -> Path:
    return atomic_write_text(
        path,
        json.dumps(payload, indent=2, ensure_ascii=False) + '\n',
        overwrite=overwrite,
        mode=mode,
    )
