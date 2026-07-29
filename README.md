# backupkit

`backupkit` es un CLI operativo para ejecutar prechecks, backups MySQL reales, verificación técnica de artefactos y restore tests sobre bases temporales.

## Capacidades actuales

- CLI:
  - `backupkit precheck`
  - `backupkit backup`
  - `backupkit verify-artifact`
  - `backupkit restore-test`
- configuración mediante `.env` y `policy.yml`;
- core con registry de adapters;
- adapter MySQL;
- dump real con `mysqldump`;
- compresión gzip y cálculo SHA-256;
- metadata JSON por artefacto;
- reportes JSON `report_version = 2`;
- reportes históricos timestamped;
- restore temporal con cleanup;
- validators SQL declarativos;
- retención y housekeeping;
- Telegram para resultados `WARN` y `ERROR`;
- lock por `project/resource`.

## Contrato de dependencias

El core de `backupkit` es standalone y no depende de repositorios host.

```text
backupkit core -> Python + herramientas declaradas por adapter
backupkit core -X-> Pruebas
backupkit core -X-> Base
backupkit core -X-> otros módulos
```

Una interfaz web externa puede integrar sus reportes, pero no forma parte del CLI ni de su contrato de ejecución.

## Comandos

### `backupkit precheck`

Valida:

- configuración mínima;
- directorio de salida escribible;
- espacio libre;
- herramientas requeridas;
- lock disponible;
- adapter soportado;
- conectividad y autenticación MySQL.

```bash
./bin/backupkit precheck \
  --env ./examples/mysql-basic/backup/.env.backup \
  --policy ./examples/mysql-basic/backup/backup.policy.yml
```

### `backupkit backup`

Flujo MySQL:

1. ejecuta validaciones base;
2. adquiere el lock `project/resource`;
3. ejecuta `mysqldump`;
4. comprime con gzip;
5. calcula SHA-256;
6. escribe el sidecar de metadata;
7. escribe el reporte de corrida;
8. aplica housekeeping si está habilitado;
9. intenta notificar según policy.

```bash
./bin/backupkit backup \
  --env ./examples/mysql-basic/backup/.env.backup \
  --policy ./examples/mysql-basic/backup/backup.policy.yml
```

### `backupkit verify-artifact`

Valida:

- existencia y tamaño del artefacto;
- integridad gzip;
- sidecar parseable;
- SHA-256;
- coherencia de path, tamaño, engine, project y resource.

```bash
./bin/backupkit verify-artifact \
  --env ./examples/mysql-basic/backup/.env.backup \
  --policy ./examples/mysql-basic/backup/verify.policy.yml
```

### `backupkit restore-test`

Ejecuta un restore real sobre una base temporal MySQL:

- verifica primero el artefacto;
- crea una base con nombre único;
- restaura el dump `.sql.gz`;
- valida tablas críticas;
- ejecuta smoke queries;
- ejecuta validators SQL declarativos;
- clasifica resultados como `OK`, `WARN` o `ERROR`;
- ejecuta `DROP DATABASE IF EXISTS` en cleanup incluso ante error.

```bash
./bin/backupkit restore-test \
  --env ./examples/mysql-basic/backup/.env.backup \
  --policy ./examples/mysql-basic/backup/restore-test.policy.yml
```

## Policy canónica

Dentro de `artifact` existen únicamente estos nombres de entrada:

- `output_dir`;
- `path`;
- `metadata_path`.

`verify_path` y `verify_metadata_path` no forman parte del contrato y producen `core.config.unsupported=ERROR`.

Semántica de rutas:

- una ruta absoluta se usa directamente;
- una ruta relativa se resuelve respecto de `artifact.output_dir`;
- los artefactos y sidecars generados registran paths absolutos.

Ver el contrato completo en [`docs/policy.md`](docs/policy.md).

## Reporte JSON `v2`

El reporte tiene una única forma canónica:

