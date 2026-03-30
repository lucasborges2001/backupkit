from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.result import ArtifactMetadata, CheckResult


@dataclass
class ArtifactVerificationResult:
    artifact_path: Path | None
    metadata_path: Path | None
    metadata: ArtifactMetadata | None


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_artifact_metadata(metadata: ArtifactMetadata) -> Path:
    artifact_path = Path(metadata.path)
    metadata_path = artifact_path.with_suffix(artifact_path.suffix + '.metadata.json')
    metadata.metadata_path = str(metadata_path)
    metadata_path.write_text(json.dumps(metadata.as_dict(), indent=2, ensure_ascii=False), encoding='utf-8')
    return metadata_path


def _parse_metadata(raw: dict[str, Any], metadata_path: Path) -> ArtifactMetadata:
    return ArtifactMetadata.from_values(
        path=raw.get('path', ''),
        size_bytes=raw.get('size_bytes', 0),
        sha256=raw.get('sha256', ''),
        timestamp=raw.get('timestamp', ''),
        engine=raw.get('engine', ''),
        resource=raw.get('resource', ''),
        project=raw.get('project', ''),
        duration_sec=raw.get('duration_sec', 0),
        status=raw.get('status', ''),
        metadata_path=raw.get('metadata_path') or metadata_path,
    )


def artifact_paths_from_config(config: dict) -> tuple[Path | None, Path | None]:
    policy = config['policy']
    output_dir = Path(policy['artifact']['output_dir'])
    artifact_cfg = policy.get('artifact', {})
    artifact_name = artifact_cfg.get('verify_path') or artifact_cfg.get('path')
    metadata_name = artifact_cfg.get('verify_metadata_path') or artifact_cfg.get('metadata_path')

    artifact_path = Path(artifact_name) if artifact_name else None
    if artifact_path and not artifact_path.is_absolute():
        artifact_path = output_dir / artifact_path

    metadata_path = Path(metadata_name) if metadata_name else None
    if metadata_path and not metadata_path.is_absolute():
        metadata_path = output_dir / metadata_path

    if artifact_path and not metadata_path:
        metadata_path = artifact_path.with_suffix(artifact_path.suffix + '.metadata.json')
    elif metadata_path and not artifact_path:
        try:
            raw = json.loads(metadata_path.read_text(encoding='utf-8'))
            candidate = raw.get('path')
            if candidate:
                artifact_path = Path(candidate)
        except Exception:
            artifact_path = None

    if artifact_path and not artifact_path.is_absolute():
        artifact_path = output_dir / artifact_path
    if metadata_path and not metadata_path.is_absolute():
        metadata_path = output_dir / metadata_path

    return artifact_path, metadata_path


