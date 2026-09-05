# Contrato de integración con Pruebas

## Estado

```text
OWNER_CONTRACT: MERGED
HOST_INTEGRATION: MERGED
STRUCTURE_PROFILE_OVERRIDE: IMPLEMENTADO
STRUCTURE_AUDIT_REMOTE_POST_FIX: PENDIENTE
```

`backupkit` ya está incorporado como submódulo opcional de tooling en `lucasborges2001/Pruebas`.

Checkpoint relevante:

```text
backupkit: 07f9eaa97791ec904833bf32d959a903ce43eff9
Pruebas:   00531dd73c40de16a76df280e019d4a46a2cfec0
Base:      a357c4469542573fbaa4b38727a29645b3d77fde
TestKit:   b61d8b16ecba682cc8816060e657230051ea1c54
```

El host fija `submodules/backupkit` exactamente en el SHA owner anterior para la corrección estructural documentada el 2026-09-04/05.

## Identidad canónica

```text
Repositorio: lucasborges2001/backupkit
Nombre operativo: backupkit
Label visible: BackupKit
Ruta host: submodules/backupkit
Branch: main
Tipo: tooling-server-backup
```

No usar variantes de mayúsculas como identidad técnica alternativa.

## Clasificación

BackupKit no es `runtime-app` ni un módulo funcional del host.

Clasificación vigente:

```text
tier: tooling-server-backup
required_for_preflight: false
include_in_app_deploy: false
tooling: true
optional: true
```

Motivo:

- ejecuta tareas operativas fuera del runtime web;
- no bloquea el deploy de la aplicación;
- no debe ejecutarse desde requests HTTP;
- puede faltar sin impedir que la aplicación principal responda;
- su estado puede integrarse mediante reportes read-only.

## Perfil estructural owner-owned

La raíz del repositorio declara:

```text
.structure-audit-profile
```

con contenido:

```text
external-tooling
```

Este archivo existe porque la presencia de `back/` corresponde al bootstrap PHP read-only y no convierte BackupKit en un módulo funcional.

El auditor de `Pruebas` soporta este contrato mediante un override genérico durante detección `auto`. El valor debe ser un perfil válido, no puede ser `auto` y cualquier declaración inválida falla cerrado.

No crear documentación ficticia como:

```text
docs/estructura-modulo.md
docs/contrato-host-modulo.md
docs/checklists/auditoria-modularidad-modulo.md
```

solo para satisfacer una clasificación errónea.

## Superficie pública del submódulo

| Archivo | Contrato |
|---|---|
| `.structure-audit-profile` | Perfil estructural explícito `external-tooling` para auditores compatibles. |
| `module.php` | Manifest `backupkit.manifest.v1` para discovery del host. |
| `back/bootstrap.php` | Funciones PHP read-only para manifest, health y reportes. |
| `bin/backupkit` | CLI operativo; nunca debe invocarse desde una request web. |
| `docs/report-format.md` | Schema canónico `backupkit.report.v2`. |
| `tests/fixtures/precheck-report.json` | Fixture estable para smoke del host. |
| `tests/test_php_contract.php` | Smoke standalone del contrato PHP. |

## Dependencias

Contrato vigente:

```text
backupkit core -> ninguna dependencia de repositorio
bootstrap PHP -> ninguna dependencia de repositorio
backupkit -X-> Pruebas
backupkit -X-> Base
backupkit -X-> otros submódulos
```

`Base` solo sería una dependencia permitida si una fase posterior agrega una interfaz propia que lo justifique. La integración actual no requiere dependencia runtime de Base.

## Manifest

`module.php` declara:

- tooling backend-only;
- CLI operativo;
- lectura de reportes;
- health backend read-only;
- ausencia de rutas públicas;
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

Funciones públicas:

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
- exige JSON válido;
- exige exactamente `report_version = 2`;
- rechaza campos legacy o no soportados;
- no ejecuta comandos;
- no lee `.env` ni policies;
- no modifica archivos.

### `backupkit_report_summary`

Produce una vista apta para UI o diagnóstico agregado:

- elimina paths absolutos de artefactos;
- no expone SQL de validators;
- no expone checks/fases crudos;
- conserva estado, duración, conteos, artefactos sanitizados, validators sanitizados y cleanup.

### `backupkit_health_payload`

Expone disponibilidad del módulo, presencia del CLI, contratos disponibles, `http_execution = false` y summary sanitizado del último reporte cuando el host configura una ruta válida.

Un último backup `ERROR` no habilita ejecución desde HTTP. Solo informa estado operativo.

## Integración vigente en Pruebas

Pruebas registra BackupKit como submódulo opcional y expone un adapter read-only.

La ruta del reporte debe configurarse fuera de `public_html`, por ejemplo:

```text
BACKUPKIT_REPORT_ROOT=/var/lib/backupkit/mysql-main/output
BACKUPKIT_REPORT_PATH=/var/lib/backupkit/mysql-main/output/backup-report.json
```

La integración no debe descubrir reportes recorriendo el filesystem ni aceptar una ruta proporcionada por query string, formulario o cookie.

## Flujo permitido

```text
cron/systemd/operador
  -> bin/backupkit
  -> report JSON v2 fuera de public_html
  -> adapter host con ruta fija
  -> back/bootstrap.php valida y resume
  -> health o UI agregada muestran estado read-only
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

## Smokes

Owner:

```bash
php tests/test_php_contract.php
```

Host:

```bash
bash scripts/smoke/run_testkit.sh backupkit_contract
bash scripts/quality/audit_structure.sh submodules/backupkit
```

Estos gates no prueban MySQL real, restore-test real, retención real, scheduler ni deploy productivo.

## Estado de Structure Audit

El reporte remoto histórico anterior a `.structure-audit-profile` clasificó BackupKit como `module` y falló por tres documentos de módulo faltantes. Ese reporte pertenece al SHA anterior y no certifica el estado actual.

La corrección está implementada en el owner y en el auditor de Pruebas, pero falta un nuevo ciclo remoto que demuestre:

```text
PIPELINE REMOTO: PASS
VALIDACIÓN PRODUCTO: PASS
profile: external-tooling
DOC_REQUIRED_MISSING de module: 0
```

Los warnings de tamaño, función larga y header observados en el reporte anterior no fueron corregidos por este cambio y deben seguir visibles si reaparecen.

## Rollback

Para retirar la integración host, Pruebas debe revertir su adapter/configuración/gitlink sin copiar lógica dentro de este repositorio.

Para retirar únicamente el perfil estructural, revertir `.structure-audit-profile` solo junto con una decisión explícita de reclasificación y sin sustituirlo por documentación ficticia.

Los artifacts/reportes operativos externos no deben borrarse como parte de un rollback de código.

## No habilitado

- deploy productivo;
- scheduler;
- SuperAdmin;
- endpoints HTTP write;
- descarga de dumps;
- backup/restore desde UI;
- credenciales versionadas;
- certificación remota post-fix del perfil estructural.
