# Contrato de `backupkit backup`

## Objetivo

Ejecutar un backup real del recurso configurado y dejar un artefacto verificable, pero sin entrar todavía en restore test ni validators.

## Flujo actual para MySQL

1. validaciones base del core
2. lock por `project/resource`
3. prechecks del adapter MySQL
4. `mysqldump`
5. compresión gzip
6. cálculo de sha256
7. escritura de metadata sidecar
8. escritura de `backup-report.json`

## Archivos generados

- `backup-report.json`
- `<project>__<resource>__<timestamp>.sql.gz`
- `<project>__<resource>__<timestamp>.sql.gz.metadata.json`

## Contrato mínimo de artefacto

```json
{
  "path": "./var/output/cargadores__mysql-main__20260330T120000Z.sql.gz",
  "size_bytes": 123456,
  "sha256": "...",
  "timestamp": "2026-03-30T12:00:00+00:00",
  "engine": "mysql",
  "resource": "mysql-main",
  "project": "cargadores",
  "duration_sec": 2.418,
  "status": "OK"
}
```

## Reporte de backup

Además de los campos base del reporte, `backup-report.json` incluye `artifact` cuando la corrida genera artefacto exitosamente.

## Checks actuales esperables

- `adapter.mysql.backup.dump`
- `adapter.mysql.backup.sha256`
- `adapter.mysql.backup.metadata`

## Relación con `verify-artifact`

El resultado de `backup` deja todo lo necesario para que una corrida posterior de `verify-artifact` valide técnicamente el artefacto y su sidecar.

## No cubre todavía

- restore test
- validators
- retención
- cifrado
- upload externo
