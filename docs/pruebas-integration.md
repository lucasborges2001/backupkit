# Contrato de integracion con Pruebas

## Estado

`backupkit` queda preparado para ser incorporado como submodulo de tooling en `lucasborges2001/Pruebas`.

Este documento define el contrato que ya existe dentro de `backupkit`. No modifica ni declara completada el alta del gitlink en `Pruebas`.

## Identidad canonica

```text
Repositorio: lucasborges2001/backupkit
Nombre operativo: backupkit
Label visible: BackupKit
Ruta futura: submodules/backupkit
Branch: main
Tipo: tooling-server-backup
```

No usar `Backupkit`, `BackupKit` o una ruta con mayusculas como identidad tecnica alternativa.

## Clasificacion esperada

`backupkit` no es un `runtime-app`.

Clasificacion objetivo en el host:

```text
tier: tooling-server-backup
required_for_preflight: false
include_in_app_deploy: false
tooling: true
optional: true
```

Motivo:

- ejecuta tareas operativas fuera del runtime web;
- no debe bloquear el deploy de la aplicacion;
- no debe ejecutarse desde requests HTTP;
- puede faltar sin impedir que la aplicacion principal responda;
- su estado debe ser visible y diagnosticable cuando se configure.

## Archivos publicos del submodulo

| Archivo | Contrato |
|---|---|
| `module.php` | manifest `backupkit.manifest.v1` para discovery del host |
| `back/bootstrap.php` | funciones PHP read-only para manifest, health y reportes |
| `bin/backupkit` | CLI operativo; nunca debe invocarse desde una request web |
| `docs/report-format.md` | schema canonico `backupkit.report.v2` |
| `tests/fixtures/precheck-report.json` | fixture estable para smoke del host |
| `tests/test_php_contract.php` | smoke standalone del contrato PHP |

## Dependencias

Contrato vigente:

```text
backupkit core -> ninguna dependencia de repositorio
bootstrap PHP -> ninguna dependencia de repositorio
backupkit -X-> Pruebas
backupkit -X-> Base
backupkit -X-> otros submodulos
```

`Base` solo sera una dependencia permitida si en una fase posterior se agrega una interfaz SuperAdmin dentro del propio submodulo. La integracion inicial no requiere UI propia ni dependencia de `Base`.

## Manifest

`module.php` declara:

- tooling backend-only;
- CLI operativo;
- lectura de reportes;
- health backend read-only;
- ausencia de rutas publicas;
- ausencia de API HTTP;
- ausencia de SuperAdmin;
- ausencia de contratos write para el host;
- ausencia de dependencias de repositorio.

El manifest diferencia:

```text
operational_writes = true
http_writes = false
```

Los writes operativos pertenecen exclusivamente al CLI ejecutado por cron, systemd o un operador autorizado. El contrato PHP del host es read-only.

## Bootstrap PHP read-only

El host puede cargar:

```php
$bootstrap = require $root . '/submodules/backupkit/back/bootstrap.php';
```

Funciones publicas:

```text
backupkit_module_root()
backupkit_manifest()
backupkit_report_validate(array $report)
backupkit_report_load(string $path)
backupkit_report_summary(array $report)
backupkit_health_payload(?string $reportPath)
```

### `backupkit_report_load`

Invariantes:

- requiere un archivo regular y legible;
- rechaza symlinks;
- requiere un nombre terminado en `-report.json`;
- limita el archivo a 2 MiB;
- exige JSON valido;
- exige exactamente `report_version = 2`;
- rechaza campos legacy o campos no soportados;
- no ejecuta comandos;
- no lee `.env` ni policies;
- no modifica archivos.

### `backupkit_report_summary`

Produce una vista apta para UI o diagnostico agregado:

- elimina paths absolutos de artefactos;
- no expone SQL de validators;
- no expone checks crudos;
- no expone fases crudas;
- conserva estado, duracion, conteos, artefactos sanitizados, validators sanitizados y cleanup.

