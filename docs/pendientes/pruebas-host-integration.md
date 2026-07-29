# Pendiente externo — Alta de backupkit en Pruebas

## Estado

Pendiente externo. No implementado en `lucasborges2001/Pruebas`.

`backupkit` ya incorpora el manifest, bootstrap read-only, fixture y smoke necesarios para preparar el alta. Este archivo registra exclusivamente los cambios que pertenecen al host integrador.

## Repositorio propietario

```text
lucasborges2001/Pruebas
```

No resolver estas tareas copiando archivos dentro de `backupkit` ni agregando dependencias desde `backupkit` hacia el host.

## Objetivo

Agregar `lucasborges2001/backupkit` como submodulo opcional de tooling del servidor y permitir que `Pruebas` muestre su estado mediante reportes JSON `v2`, sin ejecutar operaciones de backup o restore desde HTTP.

## Dependencias

```text
Fase 0: backupkit/main validado y con SHA integrable
Fase 1: alta del gitlink y manifest host
Fase 2: adapter host read-only
Fase 3: smoke/TestKit
Fase 4: documentacion operativa
Fase 5 opcional: SuperAdmin agregado usando Base
```

La Fase 5 no bloquea las fases 1 a 4.

## Fase 0 — Cerrar SHA integrable en backupkit

Repositorio: `lucasborges2001/backupkit`.

Validaciones requeridas:

```bash
python3 -m compileall -q core adapters tests
python3 -m unittest discover -s tests -p 'test_*.py' -v
php -l module.php
php -l back/bootstrap.php
php -l tests/test_php_contract.php
php tests/test_php_contract.php
git diff --check
```

Criterio PASS:

```text
[ ] suites Python PASS
[ ] lint PHP PASS
[ ] BACKUPKIT_PHP_CONTRACT_PASS
[ ] rama mergeada en backupkit/main
[ ] SHA final registrado
[ ] working tree limpio
```

Criterio FAIL:

- integrar un SHA de rama no validado;
- integrar un commit anterior al manifest/bootstrap;
- integrar con tests omitidos sin bloqueo documentado.

## Fase 1 — Alta del submodulo en Pruebas

Archivos esperados en `Pruebas`:

```text
.gitmodules
config/submodules.php
submodules/backupkit  # gitlink
```

Identidad exacta:

```text
name: backupkit
path: submodules/backupkit
url: https://github.com/lucasborges2001/backupkit.git
branch: main
```

Clasificacion:

```text
tier: tooling-server-backup
required_for_preflight: false
include_in_app_deploy: false
tooling: true
optional: true
```

`required_paths`:

```text
module.php
back/bootstrap.php
bin/backupkit
```

Criterio PASS:

```text
[ ] .gitmodules y config/submodules.php coinciden 1 a 1
[ ] gitlink apunta al SHA validado de backupkit/main
[ ] no cambia otro gitlink
[ ] no entra al app deploy
[ ] no bloquea el preflight general
[ ] ausencia del submodulo degrada como tooling opcional
```

## Fase 2 — Adapter host read-only

Responsabilidad de `Pruebas`:

- resolver una ruta fija de reporte mediante configuracion del servidor;
- cargar `submodules/backupkit/back/bootstrap.php`;
- usar `backupkit_health_payload()` para health agregado;
- usar `backupkit_report_summary()` para cualquier representacion visual;
- capturar excepciones y devolver estado degradado sanitizado;
- no imprimir el reporte crudo en una respuesta web.

Contrato de configuracion sugerido:

```text
BACKUPKIT_REPORT_PATH=/srv/backupkit/output/backup-report.json
```

Restricciones:

- la ruta no puede venir de request, query string, formulario o cookie;
- el archivo debe permanecer fuera de `public_html`;
- no recorrer directorios para descubrir reports;
- no importar internals Python;
- no leer `.env.backup` desde el host web;
- no ejecutar el CLI desde PHP.

Criterio PASS:

