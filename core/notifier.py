from __future__ import annotations

import json
import urllib.request
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from core.result import RunReport


@dataclass
class NotificationMessage:
    title: str
    body: str
    status: str  # OK, WARN, ERROR
    context: dict = field(default_factory=dict)


@dataclass
class NotificationResult:
    channel: str
    status: str    # OK, WARN, ERROR, SKIP, DISABLED
    severity: str  # info, warning, error
    note: str


class Notifier(ABC):
    @abstractmethod
    def notify(self, message: NotificationMessage) -> str:
        """Sends a notification using a pre-rendered message."""
        pass


class SummaryRenderer:
    @staticmethod
    def render(report: RunReport) -> NotificationMessage:
        """Generates a generic NotificationMessage from a RunReport."""
        failing = [c for c in report.checks if c.status in {'WARN', 'ERROR'}]
        lines = [
            f"Proyecto: {report.project}",
            f"Recurso: {report.resource}",
        ]
        if report.artifact:
            lines.append(f"Artefacto: {Path(report.artifact.path).name}")
        if report.restore_test:
            lines.append(f"Restore DB temporal: {report.restore_test.get('database')}")
            lines.append(f"Cleanup OK: {report.restore_test.get('cleanup_succeeded')}")
        
        if failing:
            lines.append("")
            lines.append("Checks:")
            for c in failing:
                lines.append(f"- {c.check_id}: {c.message}")
        
        return NotificationMessage(
            title=f"[backupkit] {report.command.upper()} {report.status}",
            body="\n".join(lines),
            status=report.status
        )


class TelegramNotifier(Notifier):
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    def notify(self, message: NotificationMessage) -> str:
        text = f"{message.title}\n\n{message.body}"
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = urllib.parse.urlencode({"chat_id": self.chat_id, "text": text}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                body = json.loads(response.read().decode("utf-8"))
                if not body.get("ok"):
                    raise RuntimeError(f"Telegram API error: {body}")
                return "telegram sent"
        except Exception as e:
            raise RuntimeError(f"Telegram failed: {e}")


class NotificationService:
    def __init__(self, config: dict):
        self.config = config
        self.env = config.get('env', {})
        self.policy = config.get('policy', {})

    def notify(self, report: RunReport) -> list[NotificationResult]:
        # 1. Render message (decoupled from transport)
        message = SummaryRenderer.render(report)
        
        results: list[NotificationResult] = []

        # 2. Handle Policy: OK status skip (as a system note)
        if report.status == 'OK':
            results.append(NotificationResult('system', 'SKIP', 'info', 'Status OK: notifications skipped'))
            return results

        # 3. Process Channels
        results.append(self._notify_telegram(message))
        
        return results

    def _notify_telegram(self, message: NotificationMessage) -> NotificationResult:
        cfg = self.policy.get('notifications', {}).get('telegram', {})
        enabled = cfg.get('enabled', False)
        
        if not enabled:
            return NotificationResult('telegram', 'DISABLED', 'info', 'Channel disabled in policy')
            
        token = self.env.get('TELEGRAM_BOT_TOKEN')
        chat_id = self.env.get('TELEGRAM_CHAT_ID')
        
        if not token or not chat_id:
            return NotificationResult('telegram', 'SKIP', 'warning', 'Missing credentials in env (TELEGRAM_BOT_TOKEN/CHAT_ID)')
            
        try:
            note = TelegramNotifier(token, chat_id).notify(message)
            return NotificationResult('telegram', 'OK', 'info', note)
        except Exception as e:
            return NotificationResult('telegram', 'ERROR', 'warning', str(e))


def notify_telegram(token: str, chat_id: str, text: str):
    """Deprecated: Kept for legacy compatibility if any bash script uses it via python -c."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=10) as response:
        body = json.loads(response.read().decode("utf-8"))
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API error: {body}")
        return body
