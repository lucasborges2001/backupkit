from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class CheckResult:
    check_id: str
    status: str
    severity: str
    message: str
    meta: dict = field(default_factory=dict)

    def as_dict(self):
        return {
            "id": self.check_id,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
            "meta": self.meta,
        }


@dataclass
class ArtifactMetadata:
    path: str
    size_bytes: int
    sha256: str
    timestamp: str
    engine: str
    resource: str
    project: str
    duration_sec: float
    status: str
    metadata_path: str | None = None

    @classmethod
    def from_values(
        cls,
        *,
        path: str | Path,
        size_bytes: int,
        sha256: str,
        timestamp: str,
        engine: str,
        resource: str,
        project: str,
        duration_sec: float,
        status: str,
        metadata_path: str | Path | None = None,
    ) -> "ArtifactMetadata":
        return cls(
            path=str(path),
            size_bytes=int(size_bytes),
            sha256=sha256,
            timestamp=timestamp,
            engine=engine,
            resource=resource,
            project=project,
            duration_sec=float(duration_sec),
            status=status,
            metadata_path=str(metadata_path) if metadata_path else None,
        )

    def as_dict(self):
        data = {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "timestamp": self.timestamp,
            "engine": self.engine,
            "resource": self.resource,
            "project": self.project,
            "duration_sec": self.duration_sec,
            "status": self.status,
        }
        if self.metadata_path:
            data["metadata_path"] = self.metadata_path
        return data


class RunReport:
    def __init__(self, project: str, resource: str, command: str, resource_type: str | None = None, phase: str | None = None):
        self.report_version = 1
        self.project = project
        self.resource = resource
        self.resource_type = resource_type
        self.command = command
        self.phase = phase or command
        self.started_at = datetime.now(timezone.utc)
        self.finished_at: datetime | None = None
        self.checks: list[CheckResult] = []
        self.artifact: ArtifactMetadata | None = None

    def add(self, result: CheckResult):
        self.checks.append(result)

    def set_artifact(self, artifact: ArtifactMetadata):
        self.artifact = artifact

    def finalize(self):
        if self.finished_at is None:
            self.finished_at = datetime.now(timezone.utc)

    @property
    def duration_sec(self) -> float:
        end = self.finished_at or datetime.now(timezone.utc)
        return round((end - self.started_at).total_seconds(), 3)

    @property
    def status(self) -> str:
        if any(c.status == 'ERROR' for c in self.checks):
            return 'ERROR'
        if any(c.status == 'WARN' for c in self.checks):
            return 'WARN'
        return 'OK'

    @property
    def summary(self) -> dict:
        counts = {"OK": 0, "WARN": 0, "ERROR": 0}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        counts["total"] = len(self.checks)
        return counts

    def has_errors(self) -> bool:
        return any(c.status == 'ERROR' for c in self.checks)

    def as_dict(self):
        self.finalize()
        data = {
            "report_version": self.report_version,
            "project": self.project,
            "resource": self.resource,
            "resource_type": self.resource_type,
            "command": self.command,
            "phase": self.phase,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_sec": self.duration_sec,
            "status": self.status,
            "summary": self.summary,
            "checks": [c.as_dict() for c in self.checks],
        }
        if self.artifact:
            data["artifact"] = self.artifact.as_dict()
        return data
