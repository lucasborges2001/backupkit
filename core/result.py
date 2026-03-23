from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


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


class RunReport:
    def __init__(self, project: str, resource: str, command: str):
        self.project = project
        self.resource = resource
        self.command = command
        self.started_at = datetime.now(timezone.utc)
        self.checks: list[CheckResult] = []

    def add(self, result: CheckResult):
        self.checks.append(result)

    @property
    def status(self) -> str:
        if any(c.status == 'ERROR' for c in self.checks):
            return 'ERROR'
        if any(c.status == 'WARN' for c in self.checks):
            return 'WARN'
        return 'OK'

    def as_dict(self):
        return {
            "project": self.project,
            "resource": self.resource,
            "command": self.command,
            "started_at": self.started_at.isoformat(),
            "status": self.status,
            "checks": [c.as_dict() for c in self.checks],
        }
