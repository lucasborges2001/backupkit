# Formato de reporte JSON

Desde `report_version = 2`, `backupkit` expone un reporte orientado a pipeline.

## Objetivo

Representar una corrida operativa completa con:

- metadata general de ejecución
- estado final consolidado
- fases explícitas
- artefactos producidos o verificados
- resultados de validators
- intentos de notificación
- resumen humano utilizable en operación

## Estructura

```json
{
  "report_version": 2,
  "project": "demo",
  "resource": "mysql-main",
  "resource_type": "mysql",
  "command": "restore-test",
  "phase": "restore-test",
  "started_at": "2026-03-31T12:00:00+00:00",
  "finished_at": "2026-03-31T12:00:03+00:00",
  "duration_sec": 3.012,
  "status": "WARN",
  "summary": {
    "OK": 10,
    "WARN": 1,
    "ERROR": 0,
    "total": 11
  },
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

## Campos

### `metadata`

Describe la corrida de alto nivel:

- `project`
- `resource`
- `resource_type`
- `command`
- `started_at`
- `finished_at`
- `duration_ms`

### `final_status`

Estado final consolidado de la corrida.

Regla actual:

- `ERROR` si existe al menos un check con `status=ERROR`
- `WARN` si no hay errores pero sí warnings
- `OK` si no hay errores ni warnings

### `phases[]`

Representa las fases explícitas del pipeline.

En la implementación actual, cada comando genera una sola fase explícita:

- `precheck`
- `backup`
- `verify-artifact`
- `restore-test`

Cada fase contiene:

- `id`
- `status`
- `started_at`
- `finished_at`
- `duration_ms`
- `summary`
- `evidence`

### `artifacts[]`

Lista de artefactos asociados a la corrida.

Por ahora puede contener el artefacto principal (`backup` o `verify-artifact`).

### `validators[]`

Lista plana de resultados de validators declarativos SQL.

Solo aplica cuando se ejecuta `restore-test` y hay validators configurados.

### `notifications[]`

Lista de notificaciones intentadas por la corrida.

Estructura actual:

- `channel`
- `status`
- `message`
- `meta`

### `housekeeping`

Detalle del proceso de retención ejecutado. Solo presente si `retention` está habilitado.

Estructura:

- `status`: `OK` | `WARN` | `SKIP`
- `policy`: copia de la política aplicada
- `discovered_runs[]`: lista de corridas encontradas en el output
- `kept_runs[]`: corridas mantenidas por policy
- `protected_runs[]`: corridas protegidas (ej: last known valid)
- `deleted_runs[]`: corridas eliminadas
- `skipped_deletions[]`: candidatos a borrado no ejecutados (ej: dry-run)
- `summary`: conteos consolidados de la operación de housekeeping

### `final_summary`

Resumen humano consolidado, pensado para operación rápida.

## Compatibilidad hacia atrás

Para no romper integraciones existentes, todavía se mantienen:

- `status`
- `summary`
- `checks`
- `artifact`
- `restore_test`
- `duration_sec`
- `project`, `resource`, `resource_type`, `command`, `phase`

La recomendación nueva es consumir primero:

- `metadata`
- `final_status`
- `phases`
- `artifacts`
- `validators`
- `notifications`
- `final_summary`
