from __future__ import annotations

import argparse
import json
from pathlib import Path

from adapters import ADAPTERS
from core.config import load_config, deep_get
from core.notifier import notify_telegram
from core.precheck import validate_required_config, validate_output_dir, validate_free_space, validate_tools, acquire_lock
from core.result import RunReport, CheckResult


def format_console(report: RunReport) -> str:
    lines = [f"backupkit precheck => {report.status}", f"project={report.project}", f"resource={report.resource}"]
    for c in report.checks:
        lines.append(f"[{c.status}] {c.check_id}: {c.message}")
    return "\n".join(lines)


def format_telegram(report: RunReport) -> str:
    failing = [c for c in report.checks if c.status in {'WARN', 'ERROR'}]
    lines = [
        f"[backupkit] PRECHECK {report.status}",
        f"Proyecto: {report.project}",
        f"Recurso: {report.resource}",
    ]
    if failing:
        lines.append("")
        lines.append("Checks:")
        for c in failing:
            lines.append(f"- {c.check_id}: {c.message}")
    return "\n".join(lines)


def write_report(report: RunReport, output_dir: str):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / 'precheck-report.json'
    report_path.write_text(json.dumps(report.as_dict(), indent=2, ensure_ascii=False), encoding='utf-8')
    return report_path


def maybe_notify(config: dict, report: RunReport):
    notify_on = set(deep_get(config['policy'], 'notifications.telegram.notify_on', []) or [])
    enabled = bool(deep_get(config['policy'], 'notifications.telegram.enabled', False))
    env = config['env']
    token = env.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = env.get('TELEGRAM_CHAT_ID', '')
    if report.status == 'OK':
        return None
    if not enabled:
        return None
    if report.status not in notify_on:
        return None
    if not token or not chat_id:
        return 'telegram disabled: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID'
    notify_telegram(token, chat_id, format_telegram(report))
    return 'telegram sent'


def run_precheck(args) -> int:
    config = load_config(args.env, args.policy)
    project = deep_get(config['policy'], 'project.name', 'unknown-project')
    resource = deep_get(config['policy'], 'resource.name', 'unknown-resource')
    report = RunReport(project=project, resource=resource, command='precheck')

    validate_required_config(config, report)
    if report.status == 'ERROR':
        out_dir = deep_get(config['policy'], 'artifact.output_dir', '.backupkit/out')
        write_report(report, out_dir)
        print(format_console(report))
        return 2

    lock = acquire_lock(config, report)
    try:
        validate_output_dir(config, report)
        validate_free_space(config, report)
        validate_tools(config, report)

        resource_type = deep_get(config['policy'], 'resource.type')
        adapter_cls = ADAPTERS.get(resource_type)
        if not adapter_cls:
            report.add(CheckResult('core.adapter.supported', 'ERROR', 'blocking', f'Unsupported adapter: {resource_type}'))
        else:
            adapter_cls.run_prechecks(config, report)

        report_path = write_report(report, deep_get(config['policy'], 'artifact.output_dir'))
        note = None
        try:
            note = maybe_notify(config, report)
            if note:
                report.add(CheckResult('notify.telegram', 'WARN' if 'missing' in note else 'OK', 'warning', note))
                report_path = write_report(report, deep_get(config['policy'], 'artifact.output_dir'))
        except Exception as exc:
            report.add(CheckResult('notify.telegram', 'WARN', 'warning', f'telegram failed: {exc}'))
            report_path = write_report(report, deep_get(config['policy'], 'artifact.output_dir'))

        print(format_console(report))
        print(f"report={report_path}")
        return 0 if report.status == 'OK' else 1 if report.status == 'WARN' else 2
    finally:
        if lock:
            lock.release()


def main() -> int:
    parser = argparse.ArgumentParser(prog='backupkit')
    sub = parser.add_subparsers(dest='command', required=True)

    p_pre = sub.add_parser('precheck', help='Run prechecks for the configured resource')
    p_pre.add_argument('--env', required=True)
    p_pre.add_argument('--policy', required=True)

    args = parser.parse_args()

    if args.command == 'precheck':
        return run_precheck(args)
    return 2
