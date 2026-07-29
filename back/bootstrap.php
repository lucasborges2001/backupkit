<?php

declare(strict_types=1);

if (!defined('BACKUPKIT_MODULE_ROOT')) {
    define('BACKUPKIT_MODULE_ROOT', dirname(__DIR__));
}

if (!defined('BACKUPKIT_REPORT_VERSION')) {
    define('BACKUPKIT_REPORT_VERSION', 2);
}

if (!defined('BACKUPKIT_MAX_REPORT_BYTES')) {
    define('BACKUPKIT_MAX_REPORT_BYTES', 2 * 1024 * 1024);
}

if (!function_exists('backupkit_module_root')) {
    function backupkit_module_root(): string
    {
        return BACKUPKIT_MODULE_ROOT;
    }
}

if (!function_exists('backupkit_manifest')) {
    /** @return array<string,mixed> */
    function backupkit_manifest(): array
    {
        $manifest = require BACKUPKIT_MODULE_ROOT . '/module.php';
        if (!is_array($manifest)) {
            throw new RuntimeException('BackupKit module.php must return an array');
        }

        return $manifest;
    }
}

if (!function_exists('backupkit_contract_validate_keys')) {
    /**
     * @param array<string,mixed> $value
     * @param list<string> $required
     * @param list<string> $allowed
     * @param list<string> $errors
     */
    function backupkit_contract_validate_keys(
        array $value,
        array $required,
        array $allowed,
        string $scope,
        array &$errors
    ): void {
        foreach ($required as $key) {
            if (!array_key_exists($key, $value)) {
                $errors[] = $scope . '.' . $key . ' is required';
            }
        }

        foreach (array_keys($value) as $key) {
            if (!in_array((string) $key, $allowed, true)) {
                $errors[] = $scope . '.' . $key . ' is not supported';
            }
        }
    }
}