class ArtifactVerifier:
    @staticmethod
    def verify(config: dict, report, *, expected_engine: str | None = None):
        expected_project = report.project
        expected_resource = report.resource
        artifact_path, metadata_path = artifact_paths_from_config(config)

        if not artifact_path and not metadata_path:
            report.add(CheckResult(
                'core.artifact.input',
                'ERROR',
                'blocking',
                'artifact.path or artifact.metadata_path required for verify-artifact',
            ))
            return ArtifactVerificationResult(None, None, None)

        ArtifactVerifier._check_artifact_presence(report, artifact_path)
        metadata = ArtifactVerifier._load_metadata(report, metadata_path)
        if metadata and not artifact_path:
            artifact_path = Path(metadata.path)

        ArtifactVerifier._check_artifact_nonempty(report, artifact_path)
        ArtifactVerifier._check_gzip_integrity(report, artifact_path)
        ArtifactVerifier._check_sha256(report, artifact_path, metadata)
        ArtifactVerifier._check_metadata_consistency(
            report,
            artifact_path,
            metadata_path,
            metadata,
            expected_engine=expected_engine,
            expected_project=expected_project,
            expected_resource=expected_resource,
        )

        if metadata:
            report.set_artifact(metadata)
        return ArtifactVerificationResult(artifact_path, metadata_path, metadata)

    @staticmethod
    def _check_artifact_presence(report, artifact_path: Path | None):
        if artifact_path and artifact_path.exists():
            report.add(CheckResult('artifact.file.exists', 'OK', 'blocking', f'Artifact exists: {artifact_path}', {'path': str(artifact_path)}))
        else:
            report.add(CheckResult('artifact.file.exists', 'ERROR', 'blocking', f'Artifact missing: {artifact_path or "not provided"}'))

    @staticmethod
    def _check_artifact_nonempty(report, artifact_path: Path | None):
        if not artifact_path or not artifact_path.exists():
            return
        size_bytes = artifact_path.stat().st_size
        if size_bytes > 0:
            report.add(CheckResult('artifact.file.nonempty', 'OK', 'blocking', f'Artifact non-empty: {size_bytes} bytes', {'size_bytes': size_bytes}))
        else:
            report.add(CheckResult('artifact.file.nonempty', 'ERROR', 'blocking', 'Artifact is empty', {'size_bytes': size_bytes}))

    @staticmethod
    def _check_gzip_integrity(report, artifact_path: Path | None):
        if not artifact_path or not artifact_path.exists():
            return
        if artifact_path.suffix != '.gz':
            report.add(CheckResult('artifact.gzip.valid', 'WARN', 'warning', 'Artifact is not a .gz file; gzip validation skipped'))
            return
        try:
            with gzip.open(artifact_path, 'rb') as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b''):
                    if not chunk:
                        break
            report.add(CheckResult('artifact.gzip.valid', 'OK', 'blocking', 'Gzip stream valid'))
        except Exception as exc:
            report.add(CheckResult('artifact.gzip.valid', 'ERROR', 'blocking', f'Invalid gzip artifact: {exc}'))

    @staticmethod
    def _load_metadata(report, metadata_path: Path | None) -> ArtifactMetadata | None:
        if metadata_path is None:
            report.add(CheckResult('artifact.metadata.present', 'ERROR', 'blocking', 'Artifact metadata path not provided and could not be inferred'))
            return None
        if not metadata_path.exists():
            report.add(CheckResult('artifact.metadata.present', 'ERROR', 'blocking', f'Artifact metadata missing: {metadata_path}'))
            return None
        try:
            raw = json.loads(metadata_path.read_text(encoding='utf-8'))
        except Exception as exc:
            report.add(CheckResult('artifact.metadata.present', 'ERROR', 'blocking', f'Artifact metadata unreadable: {exc}'))
            return None
        report.add(CheckResult('artifact.metadata.present', 'OK', 'blocking', f'Artifact metadata present: {metadata_path}', {'metadata_path': str(metadata_path)}))
        try:
            metadata = _parse_metadata(raw, metadata_path)
        except Exception as exc:
            report.add(CheckResult('artifact.metadata.parse', 'ERROR', 'blocking', f'Artifact metadata invalid: {exc}'))
            return None
        report.add(CheckResult('artifact.metadata.parse', 'OK', 'blocking', 'Artifact metadata parsed'))
        return metadata

    @staticmethod
    def _check_sha256(report, artifact_path: Path | None, metadata: ArtifactMetadata | None):
        if metadata is None:
            report.add(CheckResult('artifact.sha256.present', 'ERROR', 'blocking', 'Artifact metadata missing; sha256 cannot be validated'))
            return
        if metadata.sha256:
            report.add(CheckResult('artifact.sha256.present', 'OK', 'blocking', 'Artifact metadata includes sha256'))
        else:
            report.add(CheckResult('artifact.sha256.present', 'ERROR', 'blocking', 'Artifact metadata sha256 missing'))
            return
        if not artifact_path or not artifact_path.exists():
            return
        actual_sha = sha256_file(artifact_path)
        if actual_sha == metadata.sha256:
            report.add(CheckResult('artifact.sha256.match', 'OK', 'blocking', 'Artifact sha256 matches metadata', {'sha256': actual_sha}))
        else:
            report.add(CheckResult('artifact.sha256.match', 'ERROR', 'blocking', 'Artifact sha256 mismatch', {'expected_sha256': metadata.sha256, 'actual_sha256': actual_sha}))

    @staticmethod
    def _check_metadata_consistency(report, artifact_path: Path | None, metadata_path: Path | None, metadata: ArtifactMetadata | None, *, expected_engine: str | None, expected_project: str, expected_resource: str):
        if metadata is None:
            return

        issues: list[str] = []
        warnings: list[str] = []

        if artifact_path and metadata.path != str(artifact_path):
            issues.append(f'metadata.path={metadata.path} differs from artifact path {artifact_path}')
        if metadata_path and metadata.metadata_path and metadata.metadata_path != str(metadata_path):
            issues.append(f'metadata.metadata_path={metadata.metadata_path} differs from metadata path {metadata_path}')
        if artifact_path and artifact_path.exists() and metadata.size_bytes != artifact_path.stat().st_size:
            issues.append(f'metadata.size_bytes={metadata.size_bytes} differs from actual size {artifact_path.stat().st_size}')
        if metadata.project != expected_project:
            issues.append(f'metadata.project={metadata.project} differs from expected {expected_project}')
        if metadata.resource != expected_resource:
            issues.append(f'metadata.resource={metadata.resource} differs from expected {expected_resource}')
        if expected_engine and metadata.engine != expected_engine:
            issues.append(f'metadata.engine={metadata.engine} differs from expected {expected_engine}')
        if not metadata.timestamp:
            issues.append('metadata.timestamp missing')
        if metadata.duration_sec < 0:
            issues.append(f'metadata.duration_sec invalid: {metadata.duration_sec}')
        if metadata.status != 'OK':
            warnings.append(f'metadata.status={metadata.status} is not OK')

        if issues:
            report.add(CheckResult('artifact.metadata.consistency', 'ERROR', 'blocking', '; '.join(issues)))
        else:
            report.add(CheckResult('artifact.metadata.consistency', 'OK', 'blocking', 'Artifact metadata consistent with verify-artifact run'))
        if warnings:
            report.add(CheckResult('artifact.metadata.status', 'WARN', 'warning', '; '.join(warnings)))
        else:
            report.add(CheckResult('artifact.metadata.status', 'OK', 'blocking', 'Artifact metadata status is OK'))
