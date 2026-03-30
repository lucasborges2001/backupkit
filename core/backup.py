from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.artifact import sha256_file, write_artifact_metadata
from core.result import ArtifactMetadata


def utc_timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def build_backup_basename(project: str, resource: str, timestamp_slug: str) -> str:
    safe_project = ''.join(ch if ch.isalnum() or ch in {'-', '_'} else '-' for ch in project).strip('-') or 'project'
    safe_resource = ''.join(ch if ch.isalnum() or ch in {'-', '_'} else '-' for ch in resource).strip('-') or 'resource'
    return f"{safe_project}__{safe_resource}__{timestamp_slug}.sql.gz"



def build_artifact_metadata(*, artifact_path: str | Path, engine: str, resource: str, project: str, started_at, finished_at, status: str):
    artifact_path = Path(artifact_path)
    return ArtifactMetadata.from_values(
        path=artifact_path,
        size_bytes=artifact_path.stat().st_size,
        sha256=sha256_file(artifact_path),
        timestamp=finished_at.isoformat(),
        engine=engine,
        resource=resource,
        project=project,
        duration_sec=round((finished_at - started_at).total_seconds(), 3),
        status=status,
    )

