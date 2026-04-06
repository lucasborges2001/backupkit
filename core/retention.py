from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.result import ArtifactMetadata

logger = logging.getLogger(__name__)

@dataclass
class RetentionPolicy:
    enabled: bool = False
    keep_success: int = 7
    keep_non_success: int = 5
    delete_artifacts: bool = True
    delete_reports: bool = True
    require_verified_newer_backup: bool = True
    protect_last_known_valid: bool = True
    dry_run: bool = False

    @classmethod
    def from_config(cls, config: dict) -> RetentionPolicy:
        ret = config.get('retention', {})
        if not ret:
            return cls()
        return cls(
            enabled=ret.get('enabled', False),
            keep_success=ret.get('keep_success', 7),
            keep_non_success=ret.get('keep_non_success', 5),
            delete_artifacts=ret.get('delete_artifacts', True),
            delete_reports=ret.get('delete_reports', True),
            require_verified_newer_backup=ret.get('require_verified_newer_backup', True),
            protect_last_known_valid=ret.get('protect_last_known_valid', True),
            dry_run=ret.get('dry_run', False),
        )

@dataclass
class LogicalRun:
    timestamp: str
    project: str
    resource: str
    metadata: ArtifactMetadata | None = None
    files: list[Path] = field(default_factory=list)
    status: str = 'UNKNOWN'  # OK, WARN, ERROR, UNKNOWN
    is_valid_backup: bool = False

    def __post_init__(self):
        if self.metadata:
            self.status = self.metadata.status
            # A run is a valid backup if it has an artifact and metadata status is OK
            # We also check if the artifact file exists in RetentionManager
            if self.status == 'OK':
                self.is_valid_backup = True

@dataclass
class HousekeepingDecision:
    run: LogicalRun
    action: str  # KEEP, DELETE, PROTECT
    reason: str
    files_to_delete: list[Path] = field(default_factory=list)

