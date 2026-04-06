from __future__ import annotations

import argparse
import json
from pathlib import Path

from adapters import ADAPTERS
from core.config import load_config, deep_get
from core.notifier import NotificationService
from core.precheck import validate_required_config, validate_output_dir, validate_free_space, validate_tools, acquire_lock
from core.result import RunReport, CheckResult
from core.retention import run_housekeeping


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


def write_report(report: RunReport, output_dir: str):
    report.finalize()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    
    # Primary timestamped report
    safe_project = ''.join(ch if ch.isalnum() or ch in {'-', '_'} else '-' for ch in report.project).strip('-') or 'project'
    safe_resource = ''.join(ch if ch.isalnum() or ch in {'-', '_'} else '-' for ch in report.resource).strip('-') or 'resource'
    report_filename = f"{safe_project}__{safe_resource}__{report.timestamp_slug}__{report.command}-report.json"
    report_path = out / report_filename
    report_path.write_text(json.dumps(report.as_dict(), indent=2, ensure_ascii=False), encoding='utf-8')
    
    # Latest report link (overwritten)
    latest_report_path = out / f'{report.command}-report.json'
    latest_report_path.write_text(json.dumps(report.as_dict(), indent=2, ensure_ascii=False), encoding='utf-8')
    
    return latest_report_path


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
    # Run housekeeping phase if enabled
    try:
        hk_result = run_housekeeping(config, report)
        if hk_result:
            report.set_housekeeping(hk_result)
            status = hk_result.get('status', 'OK')
            deleted = hk_result.get('summary', {}).get('deleted_count', 0)
            kept = hk_result.get('summary', {}).get('kept_count', 0)
            protected = hk_result.get('summary', {}).get('protected_count', 0)
            report.add(CheckResult(
                'core.retention.housekeeping',
                status,
                'warning' if status == 'WARN' else 'info',
                f"Housekeeping {status}: deleted={deleted}, kept={kept}, protected={protected}"
            ))
    except Exception as exc:
        report.add(CheckResult('core.retention.error', 'WARN', 'warning', f'Housekeeping failed: {exc}'))

    report_path = write_report(report, output_dir)
    try:
        service = NotificationService(config)
        for res in service.notify(report):
            report.add(CheckResult(f'notify.{res.channel}', res.status, res.severity, res.note))
            report.add_notification(res.channel, res.status, res.note)
        report_path = write_report(report, output_dir)
    except Exception as exc:
        message = f'notifications service failed: {exc}'
        report.add(CheckResult('notify.error', 'WARN', 'warning', message))
        report.add_notification('system', 'WARN', message)
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
