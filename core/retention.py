from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from core.artifact import _parse_metadata, sha256_file
from core.backup import build_backup_basename
from core.result import ArtifactMetadata

logger = logging.getLogger(__name__)


def _safe_prefix(project: str, resource: str) -> str:
    marker = 'TIMESTAMP'
    probe = build_backup_basename(project, resource, marker)
    return probe[:probe.index(marker)]


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@dataclass
class RetentionPolicy:
    enabled: bool = False
    keep_success: int = 7
    keep_non_success: int = 5
    minimum_age_days: int = 0
    delete_artifacts: bool = True
    delete_reports: bool = True
    require_verified_newer_backup: bool = True
    protect_last_known_valid: bool = True
    dry_run: bool = True

    @classmethod
    def from_config(cls, config: dict) -> 'RetentionPolicy':
        ret = config.get('retention', {})
        if not ret:
            return cls()

        def non_negative_int(name: str, default: int) -> int:
            try:
                value = int(ret.get(name, default))
            except (TypeError, ValueError) as exc:
                raise ValueError(f'retention.{name} must be a non-negative integer') from exc
            if value < 0:
                raise ValueError(f'retention.{name} must be a non-negative integer')
            return value

        return cls(
            enabled=bool(ret.get('enabled', False)),
            keep_success=non_negative_int('keep_success', 7),
            keep_non_success=non_negative_int('keep_non_success', 5),
            minimum_age_days=non_negative_int('minimum_age_days', 0),
            delete_artifacts=bool(ret.get('delete_artifacts', True)),
            delete_reports=bool(ret.get('delete_reports', True)),
            require_verified_newer_backup=bool(ret.get('require_verified_newer_backup', True)),
            protect_last_known_valid=bool(ret.get('protect_last_known_valid', True)),
            dry_run=bool(ret.get('dry_run', True)),
        )


@dataclass
class LogicalRun:
    timestamp: str
    project: str
    resource: str
    timestamp_dt: datetime | None = None
    metadata: ArtifactMetadata | None = None
    metadata_path: Path | None = None
    artifact_path: Path | None = None
    report_path: Path | None = None
    files: list[Path] = field(default_factory=list)
    status: str = 'UNKNOWN'
    is_valid_backup: bool = False
    safety_issues: list[str] = field(default_factory=list)


@dataclass
class HousekeepingDecision:
    run: LogicalRun
    action: str
    reason: str
    files_to_delete: list[Path] = field(default_factory=list)