```text
report_version
metadata
final_status
phases[]
artifacts[]
validators[]
notifications[]
housekeeping
final_summary
```

Los checks y detalles específicos de la fase se consumen desde:

```text
phases[0].evidence.checks[]
phases[0].evidence.restore_test
```

No se publican campos top-level alternativos como:

```text
status
summary
checks
artifact
restore_test
duration_sec
project
resource
command
phase
```

Ejemplo mínimo de consumo:

```python
import json
from pathlib import Path

report = json.loads(Path('backup-report.json').read_text(encoding='utf-8'))

assert report['report_version'] == 2
status = report['final_status']
command = report['metadata']['command']
checks = report['phases'][0]['evidence']['checks']
artifacts = report['artifacts']
```

Ver el schema documentado en [`docs/report-format.md`](docs/report-format.md).

## Códigos de salida

| Estado final | Código |
|---|---:|
| `OK` | `0` |
| `WARN` | `1` |
| `ERROR` | `2` |

## Salidas esperadas

En `artifact.output_dir`:

- `precheck-report.json`;
- `backup-report.json`;
- `verify-artifact-report.json`;
- `restore-test-report.json`;
- `<project>__<resource>__<timestamp>__<command>-report.json`;
- `<project>__<resource>__<timestamp>.sql.gz`;
- `<project>__<resource>__<timestamp>.sql.gz.metadata.json`.

## Contrato del sidecar de artefacto

El sidecar incluye:

- `path` absoluto;
- `metadata_path` absoluto;
- `size_bytes`;
- `sha256`;
- `timestamp`;
- `engine`;
- `resource`;
- `project`;
- `duration_sec`;
- `status`.

Este contrato es distinto del reporte de corrida `v2`; no deben mezclarse sus campos.

## Retención y housekeeping

La sección `retention` permite:

- conservar cantidades diferentes de backups exitosos y no exitosos;
- proteger el último backup válido conocido;
- ejecutar auditoría mediante `dry_run`;
- borrar artefactos y reportes de corridas elegibles;
- incluir evidencia de decisiones en `housekeeping`.

## Diseño

- el core selecciona el adapter mediante `resource.type`;
- la lógica MySQL vive en `adapters/mysql`;
- la verificación reusable de artefactos vive en `core/artifact.py`;
- todos los comandos comparten validación, lock, reporte, retención y notificación;
- `restore-test` ejecuta validators declarativos sin introducir lógica de dominio en el core.

## Integración como submódulo

El repositorio expone una superficie pública mínima para hosts PHP:

```text
module.php                         -> backupkit.manifest.v1
back/bootstrap.php                 -> health y lectura read-only
tests/fixtures/precheck-report.json -> fixture de integración
tests/test_php_contract.php        -> smoke standalone
```

Contrato de integración:

```text
nombre: backupkit
ruta: submodules/backupkit
tier esperado: tooling-server-backup
app deploy: no
preflight general: no bloqueante
HTTP writes: no
SuperAdmin propio: no
```

El bootstrap permite validar y resumir reportes `v2`, pero no expone funciones para ejecutar el CLI, editar policies, borrar artefactos o restaurar bases.

Validación local:

```bash
php -l module.php
php -l back/bootstrap.php
php -l tests/test_php_contract.php
php tests/test_php_contract.php
```

Resultado esperado:

```text
BACKUPKIT_PHP_CONTRACT_PASS
```

El contrato completo está en [`docs/pruebas-integration.md`](docs/pruebas-integration.md). Los cambios todavía requeridos en el host están separados en [`docs/pendientes/pruebas-host-integration.md`](docs/pendientes/pruebas-host-integration.md).

## Fuera del contrato actual

- motores distintos de MySQL;
- validators de negocio complejos;
- baseline histórico;
- cifrado o upload externo de artefactos;
- ejecución desde requests web;
- interfaz SuperAdmin propia.
