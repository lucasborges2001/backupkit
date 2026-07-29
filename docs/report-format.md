# Formato de reporte JSON `v2`

`backupkit` expone un único contrato de reporte orientado a pipeline.

## Invariante principal

```text
report_version = 2
```

No existen campos top-level alternativos ni compatibilidad con el formato anterior.

## Estructura canónica

```json
{
  "report_version": 2,
  "metadata": {
    "project": "demo",
    "resource": "mysql-main",
    "resource_type": "mysql",
    "command": "restore-test",
    "started_at": "2026-03-31T12:00:00+00:00",
    "finished_at": "2026-03-31T12:00:03+00:00",
    "duration_ms": 3012
  },
  "final_status": "WARN",
  "phases": [
    {
      "id": "restore-test",
      "status": "WARN",
      "started_at": "2026-03-31T12:00:00+00:00",
      "finished_at": "2026-03-31T12:00:03+00:00",
      "duration_ms": 3012,
      "summary": {
        "human": "Pipeline restore-test finalizó con estado WARN; checks total=11; ok=10; warn=1; error=0",
        "counts": {
          "ok": 10,
          "warn": 1,
          "error": 0,
          "total": 11
        }
      },
      "evidence": {
        "checks": [],
        "artifacts": [],
        "restore_test": {},
        "validators": [],
        "notifications": [],
        "housekeeping": {}
      }
    }
  ],
  "artifacts": [],
  "validators": [],
  "notifications": [],
  "housekeeping": {},
  "final_summary": "Pipeline restore-test finalizó con estado WARN; checks total=11; ok=10; warn=1; error=0"
}
```

## Campos top-level

El conjunto de campos es exacto:

```text
report_version
metadata
final_status
phases
artifacts
validators
notifications
housekeeping
final_summary
```

Los arrays vacíos y objetos vacíos se conservan para mantener una forma estable.

## `metadata`

Describe la corrida completa:

- `project`;
- `resource`;
- `resource_type`;
- `command`;
- `started_at`;
- `finished_at`;
- `duration_ms`.

`command` admite actualmente:

- `precheck`;
- `backup`;
- `verify-artifact`;
- `restore-test`.

## `final_status`

Estado consolidado:

- `ERROR`: existe al menos un check con `status=ERROR`;
- `WARN`: no hay errores y existe al menos un warning;
- `OK`: no hay errores ni warnings.

Códigos de salida:

| `final_status` | Código |
|---|---:|
| `OK` | `0` |
| `WARN` | `1` |
| `ERROR` | `2` |

## `phases[]`

Cada comando genera actualmente una fase cuyo `id` coincide con el comando.

Campos de fase:

- `id`;
- `status`;
- `started_at`;
- `finished_at`;
- `duration_ms`;
- `summary`;
- `evidence`.

### `summary`

Contiene:

- `human`: resumen legible;
- `counts.ok`;
- `counts.warn`;
- `counts.error`;
- `counts.total`.

### `evidence`

El objeto contiene siempre:

- `checks[]`;
- `artifacts[]`;
- `restore_test`;
- `validators[]`;
- `notifications[]`;
- `housekeeping`.

`checks[]` es la fuente canónica de checks de ejecución.

`restore_test` queda vacío para comandos que no ejecutan restore.

## `artifacts[]`

Lista plana de artefactos asociados a la corrida.

Para `backup` contiene el artefacto generado. Para `verify-artifact` y `restore-test` contiene el artefacto verificado cuando su metadata pudo parsearse.

Campos actuales de un artefacto:

- `path`;
- `metadata_path`;
- `size_bytes`;
- `sha256`;
- `timestamp`;
- `engine`;
- `resource`;
- `project`;
- `duration_sec`;
- `status`.

`path` y `metadata_path` se registran como paths absolutos para artefactos nuevos.

## `validators[]`

Lista plana de resultados de validators SQL declarativos.

Se mantiene vacía salvo durante `restore-test` con validators configurados.

Cada resultado puede incluir:

- `id`;
- `status`;
- `severity`;
- `message`;
- `actual_value`;
- datos de la regla evaluada.

## `notifications[]`

Lista de intentos de notificación:

- `channel`;
- `status`;
- `message`;
- `meta`.

## `housekeeping`

Detalle de retención. Es `{}` cuando `retention.enabled=false`.

Cuando está habilitado incluye:

- `status`;
- `policy`;
- `summary`;
- `discovered_runs[]`;
- `kept_runs[]`;
- `protected_runs[]`;
- `deleted_runs[]`;
- `skipped_deletions[]`;
- `failed_deletions[]` cuando corresponda.

## `final_summary`

Resumen humano consolidado para logs y operación rápida.

No debe parsearse como fuente estructural; los consumidores deben usar los demás campos.

## Campos que no forman parte de `v2`

Los siguientes nombres no se publican en el nivel superior:

```text
project
resource
resource_type
command
phase
started_at
finished_at
duration_sec
status
summary
checks
artifact
restore_test
```

Equivalencias canónicas:

| Concepto | Ruta `v2` |
|---|---|
| estado final | `final_status` |
| comando | `metadata.command` |
| duración | `metadata.duration_ms` |
| checks | `phases[0].evidence.checks[]` |
| artefactos | `artifacts[]` |
| restore | `phases[0].evidence.restore_test` |
| validators | `validators[]` |

Estas son rutas contractuales, no aliases temporales.