class RetentionManager:
    def __init__(self, policy: RetentionPolicy):
        self.policy = policy

    def discover_runs(self, output_dir: Path, project: str, resource: str) -> list[LogicalRun]:
        if not output_dir.exists():
            return []

        runs_dict: dict[str, LogicalRun] = {}

        # 1. Find all metadata files first as anchors
        # Pattern: {project}__{resource}__{timestamp}.sql.gz.metadata.json
        metadata_suffix = '.metadata.json'
        for p in output_dir.glob(f"{project}__{resource}__*{metadata_suffix}"):
            # Extract timestamp from filename
            # project__resource__20260406T120000Z.sql.gz.metadata.json
            parts = p.name.split('__')
            if len(parts) < 3:
                continue
            
            # The timestamp is the part after the second __, but before the first .
            # Wait, the basename is built as: f"{safe_project}__{safe_resource}__{timestamp_slug}.sql.gz"
            # So the filename is: f"{safe_project}__{safe_resource}__{timestamp_slug}.sql.gz.metadata.json"
            ts_part = parts[2].split('.')[0]
            
            try:
                raw_meta = json.loads(p.read_text(encoding='utf-8'))
                from core.artifact import _parse_metadata
                meta = _parse_metadata(raw_meta, p)
            except Exception:
                meta = None

            if ts_part not in runs_dict:
                runs_dict[ts_part] = LogicalRun(timestamp=ts_part, project=project, resource=resource)
            
            run = runs_dict[ts_part]
            run.metadata = meta
            if meta:
                run.status = meta.status
                artifact_path = output_dir / Path(meta.path).name
                if meta.status == 'OK' and artifact_path.exists():
                    run.is_valid_backup = True

        # 2. Collect all files sharing the same prefix
        # This includes reports if they are timestamped
        for p in output_dir.glob(f"{project}__{resource}__*"):
            parts = p.name.split('__')
            if len(parts) < 3:
                continue
            ts_part = parts[2].split('.')[0]
            
            if ts_part in runs_dict:
                if p not in runs_dict[ts_part].files:
                    runs_dict[ts_part].files.append(p)
            else:
                # We found a file with the prefix but no metadata? 
                # Create a run for it anyway but it will be UNKNOWN
                runs_dict[ts_part] = LogicalRun(timestamp=ts_part, project=project, resource=resource)
                runs_dict[ts_part].files.append(p)

        # Sort by timestamp descending (newest first)
        sorted_ts = sorted(runs_dict.keys(), reverse=True)
        return [runs_dict[ts] for ts in sorted_ts]

    def decide(self, runs: list[LogicalRun]) -> list[HousekeepingDecision]:
        decisions: list[HousekeepingDecision] = []
        
        success_count = 0
        non_success_count = 0
        last_valid_protected = False

        # Runs are already sorted newest first
        for run in runs:
            # Check if it's the last known valid backup
            if self.policy.protect_last_known_valid and not last_valid_protected and run.is_valid_backup:
                decisions.append(HousekeepingDecision(
                    run=run,
                    action='PROTECT',
                    reason='Last known valid backup'
                ))
                last_valid_protected = True
                success_count += 1
                continue

            if run.status == 'OK':
                if success_count < self.policy.keep_success:
                    decisions.append(HousekeepingDecision(
                        run=run,
                        action='KEEP',
                        reason=f'Within keep_success limit ({success_count + 1}/{self.policy.keep_success})'
                    ))
                    success_count += 1
                else:
                    decisions.append(self._evaluate_deletion(run, 'Success limit exceeded'))
            else:
                if non_success_count < self.policy.keep_non_success:
                    decisions.append(HousekeepingDecision(
                        run=run,
                        action='KEEP',
                        reason=f'Within keep_non_success limit ({non_success_count + 1}/{self.policy.keep_non_success})'
                    ))
                    non_success_count += 1
                else:
                    decisions.append(self._evaluate_deletion(run, 'Non-success limit exceeded'))

        return decisions

    def _evaluate_deletion(self, run: LogicalRun, limit_reason: str) -> HousekeepingDecision:
        # Check safety rules
        if not run.metadata:
            return HousekeepingDecision(run=run, action='KEEP', reason=f'{limit_reason}, but metadata missing/corrupt (safety skip)')
        
        # require_verified_newer_backup: actually we already know there are newer ones 
        # because we are iterating newest first and we already counted keep_success ones.
        # But we should ensure at least one SUCCESS exists that is newer than this one.
        # (This is already implied if success_count > 0 when we reach here)
        
        files_to_delete = []
        for p in run.files:
            if p.suffix == '.gz' and self.policy.delete_artifacts:
                files_to_delete.append(p)
            elif '.metadata.json' in p.name and self.policy.delete_artifacts:
                files_to_delete.append(p)
            elif '-report.json' in p.name and self.policy.delete_reports:
                files_to_delete.append(p)
            elif self.policy.delete_reports: # other auxiliary files
                files_to_delete.append(p)

        return HousekeepingDecision(
            run=run,
            action='DELETE',
            reason=limit_reason,
            files_to_delete=files_to_delete
        )

    def execute(self, decisions: list[HousekeepingDecision]) -> dict[str, Any]:
        result = {
            'deleted': [],
            'kept': [],
            'protected': [],
            'failed_deletions': [],
            'skipped_deletions': [], # candidate for deletion but skipped for some reason
        }

        for d in decisions:
            if d.action == 'PROTECT':
                result['protected'].append({
                    'timestamp': d.run.timestamp,
                    'reason': d.reason,
                    'files': [p.name for p in d.run.files]
                })
            elif d.action == 'KEEP':
                result['kept'].append({
                    'timestamp': d.run.timestamp,
                    'reason': d.reason,
                    'files': [p.name for p in d.run.files]
                })
            elif d.action == 'DELETE':
                if self.policy.dry_run:
                    result['skipped_deletions'].append({
                        'timestamp': d.run.timestamp,
                        'reason': f"{d.reason} (DRY RUN)",
                        'files': [p.name for p in d.files_to_delete]
                    })
                else:
                    deleted_files = []
                    failed_files = []
                    for p in d.files_to_delete:
                        try:
                            if p.exists():
                                p.unlink()
                                deleted_files.append(p.name)
                        except Exception as exc:
                            failed_files.append({'file': p.name, 'error': str(exc)})
                    
                    if failed_files:
                        result['failed_deletions'].append({
                            'timestamp': d.run.timestamp,
                            'failed_files': failed_files,
                            'deleted_files': deleted_files
                        })
                    
                    result['deleted'].append({
                        'timestamp': d.run.timestamp,
                        'reason': d.reason,
                        'files': deleted_files
                    })
        
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

    # Prepare housekeeping report section
    hk_report = {
        'status': 'OK',
        'policy': {
            'keep_success': policy.keep_success,
            'keep_non_success': policy.keep_non_success,
            'delete_artifacts': policy.delete_artifacts,
            'delete_reports': policy.delete_reports,
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
            {'timestamp': r.timestamp, 'status': r.status, 'files_count': len(r.files)} 
            for r in runs
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
