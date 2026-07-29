<?php

declare(strict_types=1);

return [
    'key' => 'backupkit',
    'label' => 'BackupKit',
    'name' => 'backupkit',
    'enabled' => true,
    'description' => 'Tooling operativo standalone para backup MySQL, verificacion de artefactos, restore-test y reportes auditables.',
    'source' => 'submodules/backupkit',
    'dependencies' => [],
    'bootstrap' => 'back/bootstrap.php',
    'public_path' => '',
    'routes' => [
        'public_base_path' => '',
        'api_base_path' => '',
        'superadmin_path' => '',
        'health_path' => '',
    ],
    'health' => [
        'mode' => 'backend-readonly',
        'function' => 'backupkit_health_payload',
    ],
    'capabilities' => [
        'public' => false,
        'api' => false,
        'health' => true,
        'superadmin_panel' => false,
        'backend_only' => true,
        'writes' => false,
        'http_writes' => false,
        'tooling' => true,
        'submodule' => true,
        'operational_cli' => true,
        'operational_writes' => true,
        'report_readonly' => true,
        'mysql_adapter' => true,
        'database_required' => false,
    ],
    'resources' => [
        [
            'key' => 'backupkit_latest_report',
            'label' => 'Ultimo reporte BackupKit',
            'kind' => 'readonly',
            'contract' => 'backupkit.report.v2',
            'loader' => 'backupkit_report_load',
            'summary' => 'backupkit_report_summary',
        ],
    ],
    'superadmin' => [
        'enabled' => false,
        'panels' => [],
        'assets' => ['css' => [], 'js' => []],
        'actions' => [],
    ],
    'contracts' => [
        'readonly' => [
            'backupkit.manifest.v1',
            'backupkit.report.v2',
            'backupkit.health.v1',
        ],
        'writes' => [],
    ],
    'testkit' => [
        'suites' => [
            'backupkit_contract',
        ],
    ],
];