class RetentionManager:
    def __init__(self, policy: RetentionPolicy):
        self.policy = policy

    def discover_runs(self, output_dir: Path, project: str, resource: str) -> list[LogicalRun]:
        if not output_dir.exists():
            return []

        output_dir = output_dir.expanduser().resolve()
        prefix = _safe_prefix(project, resource)
        runs: dict[str, LogicalRun] = {}

        def get_run(timestamp: str) -> LogicalRun:
            run = runs.get(timestamp)
            if run is None:
                run = LogicalRun(
                    timestamp=timestamp,
                    project=project,
                    resource=resource,
                    timestamp_dt=_parse_timestamp(timestamp),
                )
                if run.timestamp_dt is None:
                    run.safety_issues.append('invalid timestamp')
                elif run.timestamp_dt > datetime.now(timezone.utc):
                    run.safety_issues.append('future timestamp')
                runs[timestamp] = run
            return run

        for artifact in output_dir.glob(f'{prefix}*.sql.gz'):
            rest = artifact.name[len(prefix):]
            if not rest.endswith('.sql.gz'):
                continue
            timestamp = rest[:-len('.sql.gz')]
            run = get_run(timestamp)
            run.artifact_path = artifact
            run.files.append(artifact)

        for metadata_path in output_dir.glob(f'{prefix}*.sql.gz.metadata.json'):
            rest = metadata_path.name[len(prefix):]
            timestamp = rest[:-len('.sql.gz.metadata.json')]
            run = get_run(timestamp)
            run.metadata_path = metadata_path
            if metadata_path not in run.files:
                run.files.append(metadata_path)
            if metadata_path.is_symlink():
                run.safety_issues.append('metadata symlink')
                continue
            try:
                raw = json.loads(metadata_path.read_text(encoding='utf-8'))
                run.metadata = _parse_metadata(raw, metadata_path)
                run.status = run.metadata.status
            except Exception as exc:
                run.safety_issues.append(f'metadata missing/corrupt: {exc}')

        for report_path in output_dir.glob(f'{prefix}*__backup-report.json'):
            rest = report_path.name[len(prefix):]
            timestamp = rest[:-len('__backup-report.json')]
            run = get_run(timestamp)
            run.report_path = report_path
            if report_path not in run.files:
                run.files.append(report_path)

        for run in runs.values():
            self._verify_run(run, output_dir)

        return sorted(runs.values(), key=lambda item: item.timestamp, reverse=True)

    def _verify_run(self, run: LogicalRun, output_dir: Path) -> None:
        if run.metadata is None:
            return

        expected_artifact = output_dir / build_backup_basename(run.project, run.resource, run.timestamp)
        expected_metadata = expected_artifact.with_suffix(expected_artifact.suffix + '.metadata.json')
        run.artifact_path = run.artifact_path or expected_artifact
        run.metadata_path = run.metadata_path or expected_metadata

        artifact = run.artifact_path
        metadata_path = run.metadata_path
        if artifact.is_symlink():
            run.safety_issues.append('artifact symlink')
        if metadata_path.is_symlink():
            run.safety_issues.append('metadata symlink')
        if not artifact.is_file():
            run.safety_issues.append('artifact missing')
        if not metadata_path.is_file():
            run.safety_issues.append('metadata missing')

        metadata = run.metadata
        if metadata.project != run.project:
            run.safety_issues.append('metadata project mismatch')
        if metadata.resource != run.resource:
            run.safety_issues.append('metadata resource mismatch')
        # A non-OK backup is not recoverable evidence, but its artifact can still be
        # integrity-verified and safely considered by keep_non_success housekeeping.
        if metadata.path != str(expected_artifact.resolve()):
            run.safety_issues.append('metadata artifact path mismatch')
        if metadata.metadata_path and metadata.metadata_path != str(expected_metadata.resolve()):
            run.safety_issues.append('metadata sidecar path mismatch')

        if artifact.is_file() and not artifact.is_symlink():
            actual_size = artifact.stat().st_size
            if metadata.size_bytes != actual_size:
                run.safety_issues.append('artifact size mismatch')
            if not metadata.sha256:
                run.safety_issues.append('artifact sha256 missing')
            elif sha256_file(artifact) != metadata.sha256:
                run.safety_issues.append('artifact sha256 mismatch')

        run.is_valid_backup = not run.safety_issues and metadata.status == 'OK'

    def decide(self, runs: list[LogicalRun]) -> list[HousekeepingDecision]:
        decisions: list[HousekeepingDecision] = []
        success_count = 0
        non_success_count = 0
        last_valid_protected = False
        verified_newer_exists = False

        for run in runs:
            if self.policy.protect_last_known_valid and not last_valid_protected and run.is_valid_backup:
                decisions.append(HousekeepingDecision(run, 'PROTECT', 'Newest verified valid backup'))
                last_valid_protected = True
                success_count += 1
                verified_newer_exists = True
                continue

            if run.is_valid_backup:
                if success_count < self.policy.keep_success:
                    decisions.append(HousekeepingDecision(run, 'KEEP', f'Within keep_success limit ({success_count + 1}/{self.policy.keep_success})'))
                    success_count += 1
                else:
                    decisions.append(self._evaluate_deletion(run, 'Success limit exceeded', verified_newer_exists=verified_newer_exists))
                verified_newer_exists = True
            else:
                if non_success_count < self.policy.keep_non_success:
                    decisions.append(HousekeepingDecision(run, 'KEEP', f'Within keep_non_success limit ({non_success_count + 1}/{self.policy.keep_non_success})'))
                    non_success_count += 1
                else:
                    decisions.append(self._evaluate_deletion(run, 'Non-success limit exceeded', verified_newer_exists=verified_newer_exists))
        return decisions

    def _evaluate_deletion(self, run: LogicalRun, limit_reason: str, *, verified_newer_exists: bool) -> HousekeepingDecision:
        if run.metadata is None:
            return HousekeepingDecision(run, 'KEEP', f'{limit_reason}, but metadata missing/corrupt (safety skip)')
        if run.safety_issues:
            return HousekeepingDecision(run, 'KEEP', f'{limit_reason}, but verification failed: {"; ".join(run.safety_issues)}')
        if self.policy.require_verified_newer_backup and not verified_newer_exists:
            return HousekeepingDecision(run, 'KEEP', f'{limit_reason}, but no newer verified backup exists')
        if run.timestamp_dt is None:
            return HousekeepingDecision(run, 'KEEP', f'{limit_reason}, but timestamp is invalid')
        if self.policy.minimum_age_days:
            age = datetime.now(timezone.utc) - run.timestamp_dt
            if age < timedelta(days=self.policy.minimum_age_days):
                return HousekeepingDecision(run, 'KEEP', f'{limit_reason}, but younger than minimum_age_days={self.policy.minimum_age_days}')

        files_to_delete: list[Path] = []
        if self.policy.delete_artifacts:
            if run.artifact_path and run.artifact_path.exists():
                files_to_delete.append(run.artifact_path)
            if run.metadata_path and run.metadata_path.exists():
                files_to_delete.append(run.metadata_path)
        if self.policy.delete_reports and run.report_path and run.report_path.exists():
            files_to_delete.append(run.report_path)
        return HousekeepingDecision(run, 'DELETE', limit_reason, files_to_delete)

    @staticmethod
    def _delete_safety_error(run: LogicalRun) -> str | None:
        if run.metadata is None:
            return 'metadata is missing'
        if run.safety_issues:
            return 'run integrity verification no longer passes'
        artifact = run.artifact_path
        metadata_path = run.metadata_path
        if artifact is None or metadata_path is None:
            return 'artifact or metadata path missing'
        if artifact.is_symlink() or metadata_path.is_symlink():
            return 'symlink detected before deletion'
        if not artifact.is_file() or not metadata_path.is_file():
            return 'artifact or metadata missing before deletion'
        if artifact.stat().st_size != run.metadata.size_bytes:
            return 'artifact size changed before deletion'
        if sha256_file(artifact) != run.metadata.sha256:
            return 'artifact sha256 changed before deletion'
        return None

    def execute(self, decisions: list[HousekeepingDecision]) -> dict[str, Any]:
        result = {'deleted': [], 'kept': [], 'protected': [], 'failed_deletions': [], 'skipped_deletions': []}
        for decision in decisions:
            if decision.action == 'PROTECT':
                result['protected'].append({'timestamp': decision.run.timestamp, 'reason': decision.reason, 'files': [p.name for p in decision.run.files]})
                continue
            if decision.action == 'KEEP':
                result['kept'].append({'timestamp': decision.run.timestamp, 'reason': decision.reason, 'files': [p.name for p in decision.run.files]})
                continue
            if decision.action != 'DELETE':
                continue
            if self.policy.dry_run:
                result['skipped_deletions'].append({'timestamp': decision.run.timestamp, 'reason': f'{decision.reason} (DRY RUN)', 'files': [p.name for p in decision.files_to_delete]})
                continue

            safety_error = self._delete_safety_error(decision.run)
            if safety_error:
                result['failed_deletions'].append({'timestamp': decision.run.timestamp, 'failed_files': [], 'deleted_files': [], 'error': safety_error})
                continue

            deleted_files: list[str] = []
            failed_files: list[dict[str, str]] = []
            for path in decision.files_to_delete:
                try:
                    if path.is_symlink():
                        raise RuntimeError('symlink detected before unlink')
                    if path.exists():
                        path.unlink()
                        deleted_files.append(path.name)
                except Exception as exc:
                    failed_files.append({'file': path.name, 'error': str(exc)})
            if failed_files:
                result['failed_deletions'].append({'timestamp': decision.run.timestamp, 'failed_files': failed_files, 'deleted_files': deleted_files})
            result['deleted'].append({'timestamp': decision.run.timestamp, 'reason': decision.reason, 'files': deleted_files})
        return result


