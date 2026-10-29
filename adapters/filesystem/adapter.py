from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import tarfile
import tempfile
from datetime import datetime, timezone

from core.artifact import ArtifactVerifier
from core.backup import build_artifact_metadata, build_backup_basename, utc_timestamp_slug, write_artifact_metadata
from core.config import deep_get
from core.fs import publish_new_file
from core.result import CheckResult


class FilesystemError(ValueError):
    pass


def _ensure_source(source: Path, output: Path) -> None:
    if not source.is_absolute() or not source.is_dir() or source.is_symlink():
        raise FilesystemError("filesystem.source_dir must be an existing absolute regular directory")
    if output == source or source in output.parents or output in source.parents:
        raise FilesystemError("source and artifact output directories must be disjoint")
    for ancestor in (source, *source.parents):
        if ancestor.is_symlink():
            raise FilesystemError("source ancestry must not contain symlinks")


def _inventory(source: Path) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for current, dirs, names in os.walk(source, topdown=True, followlinks=False):
        for name in dirs:
            path = Path(current) / name
            if path.is_symlink() or not path.is_dir():
                raise FilesystemError("source contains a symbolic link or non-directory")
        for name in names:
            path = Path(current) / name
            mode = path.lstat().st_mode
            if not stat.S_ISREG(mode) or path.is_symlink() or path.stat().st_nlink != 1:
                raise FilesystemError("source contains linked or non-regular file")
            files.append((path, path.relative_to(source).as_posix()))
    if not files:
        raise FilesystemError("source has no regular files")
    return sorted(files, key=lambda pair: pair[1])


def _make_archive(source: Path, target: Path, inventory: list[tuple[Path, str]]) -> None:
    with tarfile.open(target, mode="w:gz") as archive:
        for path, relative in inventory:
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise FilesystemError("source file type changed")
            member = tarfile.TarInfo("payload/" + relative)
            member.size = before.st_size
            member.mode = 0o600
            member.uid = member.gid = member.mtime = 0
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                after_open = os.fstat(stream.fileno())
                if (not stat.S_ISREG(after_open.st_mode) or after_open.st_nlink != 1
                        or (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) !=
                        (after_open.st_ino, after_open.st_dev, after_open.st_size, after_open.st_mtime_ns)):
                    raise FilesystemError("source changed during backup")
                archive.addfile(member, stream)
            after = path.lstat()
            if (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) != (
                    after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns):
                raise FilesystemError("source changed during backup")


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    if not members or len(members) > 100000:
        raise FilesystemError("archive inventory invalid")
    seen: set[str] = set()
    total_size = 0
    files = []
    for member in members:
        name = member.name
        parts = name.split("/")
        if (not member.isfile() or len(parts) < 2 or parts[0] != "payload"
                or any(x in ("", ".", "..") for x in parts) or "\\" in name
                or "\x00" in name or name in seen or member.size < 0):
            raise FilesystemError("archive unsafe member")
        total_size += member.size
        if member.size > 4 * 1024 ** 3 or total_size > 64 * 1024 ** 3:
            raise FilesystemError("archive size limit exceeded")
        seen.add(name)
        files.append(member)
    return files


def _scan_archive(path: Path, destination: Path | None = None) -> int:
    count = 0
    with tarfile.open(path, "r:gz") as archive:
        members = _safe_members(archive)
        for member in members:
            stream = archive.extractfile(member)
            if stream is None:
                raise FilesystemError("archive missing file stream")
            output = None
            if destination is not None:
                target = destination.joinpath(*member.name.split("/")[1:])
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if target.exists() or target.is_symlink():
                    raise FilesystemError("restore destination collision")
                output = target.open("xb")
                target.chmod(0o600)
            try:
                with stream:
                    digest = hashlib.sha256()
                    size = 0
                    while True:
                        chunk = stream.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        size += len(chunk)
                        if output is not None:
                            output.write(chunk)
                    if size != member.size:
                        raise FilesystemError("archive size mismatch")
                if output is not None:
                    output.flush()
                    os.fsync(output.fileno())
                    output.close()
                    output = None
                    if _hash(target) != digest.hexdigest():
                        raise FilesystemError("restore content mismatch")
                count += 1
            finally:
                if output is not None:
                    output.close()
    return count


def _hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


