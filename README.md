# backupkit

Starter operativo de `backupkit` con **precheck funcional**, **backup MySQL real** y **verificación técnica de artefacto**.

## Capacidades actuales

- CLI:
  - `backupkit precheck`
  - `backupkit backup`
  - `backupkit verify-artifact`
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

## Qué no trae todavía

- restore test
- validators SQL o de negocio
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

## Salidas esperadas

En `artifact.output_dir`:

- `precheck-report.json`
- `backup-report.json`
- `verify-artifact-report.json`
- `<project>__<resource>__<timestamp>.sql.gz`
- `<project>__<resource>__<timestamp>.sql.gz.metadata.json`

## Contrato actual de artefacto

El sidecar metadata y el reporte de `backup` o `verify-artifact` incluyen al menos:

- `path`
- `size_bytes`
- `sha256`
- `timestamp`
- `engine`
- `resource`
- `project`
- `duration_sec`
- `status`

## Política actual

Ver:

- `docs/policy.md`
- `docs/precheck-contract.md`
- `docs/backup-contract.md`
- `docs/verify-artifact-contract.md`
- `docs/roadmap.md`

## Exit codes

- `0` => OK
- `1` => WARN
- `2` => ERROR

## Diseño

El core no queda acoplado a MySQL más de lo necesario:

- el core resuelve el adapter por `resource.type`
- `precheck`, `backup` y `verify-artifact` comparten validaciones base y lock
- la lógica de dump real vive en el adapter MySQL
- la lógica reusable de validación de artefactos vive en `core/artifact.py`

## Notificación

Telegram se envía una vez por corrida y solo si el estado final es `WARN` o `ERROR`.
