# Contrato de `backupkit precheck`

## Objetivo

Validar que el recurso configurado está en condiciones mínimas de operación antes de correr un backup.

## Salida

Siempre escribe:

- `precheck-report.json`

## Campos de reporte

- `project`
- `resource`
- `resource_type`
- `command=precheck`
- `phase=precheck`
- `started_at`
- `finished_at`
- `duration_sec`
- `status`
- `summary`
- `checks[]`

## Checks actuales esperables

### Core

- `core.config.required`
- `core.output_dir.writable`
- `core.free_space`
- `core.tools.available`
- `core.lock.available`
- `core.adapter.supported` solo si el adapter no existe

### Adapter MySQL

- `adapter.mysql.connectivity`
- `adapter.mysql.auth`

## Semántica de estado

- `OK`: sin warnings ni errores
- `WARN`: al menos un warning y ningún error
- `ERROR`: al menos un error
