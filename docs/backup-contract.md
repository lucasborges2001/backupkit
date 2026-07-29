# Contrato de `backupkit backup`

## Objetivo

Ejecutar un backup real del recurso configurado y producir un artefacto verificable con sidecar de metadata.

## Flujo MySQL

1. valida la policy;
2. adquiere el lock `project/resource`;
3. ejecuta prechecks del adapter;
4. ejecuta `mysqldump`;
5. comprime la salida con gzip;
6. calcula SHA-256;
7. escribe metadata sidecar;
8. escribe el reporte `v2`;
9. ejecuta housekeeping cuando está habilitado;
10. intenta notificar según policy.

## Archivos generados

- `backup-report.json`;
- `<project>__<resource>__<timestamp>__backup-report.json`;
- `<project>__<resource>__<timestamp>.sql.gz`;
- `<project>__<resource>__<timestamp>.sql.gz.metadata.json`.

## Contrato del artefacto

```json
{
  "path": "/srv/backupkit/output/cargadores__mysql-main__20260330T120000Z.sql.gz",
  "metadata_path": "/srv/backupkit/output/cargadores__mysql-main__20260330T120000Z.sql.gz.metadata.json",
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

`path` y `metadata_path` se registran como paths absolutos.

## Reporte de corrida

Rutas canónicas:

```text
metadata.command = backup
final_status
artifacts[0]
phases[0].evidence.checks[]
housekeeping
notifications[]
```

No se publican `status`, `artifact` ni `checks` como campos top-level.

## Checks esperables

### Core

- `core.config.required`;
- `core.config.unsupported` cuando corresponda;
- `core.lock.available`;
- `core.output_dir.writable`;
- `core.free_space`;
- `core.tools.available`;
- `core.retention.housekeeping` cuando retention está habilitado;
- checks de notificación.

### Adapter MySQL

- `adapter.mysql.connectivity`;
- `adapter.mysql.auth`;
- `adapter.mysql.backup.dump`;
- `adapter.mysql.backup.sha256`;
- `adapter.mysql.backup.metadata`.

## Relación con otros comandos

`backup` produce la entrada requerida por:

- `verify-artifact`;
- `restore-test`.

`backup` no ejecuta automáticamente `restore-test`. Cada comando representa una corrida y una fase explícita diferente.

## Invariantes

- no publica un artefacto final si `mysqldump` falla;
- usa un archivo temporal `.part` antes del rename final;
- no deja el `.part` ante error controlado;
- el sidecar corresponde al artefacto final;
- el reporte siempre respeta `report_version = 2`;
- el código de salida deriva de `final_status`.

## Fuera del contrato actual

- múltiples motores además de MySQL;
- cifrado;
- upload externo;
- backup schema-only;
- exclusión declarativa de tablas;
- restore automático dentro del comando `backup`.