class FilesystemAdapter:
    name = "filesystem"

    @staticmethod
    def run_prechecks(config: dict, report) -> None:
        source_value = deep_get(config["policy"], "resource.source_dir")
        try:
            if not isinstance(source_value, str):
                raise FilesystemError("resource.source_dir required")
            source = Path(source_value)
            output = Path(deep_get(config["policy"], "artifact.output_dir")).resolve()
            _ensure_source(source, output)
            files = _inventory(source)
            report.add(CheckResult("adapter.filesystem.source", "OK", "blocking",
                                   "Regular source inventory checked", {"files": len(files)}))
        except (FilesystemError, OSError) as exc:
            report.add(CheckResult("adapter.filesystem.source", "ERROR", "blocking", str(exc)))

    @staticmethod
    def run_backup(config: dict, report):
        FilesystemAdapter.run_prechecks(config, report)
        if report.has_errors():
            return None
        source = Path(deep_get(config["policy"], "resource.source_dir"))
        output = Path(deep_get(config["policy"], "artifact.output_dir"))
        target = output / build_backup_basename(
            report.project, report.resource, utc_timestamp_slug()).replace(".sql.gz", ".tar.gz")
        temporary: Path | None = None
        published = False
        try:
            inventory = _inventory(source)
            if target.exists() or target.is_symlink():
                raise FilesystemError("backup artifact already exists")
            with tempfile.NamedTemporaryFile(prefix=".backupkit-fs-", suffix=".partial",
                                             dir=output, delete=False) as handle:
                temporary = Path(handle.name)
                os.fchmod(handle.fileno(), 0o600)
            _make_archive(source, temporary, inventory)
            _scan_archive(temporary)
            publish_new_file(temporary, target, mode=0o600)
            published = True
            temporary = None
            metadata = build_artifact_metadata(
                artifact_path=target, engine=FilesystemAdapter.name,
                project=report.project, resource=report.resource,
                started_at=report.started_at, finished_at=datetime.now(timezone.utc),
                status="OK",
            )
            write_artifact_metadata(metadata)
            report.set_artifact(metadata)
            report.add(CheckResult("adapter.filesystem.backup", "OK", "blocking",
                                   "Filesystem archive verified", {"files": len(inventory)}))
            return metadata
        except (OSError, ValueError, tarfile.TarError) as exc:
            if published:
                target.unlink(missing_ok=True)
                target.with_suffix(target.suffix + ".metadata.json").unlink(missing_ok=True)
            report.add(CheckResult("adapter.filesystem.backup", "ERROR", "blocking",
                                   "Filesystem snapshot failed: " + type(exc).__name__))
            return None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def run_verify_artifact(config: dict, report):
        result = ArtifactVerifier.verify(config, report, expected_engine=FilesystemAdapter.name)
        if report.has_errors() or result.artifact_path is None:
            return None
        try:
            count = _scan_archive(result.artifact_path)
            report.add(CheckResult("adapter.filesystem.archive", "OK", "blocking",
                                   "Safe archive contents verified", {"files": count}))
        except (OSError, ValueError, tarfile.TarError) as exc:
            report.add(CheckResult("adapter.filesystem.archive", "ERROR", "blocking",
                                   "Archive content invalid: " + type(exc).__name__))
        return result

    @staticmethod
    def run_restore_test(config: dict, report):
        verification = FilesystemAdapter.run_verify_artifact(config, report)
        if report.has_errors() or verification is None:
            return None
        output = Path(deep_get(config["policy"], "artifact.output_dir"))
        try:
            with tempfile.TemporaryDirectory(prefix=".backupkit-restore-", dir=output) as tmp:
                work = Path(tmp)
                work.chmod(0o700)
                restored = _scan_archive(verification.artifact_path, destination=work)
            report.set_restore_test({"mode": "temporary_filesystem",
                                     "files": restored, "cleanup_attempted": True,
                                     "cleanup_succeeded": True})
            report.add(CheckResult("adapter.filesystem.restore", "OK", "blocking",
                                   "Contents restored and verified in disposable directory",
                                   {"files": restored}))
        except (OSError, ValueError, tarfile.TarError) as exc:
            report.set_restore_test({"mode": "temporary_filesystem",
                                     "cleanup_attempted": True,
                                     "cleanup_succeeded": False})
            report.add(CheckResult("adapter.filesystem.restore", "ERROR", "blocking",
                                   "Temporary restore failed: " + type(exc).__name__))
        return None
