# Contrato de `restore-test`

## Objetivo

`restore-test` demuestra que un artefacto de backup ya generado:

- existe
- es técnicamente válido
- puede restaurarse en una base temporal MySQL
- deja disponibles tablas críticas esperadas
- permite ejecutar consultas simples post-restore
- puede ejecutar validators SQL declarativos sobre la restauración temporal
- puede limpiarse al final

## Flujo

1. validación de config y lock
2. validación de output dir, espacio y tools
3. `verify-artifact` interno sobre el artefacto objetivo
4. creación de base temporal efímera
5. import del dump `.sql.gz` usando `mysql`
6. chequeo de tablas críticas configuradas
7. ejecución de smoke queries configuradas
8. ejecución de validators SQL declarativos configurados
9. cleanup con `DROP DATABASE IF EXISTS` en `finally`
10. escritura de `restore-test-report.json`

## Configuración mínima

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
  path: ./var/output/mysql-basic__mysql-main__20260330T120000Z.sql.gz
  metadata_path: ./var/output/mysql-basic__mysql-main__20260330T120000Z.sql.gz.metadata.json

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
```

## Resultado esperado

### Exit codes

- `0` => restore test OK
- `1` => warnings no bloqueantes
- `2` => error bloqueante

### Reporte

Además del contrato base de `RunReport`, se emite:

```json
{
  "restore_test": {
    "database": "bkrt_mysql_basic_mysql_main_20260330t120000z",
    "artifact_path": "...sql.gz",
    "cleanup_attempted": true,
    "cleanup_succeeded": true,
    "critical_tables": ["users"],
    "smoke_queries": ["SELECT 1;"],
    "validators": [{"id": "users_non_zero", "sql": "SELECT COUNT(*) FROM users;", "expected": {"rule": "non_zero"}, "severity": "error"}],
    "validator_results": [{"id": "users_non_zero", "status": "OK", "actual_value": 42}],
    "validators_summary": {"total": 1, "ok": 1, "warn": 0, "error": 0}
  }
}
```

## Límites actuales

- usa una base temporal en el mismo servidor MySQL configurado
- no crea todavía contenedor efímero ni instancia aislada aparte
- no soporta validators de negocio complejos ni una DSL avanzada
- asume que el dump puede restaurarse directamente en una DB recién creada
- si el dump incluye `USE otra_db` o DDL muy específico del entorno, la restauración dependerá de ese formato

## Reglas soportadas hoy

- `equals`
- `greater_than`
- `less_than`
- `zero`
- `non_zero`

La severidad del validator controla el impacto en el resultado final:

- `severity: error` => el fallo degrada a `ERROR`
- `severity: warning` => el fallo degrada a `WARN`

## Punto de extensión siguiente

Sobre esta base se pueden montar luego:

- validators más ricos sin contaminar el core
- entornos efímeros más aislados
- matrices multi-engine
- políticas de cleanup y retención más avanzadas
