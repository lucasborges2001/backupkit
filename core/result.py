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
        self.report_version = 2
        self.project = project
        self.resource = resource
        self.resource_type = resource_type
        self.command = command
        self.phase = phase or command
        self.started_at = datetime.now(timezone.utc)
        self.finished_at: datetime | None = None
        self.checks: list[CheckResult] = []
        self.artifact: ArtifactMetadata | None = None
        self.restore_test: dict | None = None
        self.notifications: list[dict] = []

    def add(self, result: CheckResult):
        self.checks.append(result)

    def set_artifact(self, artifact: ArtifactMetadata):
        self.artifact = artifact

    def set_restore_test(self, data: dict):
        self.restore_test = data

    def add_notification(self, channel: str, status: str, message: str, meta: dict | None = None):
        self.notifications.append({
            "channel": channel,
            "status": status,
            "message": message,
            "meta": meta or {},
        })

    def finalize(self):
        if self.finished_at is None:
            self.finished_at = datetime.now(timezone.utc)

    @property
    def duration_sec(self) -> float:
        end = self.finished_at or datetime.now(timezone.utc)
        return round((end - self.started_at).total_seconds(), 3)

    @property
    def duration_ms(self) -> int:
        return int(round(self.duration_sec * 1000))

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

    def _artifact_list(self) -> list[dict]:
        return [self.artifact.as_dict()] if self.artifact else []

    def _validator_list(self) -> list[dict]:
        if not self.restore_test:
            return []
        return list(self.restore_test.get('validator_results', []) or [])

    def _notifications_list(self) -> list[dict]:
        return list(self.notifications)

    def _summary_human(self) -> str:
        counts = self.summary
        parts = [
            f"Pipeline {self.command} finalizó con estado {self.status}",
            f"checks total={counts['total']}",
            f"ok={counts['OK']}",
            f"warn={counts['WARN']}",
            f"error={counts['ERROR']}",
        ]
        if self.artifact:
            parts.append(f"artifact={Path(self.artifact.path).name}")
        if self.restore_test:
            parts.append(f"restore_db={self.restore_test.get('database')}")
            if 'cleanup_succeeded' in self.restore_test:
                parts.append(f"cleanup={'ok' if self.restore_test.get('cleanup_succeeded') else 'failed'}")
        validators = self._validator_list()
        if validators:
            warn = sum(1 for item in validators if item.get('status') == 'WARN')
            error = sum(1 for item in validators if item.get('status') == 'ERROR')
            parts.append(f"validators total={len(validators)} warn={warn} error={error}")
        notifications = self._notifications_list()
        if notifications:
            parts.append(f"notifications={len(notifications)}")
        return '; '.join(parts)

    def _phase_payload(self) -> dict:
        counts = self.summary
        phase_summary = {
            'human': self._summary_human(),
            'counts': {
                'ok': counts['OK'],
                'warn': counts['WARN'],
                'error': counts['ERROR'],
                'total': counts['total'],
            },
        }
        evidence = {
            'checks': [c.as_dict() for c in self.checks],
        }
        if self.artifact:
            evidence['artifacts'] = self._artifact_list()
        if self.restore_test is not None:
            evidence['restore_test'] = self.restore_test
        validators = self._validator_list()
        if validators:
            evidence['validators'] = validators
        notifications = self._notifications_list()
        if notifications:
            evidence['notifications'] = notifications
        return {
            'id': self.phase,
            'status': self.status,
            'started_at': self.started_at.isoformat(),
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'duration_ms': self.duration_ms,
            'summary': phase_summary,
            'evidence': evidence,
        }

    def as_dict(self):
        self.finalize()
        counts = self.summary
        phase = self._phase_payload()
        artifacts = self._artifact_list()
        validators = self._validator_list()
        notifications = self._notifications_list()
        data = {
            'report_version': self.report_version,
            'project': self.project,
            'resource': self.resource,
            'resource_type': self.resource_type,
            'command': self.command,
            'phase': self.phase,
            'started_at': self.started_at.isoformat(),
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'duration_sec': self.duration_sec,
            'status': self.status,
            'summary': counts,
            'checks': [c.as_dict() for c in self.checks],
            'metadata': {
                'project': self.project,
                'resource': self.resource,
                'resource_type': self.resource_type,
                'command': self.command,
                'started_at': self.started_at.isoformat(),
                'finished_at': self.finished_at.isoformat() if self.finished_at else None,
                'duration_ms': self.duration_ms,
            },
            'final_status': self.status,
            'phases': [phase],
            'artifacts': artifacts,
            'validators': validators,
            'notifications': notifications,
            'final_summary': self._summary_human(),
        }
        if self.artifact:
            data['artifact'] = self.artifact.as_dict()
        if self.restore_test is not None:
            data['restore_test'] = self.restore_test
        return data
