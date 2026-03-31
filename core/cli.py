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
    lines = [f"backupkit {report.command} => {report.status}", f"project={report.project}", f"resource={report.resource}"]
    if report.artifact:
        lines.append(f"artifact={report.artifact.path}")
        lines.append(f"sha256={report.artifact.sha256}")
    if report.restore_test:
        lines.append(f"restore_db={report.restore_test.get('database')}")
        lines.append(f"cleanup={report.restore_test.get('cleanup_succeeded')}")
    for c in report.checks:
        lines.append(f"[{c.status}] {c.check_id}: {c.message}")
    return "\n".join(lines)


def format_telegram(report: RunReport) -> str:
    failing = [c for c in report.checks if c.status in {'WARN', 'ERROR'}]
    lines = [
        f"[backupkit] {report.command.upper()} {report.status}",
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
    return "\n".join(lines)


def write_report(report: RunReport, output_dir: str):
    report.finalize()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / f'{report.command}-report.json'
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


def build_report(config: dict, command: str) -> RunReport:
    return RunReport(
        project=deep_get(config['policy'], 'project.name', 'unknown-project'),
        resource=deep_get(config['policy'], 'resource.name', 'unknown-resource'),
        resource_type=deep_get(config['policy'], 'resource.type'),
        command=command,
        phase=command,
    )


def run_post_lock_validations(config: dict, report: RunReport):
    validate_output_dir(config, report)
    validate_free_space(config, report)
    validate_tools(config, report)
    return not report.has_errors()


def resolve_adapter(config: dict, report: RunReport):
    resource_type = deep_get(config['policy'], 'resource.type')
    adapter_cls = ADAPTERS.get(resource_type)
    if not adapter_cls:
        report.add(CheckResult('core.adapter.supported', 'ERROR', 'blocking', f'Unsupported adapter: {resource_type}'))
        return None
    return adapter_cls


def finish_run(config: dict, report: RunReport, output_dir: str):
    report_path = write_report(report, output_dir)
    note = None
    try:
        note = maybe_notify(config, report)
        if note:
            report.add(CheckResult('notify.telegram', 'WARN' if 'missing' in note else 'OK', 'warning', note))
            report_path = write_report(report, output_dir)
    except Exception as exc:
        report.add(CheckResult('notify.telegram', 'WARN', 'warning', f'telegram failed: {exc}'))
        report_path = write_report(report, output_dir)

    print(format_console(report))
    print(f"report={report_path}")
    return 0 if report.status == 'OK' else 1 if report.status == 'WARN' else 2


def _run_with_adapter(args, command: str, adapter_method: str) -> int:
    config = load_config(args.env, args.policy)
    report = build_report(config, command)
    output_dir = deep_get(config['policy'], 'artifact.output_dir', '.backupkit/out')

    validate_required_config(config, report, command)
    if report.has_errors():
        write_report(report, output_dir)
        print(format_console(report))
        return 2

    lock = acquire_lock(config, report)
    try:
        if report.has_errors():
            return finish_run(config, report, output_dir)
        if not run_post_lock_validations(config, report):
            return finish_run(config, report, output_dir)
        adapter_cls = resolve_adapter(config, report)
        if adapter_cls:
            getattr(adapter_cls, adapter_method)(config, report)
        return finish_run(config, report, output_dir)
    finally:
        if lock:
            lock.release()


def run_precheck(args) -> int:
    return _run_with_adapter(args, 'precheck', 'run_prechecks')


def run_backup(args) -> int:
    return _run_with_adapter(args, 'backup', 'run_backup')


def run_verify_artifact(args) -> int:
    return _run_with_adapter(args, 'verify-artifact', 'run_verify_artifact')


def run_restore_test(args) -> int:
    return _run_with_adapter(args, 'restore-test', 'run_restore_test')


def main() -> int:
    parser = argparse.ArgumentParser(prog='backupkit')
    sub = parser.add_subparsers(dest='command', required=True)

    p_pre = sub.add_parser('precheck', help='Run prechecks for the configured resource')
    p_pre.add_argument('--env', required=True)
    p_pre.add_argument('--policy', required=True)

    p_backup = sub.add_parser('backup', help='Run a backup for the configured resource')
    p_backup.add_argument('--env', required=True)
    p_backup.add_argument('--policy', required=True)

    p_verify = sub.add_parser('verify-artifact', help='Verify the generated backup artifact and metadata')
    p_verify.add_argument('--env', required=True)
    p_verify.add_argument('--policy', required=True)

    p_restore = sub.add_parser('restore-test', help='Restore the generated artifact into a temporary database and validate it')
    p_restore.add_argument('--env', required=True)
    p_restore.add_argument('--policy', required=True)

    args = parser.parse_args()

    if args.command == 'precheck':
        return run_precheck(args)
    if args.command == 'backup':
        return run_backup(args)
    if args.command == 'verify-artifact':
        return run_verify_artifact(args)
    if args.command == 'restore-test':
        return run_restore_test(args)
    return 2