def run_housekeeping(config: dict, report: Any):
    policy = RetentionPolicy.from_config(config['policy'])
    if not policy.enabled:
        return None
    output_dir = Path(config['policy']['artifact']['output_dir'])
    manager = RetentionManager(policy)
    runs = manager.discover_runs(output_dir, report.project, report.resource)
    decisions = manager.decide(runs)
    execution_result = manager.execute(decisions)
    hk_report = {
        'status': 'OK',
        'policy': {
            'keep_success': policy.keep_success,
            'keep_non_success': policy.keep_non_success,
            'minimum_age_days': policy.minimum_age_days,
            'delete_artifacts': policy.delete_artifacts,
            'delete_reports': policy.delete_reports,
            'require_verified_newer_backup': policy.require_verified_newer_backup,
            'protect_last_known_valid': policy.protect_last_known_valid,
            'dry_run': policy.dry_run,
        },
        'summary': {
            'discovered_count': len(runs),
            'kept_count': len(execution_result['kept']),
            'protected_count': len(execution_result['protected']),
            'deleted_count': len(execution_result['deleted']),
            'failed_count': len(execution_result['failed_deletions']),
            'skipped_count': len(execution_result['skipped_deletions']),
        },
        'discovered_runs': [
            {'timestamp': run.timestamp, 'status': run.status, 'verified': run.is_valid_backup, 'safety_issues': run.safety_issues, 'files_count': len(run.files)}
            for run in runs
        ],
        'kept_runs': execution_result['kept'],
        'protected_runs': execution_result['protected'],
        'deleted_runs': execution_result['deleted'],
        'skipped_deletions': execution_result['skipped_deletions'],
    }
    if execution_result['failed_deletions']:
        hk_report['status'] = 'WARN'
        hk_report['failed_deletions'] = execution_result['failed_deletions']
    return hk_report
