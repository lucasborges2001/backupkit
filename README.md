# backupkit

Starter operativo de `backupkit` con **precheck funcional**, **backup MySQL real**, **verificación técnica de artefacto**, **restore test real sobre base temporal MySQL** y **validators SQL declarativos ejecutados sobre la restauración temporal**.

## Capacidades actuales

- CLI:
  - `backupkit precheck`
  - `backupkit backup`
  - `backupkit verify-artifact`
  - `backupkit restore-test`
- `.env` + `policy.yml`
- core reusable con registry de adapters
- adapter MySQL inicial
- reporte JSON por corrida
- metadata JSON por artefacto de backup
- Telegram solo para `WARN` y `ERROR`
- lock de ejecución por `project/resource`

## Qué soporta hoy

### `backupkit precheck`

Checks de:
- config mínima
- output dir escribible
- espacio libre
- herramientas requeridas
- conectividad TCP al recurso
- auth MySQL

### `backupkit backup`

Flujo real para MySQL:
- validaciones base equivalentes a `precheck`
- dump MySQL real con `mysqldump`
- compresión gzip
- cálculo de sha256
- metadata del artefacto en sidecar JSON
- integración con `backup-report.json`

### `backupkit verify-artifact`

Validación técnica del artefacto generado:
- archivo existe
- archivo no vacío
- gzip válido si aplica
- sha256 presente y consistente
- metadata presente y parseable
- metadata coherente con artefacto, engine, project y resource
- integración con `verify-artifact-report.json`

### `backupkit restore-test`

Restore real para MySQL sobre base temporal efímera:
- reutiliza `verify-artifact` antes de restaurar
- crea una base temporal con nombre único
- restaura el dump `.sql.gz` en esa base
- valida tablas críticas configurables
- ejecuta smoke queries configurables
- ejecuta validators SQL declarativos sobre la base restaurada
- clasifica fallos en `warning` o `error` según policy
- limpia con `DROP DATABASE IF EXISTS` incluso ante error
- integra resultado y cleanup en `restore-test-report.json`

## Qué no trae todavía

- validators de negocio complejos o específicos de dominio
- retención
- múltiples motores además de MySQL
- baseline histórico
- pipeline final completo

## Uso

### Precheck

```bash
./bin/backupkit precheck \
  --env ./examples/mysql-basic/backup/.env.backup \
  --policy ./examples/mysql-basic/backup/backup.policy.yml
```

### Backup

```bash
./bin/backupkit backup \
  --env ./examples/mysql-basic/backup/.env.backup \
  --policy ./examples/mysql-basic/backup/backup.policy.yml
```

### Verify artifact

```bash
./bin/backupkit verify-artifact \
  --env ./examples/mysql-basic/backup/.env.backup \
  --policy ./examples/mysql-basic/backup/verify.policy.yml
```

### Restore test

```bash
./bin/backupkit restore-test \
  --env ./examples/mysql-basic/backup/.env.backup \
  --policy ./examples/mysql-basic/backup/restore-test.policy.yml
```

## Salidas esperadas

En `artifact.output_dir`:

- `precheck-report.json`
- `backup-report.json`
- `verify-artifact-report.json`
- `restore-test-report.json`
- `<project>__<resource>__<timestamp>.sql.gz`
- `<project>__<resource>__<timestamp>.sql.gz.metadata.json`

## Contrato actual de artefacto

El sidecar metadata y el reporte incluyen al menos:

- `path`
- `size_bytes`
- `sha256`
- `timestamp`
- `engine`
- `resource`
- `project`
- `duration_sec`
- `status`

El reporte de `restore-test` agrega además:

- `restore_test.database`
- `restore_test.cleanup_attempted`
- `restore_test.cleanup_succeeded`
- `restore_test.critical_tables`
- `restore_test.smoke_queries`
- `restore_test.validators`
- `restore_test.validator_results`
- `restore_test.validators_summary`

## Diseño

El core no queda acoplado a MySQL más de lo necesario:

- el core resuelve el adapter por `resource.type`
- `precheck`, `backup`, `verify-artifact` y `restore-test` comparten validaciones base y lock
- la lógica de dump y restore real vive en el adapter MySQL
- la lógica reusable de validación de artefactos vive en `core/artifact.py`
- `restore-test` ya soporta validators SQL declarativos y deja abierto el camino para validators más ricos sin meter lógica de dominio en el core

## Notificación

Telegram se envía una vez por corrida y solo si el estado final es `WARN` o `ERROR`.
