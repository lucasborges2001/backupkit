<?php

declare(strict_types=1);

function backupkit_test_assert(bool $condition, string $message): void
{
    if (!$condition) {
        fwrite(STDERR, "BACKUPKIT_PHP_CONTRACT_FAIL: {$message}\n");
        exit(1);
    }
}

$root = dirname(__DIR__);
$bootstrap = require $root . '/back/bootstrap.php';

backupkit_test_assert(is_array($bootstrap), 'bootstrap must return an array');
backupkit_test_assert(($bootstrap['ok'] ?? false) === true, 'bootstrap must be available');
backupkit_test_assert(($bootstrap['report_contract'] ?? null) === 'backupkit.report.v2', 'report contract mismatch');
backupkit_test_assert(($bootstrap['http_execution'] ?? null) === false, 'HTTP execution must remain disabled');

$manifest = backupkit_manifest();
backupkit_test_assert(($manifest['key'] ?? null) === 'backupkit', 'manifest key mismatch');
backupkit_test_assert(($manifest['source'] ?? null) === 'submodules/backupkit', 'manifest source mismatch');
backupkit_test_assert(($manifest['dependencies'] ?? null) === [], 'standalone contract must have no repository dependencies');
backupkit_test_assert(($manifest['bootstrap'] ?? null) === 'back/bootstrap.php', 'bootstrap path mismatch');
backupkit_test_assert(($manifest['capabilities']['tooling'] ?? false) === true, 'tooling capability missing');
backupkit_test_assert(($manifest['capabilities']['backend_only'] ?? false) === true, 'backend-only capability missing');
backupkit_test_assert(($manifest['capabilities']['report_readonly'] ?? false) === true, 'read-only report capability missing');
backupkit_test_assert(($manifest['capabilities']['public'] ?? true) === false, 'public capability must be disabled');
backupkit_test_assert(($manifest['capabilities']['api'] ?? true) === false, 'API capability must be disabled');
backupkit_test_assert(($manifest['capabilities']['http_writes'] ?? true) === false, 'HTTP writes must be disabled');
backupkit_test_assert(($manifest['superadmin']['enabled'] ?? true) === false, 'SuperAdmin must remain disabled');
backupkit_test_assert(($manifest['contracts']['writes'] ?? null) === [], 'host write contracts must be empty');

$deployment = $manifest['deployment'] ?? null;
backupkit_test_assert(is_array($deployment), 'deployment contract must exist');
backupkit_test_assert(($deployment['contract'] ?? null) === 'backupkit.deploy.v1', 'deploy contract mismatch');
backupkit_test_assert(($deployment['profile'] ?? null) === 'server', 'deploy profile must be server');
backupkit_test_assert(($deployment['module_manifest'] ?? null) === 'deploy/module.manifest.json', 'module deploy manifest mismatch');
backupkit_test_assert(($deployment['server_manifest'] ?? null) === 'deploy/server.manifest.json', 'server deploy manifest mismatch');
backupkit_test_assert(($deployment['include_in_app_deploy'] ?? true) === false, 'BackupKit must not enter app deploy');
backupkit_test_assert(($deployment['requires_public_html'] ?? true) === false, 'BackupKit deploy must not require public_html');
backupkit_test_assert(($deployment['base_runtime_dependency'] ?? true) === false, 'Base must not be a runtime dependency');
backupkit_test_assert(in_array('backupkit.deploy.v1', $manifest['contracts']['readonly'] ?? [], true), 'deploy readonly contract missing');
backupkit_test_assert(is_file($root . '/' . $deployment['module_manifest']), 'module deploy manifest must exist');
backupkit_test_assert(is_file($root . '/' . $deployment['server_manifest']), 'server deploy manifest must exist');

$fixture = $root . '/tests/fixtures/precheck-report.json';
$report = backupkit_report_load($fixture);
$validation = backupkit_report_validate($report);
backupkit_test_assert($validation['ok'] === true, 'fixture must satisfy report v2');
backupkit_test_assert($validation['errors'] === [], 'valid fixture must not expose validation errors');

$summary = backupkit_report_summary($report);
backupkit_test_assert(($summary['contract'] ?? null) === 'backupkit.report.v2', 'summary contract mismatch');
backupkit_test_assert(($summary['command'] ?? null) === 'precheck', 'summary command mismatch');
backupkit_test_assert(($summary['final_status'] ?? null) === 'OK', 'summary status mismatch');
backupkit_test_assert(($summary['counts']['total'] ?? null) === 2, 'summary counts mismatch');
backupkit_test_assert(!array_key_exists('checks', $summary), 'UI-safe summary must not expose raw checks');
backupkit_test_assert(!array_key_exists('phases', $summary), 'UI-safe summary must not expose raw phases');

$legacy = $report;
$legacy['status'] = 'OK';
$legacyValidation = backupkit_report_validate($legacy);
backupkit_test_assert($legacyValidation['ok'] === false, 'legacy top-level fields must be rejected');
backupkit_test_assert(
    in_array('report.status is not supported', $legacyValidation['errors'], true),
    'legacy rejection must identify report.status'
);

$filenameRejected = false;
try {
    backupkit_report_load($root . '/tests/fixtures/report-v2-ok.json');
} catch (RuntimeException $exception) {
    $filenameRejected = strpos($exception->getMessage(), '-report.json') !== false;
}
backupkit_test_assert($filenameRejected, 'operational loader must reject non-report filenames');

$health = backupkit_health_payload($fixture);
backupkit_test_assert(($health['ok'] ?? false) === true, 'health must be available with valid fixture');
backupkit_test_assert(($health['status'] ?? null) === 'available', 'health status mismatch');
backupkit_test_assert(($health['http_execution'] ?? null) === false, 'health must declare HTTP execution disabled');
backupkit_test_assert(($health['latest_report']['final_status'] ?? null) === 'OK', 'health report status mismatch');

fwrite(STDOUT, "BACKUPKIT_PHP_CONTRACT_PASS\n");