La UI futura debe consumir este summary y no imprimir el reporte crudo directamente.

### `backupkit_health_payload`

Expone:

- disponibilidad del modulo;
- presencia y bit ejecutable del CLI;
- contratos disponibles;
- declaracion explicita `http_execution = false`;
- summary del ultimo reporte cuando el host configura una ruta valida.

Un ultimo backup `ERROR` no habilita ejecucion desde HTTP. Solo informa estado operativo.

## Configuracion esperada en Pruebas

La ruta del reporte debe ser configurada por el host y permanecer fuera de `public_html`.

Ejemplo conceptual:

```text
BACKUPKIT_REPORT_PATH=/srv/backupkit/output/backup-report.json
```

La integracion no debe buscar reports recorriendo el filesystem ni aceptar una ruta proporcionada por query string o formulario.

## Entrada candidata en `config/submodules.php`

Esta entrada pertenece a una fase futura en `Pruebas` y no fue aplicada por este cambio:

```php
[
    'name' => 'backupkit',
    'path' => 'submodules/backupkit',
    'url' => 'https://github.com/lucasborges2001/backupkit.git',
    'branch' => 'main',
    'tier' => 'tooling-server-backup',
    'required_for_preflight' => false,
    'required_paths' => [
        'module.php',
        'back/bootstrap.php',
        'bin/backupkit',
    ],
    'include_in_app_deploy' => false,
    'tooling' => true,
    'optional' => true,
    'notes' => 'Tooling standalone de backup MySQL, verificacion y restore-test; integracion host exclusivamente read-only mediante reportes v2.',
],
```

## Flujo permitido

```text
cron/systemd/operador
  -> bin/backupkit
  -> report JSON v2 fuera de public_html
  -> adapter host configura una ruta fija
  -> back/bootstrap.php valida y resume
  -> health o SuperAdmin agregado muestran estado read-only
```

## Flujos prohibidos

```text
HTTP -> shell_exec(bin/backupkit backup)
HTTP -> shell_exec(bin/backupkit restore-test)
HTTP -> path elegido por usuario -> backupkit_report_load()
Pruebas -> importar internals Python
Pruebas -> editar policy o secretos
SuperAdmin -> borrar artefactos
SuperAdmin -> descargar dumps
```

## Smoke standalone

Comando esperado:

```bash
php tests/test_php_contract.php
```

Resultado esperado:

```text
BACKUPKIT_PHP_CONTRACT_PASS
```

El smoke verifica:

- manifest;
- ausencia de dependencias;
- capacidades backend/tooling;
- ausencia de HTTP writes;
- carga del fixture `v2`;
- rechazo de campos legacy;
- rechazo de nombres que no terminan en `-report.json`;
- summary sanitizado;
- health read-only.

## Smoke futuro en Pruebas

El host debe validar como minimo:

1. el submodulo existe en la ruta declarada;
2. `module.php` y `back/bootstrap.php` cargan;
3. el fixture del submodulo satisface el contrato;
4. el summary no expone paths absolutos ni SQL;
5. falta de report configurado degrada de forma informativa y no bloquea la app;
6. un report invalido no se interpreta como `ready`;
7. no existe ruta HTTP capaz de ejecutar el CLI.

## Criterio de preparacion del repositorio

`backupkit` esta preparado para el alta cuando:

```text
[ ] python3 -m compileall -q core adapters tests
[ ] python3 -m unittest discover -s tests -p 'test_*.py' -v
[ ] php -l module.php
[ ] php -l back/bootstrap.php
[ ] php -l tests/test_php_contract.php
[ ] php tests/test_php_contract.php
[ ] git diff --check
[ ] branch validada y mergeada en backupkit/main
```

Hasta ejecutar esas validaciones y mergear la rama, el codigo esta implementado pero el SHA integrable definitivo no esta cerrado.
