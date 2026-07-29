# Contrato de `backupkit precheck`

## Objetivo

Validar que el recurso configurado cumple las condiciones mínimas antes de ejecutar operaciones de backup.

## Entrada

- `.env` con secretos del adapter;
- `policy.yml` conforme a [`policy.md`](policy.md).

`precheck` no genera artefactos de backup.

## Salida

Archivos:

- `precheck-report.json`;
- `<project>__<resource>__<timestamp>__precheck-report.json`.

Rutas canónicas del reporte:

```text
metadata.command = precheck
final_status
phases[0].summary
phases[0].evidence.checks[]
```

No se publican `status`, `summary` ni `checks` como campos top-level.

## Checks esperables

### Core

- `core.config.required`;
- `core.config.unsupported` cuando la policy usa campos retirados;
- `core.output_dir.writable`;
- `core.free_space`;
- `core.tools.available`;
- `core.lock.available`;
- `core.adapter.supported` cuando el adapter no existe.

### Adapter MySQL

- `adapter.mysql.connectivity`;
- `adapter.mysql.auth`.

## Semántica de estado

- `OK`: ningún check en `WARN` o `ERROR`;
- `WARN`: al menos un warning y ningún error;
- `ERROR`: al menos un error.

El estado se publica exclusivamente en:

```text
final_status
```

## Códigos de salida

| Estado | Código |
|---|---:|
| `OK` | `0` |
| `WARN` | `1` |
| `ERROR` | `2` |

## Invariantes

- no ejecuta `mysqldump`;
- no crea ni elimina bases;
- no restaura artefactos;
- no requiere un artefacto previo;
- adquiere el mismo lock `project/resource` usado por los demás comandos;
- siempre escribe un reporte, incluso ante configuración inválida.
