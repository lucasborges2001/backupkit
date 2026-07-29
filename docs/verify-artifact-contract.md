# Contrato de `backupkit verify-artifact`

## Objetivo

Validar técnicamente un artefacto generado por `backupkit backup`, sin restaurarlo ni ejecutar validadores de negocio.

## Entrada esperada

Dentro de `artifact` se informa:

- `output_dir`;
- `path` o `metadata_path`.

Nombres canónicos:

```text
artifact.path
artifact.metadata_path
```

No se aceptan:

```text
artifact.verify_path
artifact.verify_metadata_path
```

Su presencia produce `core.config.unsupported=ERROR`.

## Semántica de rutas

- un path absoluto se usa directamente;
- un path relativo se resuelve respecto de `artifact.output_dir`;
- si solo se informa `path`, el sidecar se infiere agregando `.metadata.json`;
- si solo se informa `metadata_path`, `path` se obtiene desde la metadata.

Ejemplo relativo:

```yaml
artifact:
  output_dir: ./var/output
  path: mysql-basic__mysql-main__20260330T120000Z.sql.gz
  metadata_path: mysql-basic__mysql-main__20260330T120000Z.sql.gz.metadata.json
```

## Validaciones mínimas

- archivo existe;
- archivo no vacío;
- gzip válido si termina en `.gz`;
- metadata presente y parseable;
- SHA-256 presente;
- SHA-256 consistente;
- metadata coherente con:
  - path;
  - metadata path;
  - tamaño;
  - engine;
  - project;
  - resource;
  - timestamp;
  - duración no negativa.

## Clasificación

### `ERROR`

Fallas bloqueantes:

- path de entrada ausente;
- archivo faltante o vacío;
- gzip inválido;
- metadata ausente o ilegible;
- SHA-256 ausente o inconsistente;
- metadata incoherente;
- campo de policy retirado.

### `WARN`

Casos no bloqueantes:

- metadata con `status` distinto de `OK`;
- archivo no `.gz`, por lo que se omite la validación gzip.

## Salida

Archivos:

- `verify-artifact-report.json`;
- `<project>__<resource>__<timestamp>__verify-artifact-report.json`.

Rutas canónicas del resultado:

```text
final_status
artifacts[]
phases[0].evidence.checks[]
```

No se publican `status`, `artifact` ni `checks` como campos top-level.

## Checks esperables

- `core.config.unsupported` cuando la policy contiene campos retirados;
- `artifact.file.exists`;
- `artifact.file.nonempty`;
- `artifact.gzip.valid`;
- `artifact.metadata.present`;
- `artifact.metadata.parse`;
- `artifact.sha256.present`;
- `artifact.sha256.match`;
- `artifact.metadata.consistency`;
- `artifact.metadata.status`.

## Fuera de alcance

- restore test;
- validators de negocio;
- baseline histórico;
- verificación semántica completa del SQL;
- upload o cifrado del artefacto.
