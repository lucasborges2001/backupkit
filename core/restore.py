from __future__ import annotations

import re
from datetime import datetime, timezone


def utc_restore_slug() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def build_restore_database_name(project: str, resource: str, prefix: str, timestamp_slug: str | None = None) -> str:
    slug = timestamp_slug or utc_restore_slug()
    safe_project = re.sub(r'[^a-zA-Z0-9_]', '_', project).strip('_') or 'project'
    safe_resource = re.sub(r'[^a-zA-Z0-9_]', '_', resource).strip('_') or 'resource'
    base = f"{prefix}_{safe_project}_{safe_resource}_{slug}".lower()
    return base[:64]