if (!function_exists('backupkit_report_validate')) {
    /**
     * Validate the exact public JSON contract emitted by report_version=2.
     *
     * @param array<string,mixed> $report
     * @return array{ok:bool,errors:list<string>}
     */
    function backupkit_report_validate(array $report): array
    {
        $errors = [];
        $topLevelKeys = [
            'report_version',
            'metadata',
            'final_status',
            'phases',
            'artifacts',
            'validators',
            'notifications',
            'housekeeping',
            'final_summary',
        ];
        backupkit_contract_validate_keys($report, $topLevelKeys, $topLevelKeys, 'report', $errors);

        if (($report['report_version'] ?? null) !== BACKUPKIT_REPORT_VERSION) {
            $errors[] = 'report.report_version must be integer 2';
        }

        $metadata = $report['metadata'] ?? null;
        $metadataKeys = [
            'project',
            'resource',
            'resource_type',
            'command',
            'started_at',
            'finished_at',
            'duration_ms',
        ];
        if (!is_array($metadata)) {
            $errors[] = 'report.metadata must be an object';
            $metadata = [];
        } else {
            backupkit_contract_validate_keys($metadata, $metadataKeys, $metadataKeys, 'report.metadata', $errors);
        }

        foreach (['project', 'resource', 'command', 'started_at', 'finished_at'] as $key) {
            if (!is_string($metadata[$key] ?? null) || trim((string) $metadata[$key]) === '') {
                $errors[] = 'report.metadata.' . $key . ' must be a non-empty string';
            }
        }
        if (isset($metadata['resource_type']) && $metadata['resource_type'] !== null && !is_string($metadata['resource_type'])) {
            $errors[] = 'report.metadata.resource_type must be string or null';
        }
        if (!is_int($metadata['duration_ms'] ?? null) || ($metadata['duration_ms'] ?? -1) < 0) {
            $errors[] = 'report.metadata.duration_ms must be a non-negative integer';
        }

        $commands = ['precheck', 'backup', 'verify-artifact', 'restore-test'];
        if (isset($metadata['command']) && !in_array($metadata['command'], $commands, true)) {
            $errors[] = 'report.metadata.command is unsupported';
        }

        $finalStatus = $report['final_status'] ?? null;
        if (!in_array($finalStatus, ['OK', 'WARN', 'ERROR'], true)) {
            $errors[] = 'report.final_status must be OK, WARN or ERROR';
        }

        $phases = $report['phases'] ?? null;
        if (!is_array($phases) || count($phases) !== 1 || !is_array($phases[0] ?? null)) {
            $errors[] = 'report.phases must contain exactly one phase object';
        } else {
            $phase = $phases[0];
            $phaseKeys = ['id', 'status', 'started_at', 'finished_at', 'duration_ms', 'summary', 'evidence'];
            backupkit_contract_validate_keys($phase, $phaseKeys, $phaseKeys, 'report.phases[0]', $errors);

            if (($phase['id'] ?? null) !== ($metadata['command'] ?? null)) {
                $errors[] = 'report.phases[0].id must equal report.metadata.command';
            }
            if (($phase['status'] ?? null) !== $finalStatus) {
                $errors[] = 'report.phases[0].status must equal report.final_status';
            }
            if (!is_int($phase['duration_ms'] ?? null) || ($phase['duration_ms'] ?? -1) < 0) {
                $errors[] = 'report.phases[0].duration_ms must be a non-negative integer';
            }

            $summary = $phase['summary'] ?? null;
            if (!is_array($summary)) {
                $errors[] = 'report.phases[0].summary must be an object';
            } else {
                backupkit_contract_validate_keys(
                    $summary,
                    ['human', 'counts'],
                    ['human', 'counts'],
                    'report.phases[0].summary',
                    $errors
                );
                if (!is_string($summary['human'] ?? null)) {
                    $errors[] = 'report.phases[0].summary.human must be a string';
                }
                $counts = $summary['counts'] ?? null;
                if (!is_array($counts)) {
                    $errors[] = 'report.phases[0].summary.counts must be an object';
                } else {
                    $countKeys = ['ok', 'warn', 'error', 'total'];
                    backupkit_contract_validate_keys(
                        $counts,
                        $countKeys,
                        $countKeys,
                        'report.phases[0].summary.counts',
                        $errors
                    );
                    foreach ($countKeys as $key) {
                        if (!is_int($counts[$key] ?? null) || ($counts[$key] ?? -1) < 0) {
                            $errors[] = 'report.phases[0].summary.counts.' . $key . ' must be a non-negative integer';
                        }
                    }
                }
            }

            $evidence = $phase['evidence'] ?? null;
            if (!is_array($evidence)) {
                $errors[] = 'report.phases[0].evidence must be an object';
            } else {
                backupkit_contract_validate_keys(
                    $evidence,
                    ['checks', 'restore_test'],
                    ['checks', 'restore_test'],
                    'report.phases[0].evidence',
                    $errors
                );
                if (!is_array($evidence['checks'] ?? null)) {
                    $errors[] = 'report.phases[0].evidence.checks must be an array';
                }
                if (!is_array($evidence['restore_test'] ?? null)) {
                    $errors[] = 'report.phases[0].evidence.restore_test must be an object';
                }
            }
        }

        foreach (['artifacts', 'validators', 'notifications', 'housekeeping'] as $key) {
            if (!is_array($report[$key] ?? null)) {
                $errors[] = 'report.' . $key . ' must be an array or object';
            }
        }
        if (!is_string($report['final_summary'] ?? null)) {
            $errors[] = 'report.final_summary must be a string';
        }

        return [
            'ok' => $errors === [],
            'errors' => $errors,
        ];
    }
}

if (!function_exists('backupkit_report_load')) {
    /** @return array<string,mixed> */
    function backupkit_report_load(string $path): array
    {
        $path = trim($path);
        if ($path === '') {
            throw new InvalidArgumentException('BackupKit report path is required');
        }
        if (is_link($path)) {
            throw new RuntimeException('BackupKit report symlinks are not accepted');
        }

        $resolved = realpath($path);
        if ($resolved === false || !is_file($resolved) || !is_readable($resolved)) {
            throw new RuntimeException('BackupKit report is missing or unreadable');
        }
        if (substr(basename($resolved), -12) !== '-report.json') {
            throw new RuntimeException('BackupKit report filename must end with -report.json');
        }

        $size = filesize($resolved);
        if ($size === false || $size > BACKUPKIT_MAX_REPORT_BYTES) {
            throw new RuntimeException('BackupKit report exceeds the allowed size');
        }

        $content = file_get_contents($resolved);
        if ($content === false) {
            throw new RuntimeException('BackupKit report could not be read');
        }

        try {
            $report = json_decode($content, true, 512, JSON_THROW_ON_ERROR);
        } catch (JsonException $exception) {
            throw new RuntimeException('BackupKit report contains invalid JSON', 0, $exception);
        }
        if (!is_array($report)) {
            throw new RuntimeException('BackupKit report root must be an object');
        }

        $validation = backupkit_report_validate($report);
        if (!$validation['ok']) {
            throw new UnexpectedValueException(
                'BackupKit report does not satisfy backupkit.report.v2: ' . implode('; ', $validation['errors'])
            );
        }

        return $report;
    }
}

