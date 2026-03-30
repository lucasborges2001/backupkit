# Contrato de `backupkit verify-artifact`

## Objetivo

Validar técnicamente un artefacto ya generado por `backupkit backup`, sin restaurarlo ni ejecutar validadores de negocio.

## Entrada esperada

En `policy.yml`, dentro de `artifact`, se debe informar al menos una de estas opciones:

- `path`
- `metadata_path`

También se aceptan:

- `verify_path`
- `verify_metadata_path`

Si solo se informa `path`, el sistema intenta inferir el sidecar con sufijo `.metadata.json`.
Si solo se informa `metadata_path`, el sistema intenta resolver el `path` desde la metadata.

## Validaciones mínimas

- archivo existe
- archivo no vacío
- gzip válido si el archivo termina en `.gz`
- metadata presente y parseable
- sha256 presente en metadata
- sha256 consistente con el archivo
- metadata coherente con:
  - path
  - tamaño
  - engine
  - project
  - resource

## Clasificación actual

### `ERROR`

Se usa para fallas bloqueantes como:
- archivo faltante
- archivo vacío
- gzip inválido
- metadata faltante o ilegible
- sha256 ausente
- sha256 inconsistente
- metadata incoherente con el artefacto o con la corrida

### `WARN`

Se usa para casos no bloqueantes, por ejemplo:
- metadata con `status` distinto de `OK`
- archivo no `.gz`, donde la validación de gzip se omite

## Salida

- `verify-artifact-report.json`
- `artifact` embebido en el reporte si la metadata pudo parsearse

## Checks actuales esperables

- `artifact.file.exists`
- `artifact.file.nonempty`
- `artifact.gzip.valid`
- `artifact.metadata.present`
- `artifact.metadata.parse`
- `artifact.sha256.present`
- `artifact.sha256.match`
- `artifact.metadata.consistency`
- `artifact.metadata.status`

## No cubre todavía

- restore test
- validators de negocio
- baseline histórico
- verificación de contenido SQL más allá de la integridad técnica del artefacto
