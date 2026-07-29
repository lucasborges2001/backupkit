# Formato de reporte JSON `v2`

`backupkit` expone un único contrato de reporte orientado a pipeline.

## Invariante principal

```text
report_version = 2
```

No existen aliases, campos legacy ni rutas duplicadas para un mismo concepto.

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
        "restore_test": {}
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

El conjunto es exacto:

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

Los arrays y objetos vacíos se conservan para mantener una forma estable.

## Mapa 1 a 1

| Concepto | Ruta única |
|---|---|
| identidad y tiempo de corrida | `metadata` |
| estado final | `final_status` |
| estado y resumen de fase | `phases[].status` y `phases[].summary` |
| checks | `phases[].evidence.checks[]` |
| detalle de restore | `phases[].evidence.restore_test` |
| artefactos | `artifacts[]` |
| resultados de validators | `validators[]` |
| intentos de notificación | `notifications[]` |
| retención | `housekeeping` |
| resumen humano global | `final_summary` |

`phases[].evidence` no replica `artifacts`, `validators`, `notifications` ni `housekeeping`.

El objeto `restore_test` no replica `validator_results`; los resultados viven únicamente en `validators[]`.

## `metadata`

Describe la corrida completa:

- `project`;
- `resource`;
- `resource_type`;
- `command`;
- `started_at`;
- `finished_at`;
- `duration_ms`.

Comandos vigentes:

- `precheck`;
- `backup`;
- `verify-artifact`;
- `restore-test`.

## `final_status`

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

Cada comando genera actualmente una fase cuyo `id` coincide con `metadata.command`.

Campos:

- `id`;
- `status`;
- `started_at`;
- `finished_at`;
- `duration_ms`;
- `summary`;
- `evidence`.

### `summary`

- `human`;
- `counts.ok`;
- `counts.warn`;
- `counts.error`;
- `counts.total`.

### `evidence`

Contiene exactamente:

```text
checks
restore_test
```

`restore_test` es `{}` para comandos distintos de `restore-test`.

## `artifacts[]`

Lista única de artefactos asociados a la corrida.

Para `backup` contiene el artefacto generado. Para `verify-artifact` y `restore-test` contiene el artefacto verificado cuando su metadata pudo parsearse.

Campos actuales:

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

Lista única de resultados de validators SQL declarativos.

Se mantiene vacía salvo durante `restore-test` con validators configurados.

Cada resultado puede incluir:

- `id`;
- `status`;
- `severity`;
- `message`;
- `actual_value`;
- datos de la regla evaluada.

Las definiciones configuradas y el resumen agregado pueden permanecer en `phases[].evidence.restore_test`, pero los resultados individuales no se duplican allí.

## `notifications[]`

Lista única de intentos de notificación:

- `channel`;
- `status`;
- `message`;
- `meta`.

## `housekeeping`

Objeto único de retención. Es `{}` cuando `retention.enabled=false`.

Cuando está habilitado puede incluir:

- `status`;
- `policy`;
- `summary`;
- `discovered_runs[]`;
- `kept_runs[]`;
- `protected_runs[]`;
- `deleted_runs[]`;
- `skipped_deletions[]`;
- `failed_deletions[]`.

## `final_summary`

Resumen humano para logs y operación rápida.

No debe parsearse como fuente estructural.

## Campos que no forman parte de `v2`

No se publican en el nivel superior:

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

Tampoco se publican rutas alternativas dentro de `phases[].evidence` para conceptos que ya tienen un campo top-level canónico.