```text
[ ] sin ruta configurada => unavailable/degraded informativo
[ ] report v2 valido => summary read-only
[ ] report invalido => degraded, nunca ready
[ ] excepcion no filtra paths ni secretos al cliente
[ ] no existe shell_exec/proc_open/system/passthru para backupkit
```

## Fase 3 — Smoke y TestKit

Archivos candidatos en `Pruebas`:

```text
config/testkit-suites.php
test/smoke/backupkit_contract.php
```

El smoke host debe consumir:

```text
submodules/backupkit/tests/fixtures/precheck-report.json
```

Cobertura minima:

1. manifest accesible;
2. bootstrap accesible;
3. dependencia de repositorio vacia;
4. fixture `v2` valido;
5. campo legacy rechazado;
6. summary sin paths absolutos;
7. summary sin SQL;
8. health sin ejecucion HTTP;
9. modulo faltante no bloquea la app;
10. report invalido no produce ready.

No considerar este smoke como prueba de backup MySQL real. La ejecucion real permanece en las suites propias de `backupkit` y en un entorno descartable.

Criterio PASS:

```text
[ ] suite backupkit_contract registrada
[ ] smoke aislado PASS
[ ] host_integrated incluye la suite si corresponde
[ ] resultado distingue fixture de ejecucion real
```

## Fase 4 — Documentacion operativa en Pruebas

Archivos candidatos:

```text
README.md
docs/operacion/submodulos.md
docs/integraciones/backupkit.md
docs/cambios/<fecha>-backupkit.md
```

La documentacion debe declarar:

- tooling opcional;
- ejecucion fuera del runtime web;
- ruta de reports fuera de `public_html`;
- contratos `backupkit.manifest.v1`, `backupkit.report.v2` y `backupkit.health.v1`;
- ausencia de UI propia;
- ausencia de HTTP writes;
- scheduling externo;
- limites y rollback.

Criterio PASS:

```text
[ ] no se promete SuperAdmin si no existe
[ ] no se documenta ejecucion desde HTTP
[ ] no se documentan aliases o campos legacy
[ ] docs coinciden con config/submodules.php
```

## Fase 5 — SuperAdmin agregado opcional

Esta fase pertenece a `Pruebas` y `Base`, no al core standalone de `backupkit`.

Arquitectura permitida:

```text
Base -> auth, layout y componentes reusables
Pruebas -> adapter y composicion del panel
backupkit -> manifest, health y summary read-only
```

Primera version permitida:

- estado del ultimo reporte;
- proyecto y recurso;
- comando;
- duracion;
- conteos OK/WARN/ERROR;
- nombre y tamaño del artefacto sin path absoluto;
- cleanup de restore-test;
- validators sanitizados;
- housekeeping resumido.

Acciones prohibidas:

- iniciar backup;
- iniciar restore-test;
- borrar artefactos;
- editar policy;
- editar secretos;
- descargar dumps;
- elegir paths arbitrarios;
- ejecutar SQL.

Criterio PASS:

```text
[ ] solo lectura
[ ] usa componentes publicos de Base
[ ] no agrega dependencia Base al core Python
[ ] no expone paths absolutos ni SQL
[ ] no registra acciones write
```

## Rollback

Orden de rollback en `Pruebas`:

1. deshabilitar adapter/panel host;
2. retirar suite host si depende del gitlink;
3. revertir entrada de `config/submodules.php`;
4. revertir `.gitmodules` y gitlink en el mismo cambio controlado;
5. conservar los reportes y configuracion operativa fuera del repo;
6. no borrar artefactos de backup como parte del rollback de codigo.

## Criterio de cierre total

```text
[ ] backupkit/main contiene el contrato validado
[ ] Pruebas registra el submodulo como tooling opcional
[ ] adapter host es read-only
[ ] TestKit host PASS
[ ] docs operativas actualizadas
[ ] no hay ejecucion CLI desde HTTP
[ ] no hay dependencia directa backupkit -> Pruebas
[ ] SuperAdmin, si existe, permanece read-only
```