if (!function_exists('backupkit_report_summary')) {
    /**
     * Build a UI-safe summary without absolute paths or validator SQL.
     *
     * @param array<string,mixed> $report
     * @return array<string,mixed>
     */
    function backupkit_report_summary(array $report): array
    {
        $validation = backupkit_report_validate($report);
        if (!$validation['ok']) {
            throw new UnexpectedValueException(
                'BackupKit report does not satisfy backupkit.report.v2: ' . implode('; ', $validation['errors'])
            );
        }

        $phase = $report['phases'][0];
        $restore = $phase['evidence']['restore_test'];
        $artifacts = [];
        foreach ($report['artifacts'] as $artifact) {
            if (!is_array($artifact)) {
                continue;
            }
            $artifacts[] = [
                'name' => basename((string) ($artifact['path'] ?? '')),
                'size_bytes' => $artifact['size_bytes'] ?? null,
                'sha256' => $artifact['sha256'] ?? null,
                'status' => $artifact['status'] ?? null,
            ];
        }

        $validators = [];
        foreach ($report['validators'] as $validator) {
            if (!is_array($validator)) {
                continue;
            }
            $validators[] = [
                'id' => $validator['id'] ?? null,
                'description' => $validator['description'] ?? null,
                'expected' => $validator['expected'] ?? null,
                'severity' => $validator['severity'] ?? null,
                'actual_value' => $validator['actual_value'] ?? null,
                'status' => $validator['status'] ?? null,
                'message' => $validator['message'] ?? null,
            ];
        }

        $notifications = [];
        foreach ($report['notifications'] as $notification) {
            if (!is_array($notification)) {
                continue;
            }
            $notifications[] = [
                'channel' => $notification['channel'] ?? null,
                'status' => $notification['status'] ?? null,
            ];
        }

        return [
            'contract' => 'backupkit.report.v2',
            'project' => $report['metadata']['project'],
            'resource' => $report['metadata']['resource'],
            'resource_type' => $report['metadata']['resource_type'],
            'command' => $report['metadata']['command'],
            'started_at' => $report['metadata']['started_at'],
            'finished_at' => $report['metadata']['finished_at'],
            'duration_ms' => $report['metadata']['duration_ms'],
            'final_status' => $report['final_status'],
            'counts' => $phase['summary']['counts'],
            'artifacts' => $artifacts,
            'validators' => $validators,
            'notifications' => $notifications,
            'housekeeping' => $report['housekeeping'],
            'restore_test' => [
                'cleanup_attempted' => $restore['cleanup_attempted'] ?? null,
                'cleanup_succeeded' => $restore['cleanup_succeeded'] ?? null,
                'validators_summary' => $restore['validators_summary'] ?? null,
            ],
            'final_summary' => $report['final_summary'],
        ];
    }
}

if (!function_exists('backupkit_health_payload')) {
    /** @return array<string,mixed> */
    function backupkit_health_payload(?string $reportPath = null): array
    {
        $cliPath = BACKUPKIT_MODULE_ROOT . '/bin/backupkit';
        $payload = [
            'ok' => is_file($cliPath),
            'module' => 'backupkit',
            'status' => is_file($cliPath) ? 'available' : 'error',
            'contract' => 'backupkit.health.v1',
            'report_contract' => 'backupkit.report.v2',
            'cli_present' => is_file($cliPath),
            'cli_executable' => is_executable($cliPath),
            'http_execution' => false,
            'report_configured' => $reportPath !== null && trim($reportPath) !== '',
        ];

        if ($payload['report_configured']) {
            try {
                $payload['latest_report'] = backupkit_report_summary(backupkit_report_load((string) $reportPath));
            } catch (Throwable $exception) {
                $payload['ok'] = false;
                $payload['status'] = 'degraded';
                $payload['report_error'] = $exception->getMessage();
            }
        }

        return $payload;
    }
}

return [
    'ok' => true,
    'module' => 'backupkit',
    'manifest_contract' => 'backupkit.manifest.v1',
    'report_contract' => 'backupkit.report.v2',
    'health_contract' => 'backupkit.health.v1',
    'http_execution' => false,
];
