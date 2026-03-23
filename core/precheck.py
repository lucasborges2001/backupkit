from __future__ import annotations

import json
import shutil
import socket
import tempfile
from pathlib import Path

from core.config import deep_get
from core.lock import FileLock
from core.result import CheckResult, RunReport
from core.tools import resolve_tool


def required_paths_for_resource(resource_type: str):
    base = [
        "project.name",
        "resource.name",
        "resource.type",
        "artifact.output_dir",
        "prechecks.require_free_space_mb",
    ]
    if resource_type == "mysql":
        base += [
            "resource.connection.host",
            "resource.connection.port",
            "resource.connection.database",
            "resource.connection.username",
        ]
    return base


def validate_required_config(config: dict, report: RunReport):
    policy = config["policy"]
    resource_type = deep_get(policy, "resource.type")
    missing = [path for path in required_paths_for_resource(resource_type) if deep_get(policy, path) in (None, "")]
    if missing:
        report.add(CheckResult("core.config.required", "ERROR", "blocking", f"Missing required policy fields: {', '.join(missing)}"))
    else:
        report.add(CheckResult("core.config.required", "OK", "blocking", "Required policy fields present"))


def validate_output_dir(config: dict, report: RunReport):
    out_dir = Path(deep_get(config["policy"], "artifact.output_dir"))
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=out_dir, delete=True) as _:
            pass
        report.add(CheckResult("core.output_dir.writable", "OK", "blocking", f"Output dir writable: {out_dir}"))
    except Exception as exc:
        report.add(CheckResult("core.output_dir.writable", "ERROR", "blocking", f"Output dir not writable: {exc}"))


def validate_free_space(config: dict, report: RunReport):
    out_dir = Path(deep_get(config["policy"], "artifact.output_dir"))
    required_mb = int(deep_get(config["policy"], "prechecks.require_free_space_mb", 0) or 0)
    warn_below = int(deep_get(config["policy"], "prechecks.warn_free_space_below_mb", 0) or 0)
    usage = shutil.disk_usage(out_dir)
    free_mb = usage.free // (1024 * 1024)
    if free_mb < required_mb:
        report.add(CheckResult("core.free_space", "ERROR", "blocking", f"Free space {free_mb} MB below required {required_mb} MB", {"free_mb": free_mb}))
    elif warn_below and free_mb < warn_below:
        report.add(CheckResult("core.free_space", "WARN", "warning", f"Free space low: {free_mb} MB", {"free_mb": free_mb}))
    else:
        report.add(CheckResult("core.free_space", "OK", "blocking", f"Free space OK: {free_mb} MB", {"free_mb": free_mb}))


def validate_tools(config: dict, report: RunReport):
    tool_ids = deep_get(config["policy"], "prechecks.require_tools", []) or []
    missing = []
    resolved = {}
    for tool_id in tool_ids:
        path = resolve_tool(tool_id)
        if not path:
            missing.append(tool_id)
        else:
            resolved[tool_id] = path
    if missing:
        report.add(CheckResult("core.tools.available", "ERROR", "blocking", f"Missing required tools: {', '.join(missing)}"))
    else:
        report.add(CheckResult("core.tools.available", "OK", "blocking", "Required tools available", resolved))


def acquire_lock(config: dict, report: RunReport):
    lock_dir = Path(deep_get(config["policy"], "runtime.lock_dir", ".backupkit/locks"))
    lock_name = f"{deep_get(config['policy'], 'project.name', 'project')}-{deep_get(config['policy'], 'resource.name', 'resource')}.lock"
    lock = FileLock(lock_dir / lock_name)
    try:
        lock.acquire()
        report.add(CheckResult("core.lock.available", "OK", "blocking", f"Lock acquired: {lock.path}"))
        return lock
    except FileExistsError:
        report.add(CheckResult("core.lock.available", "ERROR", "blocking", f"Lock already exists: {lock.path}"))
        return None
    except Exception as exc:
        report.add(CheckResult("core.lock.available", "ERROR", "blocking", f"Lock failure: {exc}"))
        return None


def tcp_connectivity(host: str, port: int, timeout: int):
    with socket.create_connection((host, port), timeout=timeout):
        return True
