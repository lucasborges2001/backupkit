# Contrato de `backupkit restore-test`

## Objetivo

Demostrar que un artefacto ya generado:

- existe;
- es técnicamente válido;
- puede restaurarse en una base temporal MySQL;
- contiene las tablas críticas declaradas;
- admite smoke queries post-restore;
- cumple validators SQL declarativos;
- puede limpiarse al finalizar.

## Flujo

1. valida configuración y campos soportados;
2. adquiere el lock `project/resource`;
3. valida output dir, espacio y herramientas;
4. verifica el artefacto;
5. crea una base temporal efímera;
6. importa el dump `.sql.gz` mediante `mysql`;
7. valida tablas críticas;
8. ejecuta smoke queries;
9. ejecuta validators SQL declarativos;
10. ejecuta cleanup con `DROP DATABASE IF EXISTS` dentro de `finally`;
11. escribe el reporte `v2`;
12. ejecuta housekeeping y notificación si corresponden.

## Configuración mínima

Las rutas relativas se resuelven respecto de `artifact.output_dir`:

```yaml
project:
  name: mysql-basic

resource:
  name: mysql-main
  type: mysql
  connection:
    host: 127.0.0.1
    port: 3306
    username: root

artifact:
  output_dir: ./var/output
  path: mysql-basic__mysql-main__20260330T120000Z.sql.gz
  metadata_path: mysql-basic__mysql-main__20260330T120000Z.sql.gz.metadata.json

restore_test:
  database_prefix: bkrt
  critical_tables:
    - users
  smoke_queries:
    - SELECT 1;
  validators:
    - id: users_non_zero
      sql: SELECT COUNT(*) FROM users;
      expected:
        rule: non_zero
      severity: error

runtime:
  lock_dir: ./var/locks

prechecks:
  require_free_space_mb: 64
  require_tools:
    - mysql_query_client
    - gzip_provider
    - hash_provider
```

Nombres canónicos:

```text
artifact.path
artifact.metadata_path
```

`artifact.verify_path` y `artifact.verify_metadata_path` producen `core.config.unsupported=ERROR`.

## Códigos de salida

| Resultado | Código |
|---|---:|
| `OK` | `0` |
| `WARN` | `1` |
| `ERROR` | `2` |

## Reporte `v2`

Mapa 1 a 1 del comando:

| Concepto | Ruta única |
|---|---|
| comando | `metadata.command` |
| estado final | `final_status` |
| artefacto verificado | `artifacts[]` |
| resultados de validators | `validators[]` |
| checks | `phases[0].evidence.checks[]` |
| base temporal, cleanup, tablas y definiciones | `phases[0].evidence.restore_test` |
| retención | `housekeeping` |
| notificaciones | `notifications[]` |

El detalle de restore no contiene `validator_results`; esos resultados viven exclusivamente en `validators[]`.

Ejemplo parcial:

```json
{
  "report_version": 2,
  "metadata": {
    "command": "restore-test"
  },
  "final_status": "OK",
  "phases": [
    {
      "id": "restore-test",
      "status": "OK",
      "evidence": {
        "checks": [],
        "restore_test": {
          "database": "bkrt_mysql_basic_mysql_main_20260330t120000z",
          "artifact_path": "/srv/backupkit/output/mysql-basic__mysql-main__20260330T120000Z.sql.gz",
          "cleanup_attempted": true,
          "cleanup_succeeded": true,
          "critical_tables": ["users"],
          "smoke_queries": ["SELECT 1;"],
          "validators": [
            {
              "id": "users_non_zero",
              "sql": "SELECT COUNT(*) FROM users;",
              "expected": {"rule": "non_zero"},
              "severity": "error"
            }
          ],
          "validators_summary": {
            "total": 1,
            "ok": 1,
            "warn": 0,
            "error": 0
          }
        }
      }
    }
  ],
  "artifacts": [],
  "validators": [
    {
      "id": "users_non_zero",
      "status": "OK",
      "actual_value": 42
    }
  ],
  "notifications": [],
  "housekeeping": {},
  "final_summary": "..."
}
```

No se publican `status`, `checks`, `artifact` ni `restore_test` como campos top-level. Tampoco se replican `artifacts`, `validators`, `notifications` o `housekeeping` dentro de la fase.

## Validators

Reglas soportadas:

- `equals`;
- `greater_than`;
- `less_than`;
- `zero`;
- `non_zero`.

Impacto:

- `severity: error`: un fallo degrada a `ERROR`;
- `severity: warning`: un fallo degrada a `WARN`.

## Invariantes de cleanup

- el cleanup se intenta aunque falle el import o una validación posterior;
- `cleanup_attempted` refleja el intento real;
- `cleanup_succeeded=false` agrega evidencia de fallo;
- no se reutiliza una base temporal previa;
- el nombre temporal se genera por corrida.

## Límites actuales

- usa una base temporal en el mismo servidor MySQL;
- no crea un contenedor o instancia aislada adicional;
- no soporta validators de negocio complejos ni una DSL avanzada;
- asume que el dump puede restaurarse en una base recién creada;
- DDL dependiente del entorno puede requerir adaptación futura;
- no soporta motores distintos de MySQL.
