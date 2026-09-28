# Pendiente — Cutover de BackupKit en PlataformaCarga

## Estado

```text
TYPE=OWNER_CONSUMER_CUTOVER_PENDING
OWNER=lucasborges2001/backupkit
OWNER_SHA=8d497912fc601f2d4bf8a4ce53b779dc13990b4f
CONSUMER=lucasborges2001/PlataformaCarga
OWNER_IMPLEMENTATION=HARDENED
OWNER_EXACT_SHA_SUITE=PASS_R34
OWNER_PYTHON_SUITE=PASS_51_TESTS
OWNER_PHP_CONTRACT=PASS
HOST_PINNED=PASS
HOST_READONLY_WIRING=PASS_R34
REMOTE_PIPELINE_R34=PASS
REMOTE_PRODUCT_R34=FAIL_HOST_PREFLIGHT
REMOTE_R35=NO_EJECUTADO_NO_CLAIM
REMOTE_VALIDATION=PENDING_RETRY_AFTER_HOST_HARNESS_FIX
DUPLICATE_REMOVAL=BLOCKED
PRODUCTION_ENABLED=NO
```

## Objetivo

Formalizar a BackupKit como owner único de las capacidades genéricas de backup
MySQL, verificación técnica de artifacts, restore-test, housekeeping/retención,
locks y reportes; demostrar paridad real desde el host consumidor y sólo
después retirar las capacidades equivalentes de `PlataformaCarga`.

Este documento no convierte a `PlataformaCarga` en dependencia de
`Pruebas`. La integración se realiza directamente mediante el gitlink y los
contratos públicos de BackupKit.

## Implementación owner ya realizada

El SHA vigente incorpora, entre otros invariantes:

- publicación atómica y no-overwrite de artifacts/sidecars/reportes;
- directorios privados y archivos generados privados;
- credenciales MySQL mediante option-file temporal, sin password en argv;
- flags de dump compatibles con el baseline previamente validado por el host;
- `verify-artifact` con size, SHA-256 y gzip;
- rechazo fail-closed de symlinks en artifacts, metadata y locks;
- lock advisory por proyecto/recurso con directorio privado;
- restore-test con SQL configurable limitado a lectura;
- cleanup fallido como error terminal;
- descompresión acotada por chunks, sin materializar el dump completo en RAM;
- housekeeping `dry_run=true` por defecto;
- protección del último backup válido, antigüedad mínima y requisito de backup
  verificado más nuevo;
- revalidación de integridad antes de borrar;
- eliminación del runtime Bash legacy duplicado dentro del propio BackupKit.

## Evidencia disponible

El host consumidor fijó el owner por gitlink en:

```text
backupkit=8d497912fc601f2d4bf8a4ce53b779dc13990b4f
```

`PlataformaCarga` tiene wiring read-only para:

```text
backupkit.manifest.v1
backupkit.report.v2
backupkit.health.v1
backupkit.deploy.v1
```

El request `plataformacarga-backupkit-cutover-20260928-r34` probó
`backupkit@8d497912fc601f2d4bf8a4ce53b779dc13990b4f` materializado por gitlink,
lock y config efectivos. El pipeline remoto fue `PASS`; la suite Python del
owner ejecutó 51 tests con resultado `OK`, el contrato PHP owner fue `PASS`
y el contrato read-only del host fue `PASS`.

La validación de producto r34 terminó `FAIL` antes de iniciar MySQL descartable
porque el harness consumidor conservaba un expected SHA histórico. Ese fallo
pertenecía al host, no al owner. `PlataformaCarga` corrigió el harness para
derivar y comparar gitlink=lock=checkout materializado.

El request posterior r35, dirigido al estado host con ese fix, no obtuvo claim
durante la ventana de observación y fue deshabilitado. Por tanto:

```text
R34_OWNER_EXACT_SHA_SUITE=PASS
R34_PIPELINE_REMOTE=PASS
R34_PRODUCT_VALIDATION=FAIL_HOST_PREFLIGHT
R34_DISPOSABLE_MYSQL=NOT_RUN
R35_CLAIM=NOT_OBSERVED
R35_PIPELINE_REMOTE=NO_EJECUTADO
R35_PRODUCT_VALIDATION=NO_EJECUTADA
```

## Validación exacta del owner

El SHA actual ya tiene evidencia ejecutada proporcional desde el gate remoto del
consumidor:

```text
OWNER_SHA=8d497912fc601f2d4bf8a4ce53b779dc13990b4f
python3 -m compileall -q core adapters tests=PASS
python3 -m unittest discover -s tests -p 'test_*.py' -v=PASS_51_TESTS
php tests/test_php_contract.php=PASS
EVIDENCE_SOURCE=PlataformaCarga r34
```

GitHub Actions no produjo un run nuevo para este SHA; esa ausencia no invalida
la evidencia ejecutada de r34, pero tampoco debe presentarse como CI PASS.

## Validaciones pendientes desde PlataformaCarga

El gate consumidor debe probar el mismo SHA exacto con infraestructura
descartable:

```text
[x] owner pin exacto — PASS r34
[x] suite Python owner — PASS r34, 51 tests
[x] contrato PHP owner — PASS r34
[x] contrato read-only host — PASS r34
[ ] backup real contra MySQL 8.4 descartable
[ ] verify-artifact PASS
[ ] restore-test PASS
[ ] cleanup de DB temporal comprobado
[ ] restore independiente sobre segunda instancia MySQL limpia
[ ] fingerprint estructural source/target equivalente
[ ] conteos/invariantes del fixture equivalentes
[ ] verificación de Base/Cargador por contratos públicos
[ ] restore negativo rechazado
[ ] volúmenes y artifacts descartables limpiados
[ ] pipeline_status=PASS
[ ] product_status=PASS
```

Un request `enabled`, `queued` o sin claim no satisface el gate.

## Cutover después del PASS

Con evidencia exacta, el cambio pertenece al host consumidor:

1. refactorizar el harness de recuperación para invocar únicamente el CLI
   público de BackupKit para backup/verify/restore;
2. conservar en `PlataformaCarga` sólo la orquestación de recuperación y los
   verificadores específicos de owners;
3. retirar `mysql_backup_create.sh` y `mysql_backup_retention.sh` cuando
   ya no tengan consumidores;
4. retirar o reemplazar suites/runners históricos de backup/retención que hayan
   quedado redundantes;
5. ejecutar nuevamente contratos y recuperación descartable sobre el estado
   **sin duplicación**;
6. documentar los SHAs anterior/nuevo y la evidencia terminal.

No copiar internals Python de BackupKit al host y no habilitar ejecución CLI por
HTTP.

## Pendientes que NO cierra este cutover

Aunque el cutover técnico dé PASS, continúan separados:

- scheduler productivo;
- credenciales reales y su rotación;
- storage persistente/externo;
- valores productivos de retención;
- retención destructiva;
- RPO/RTO;
- cifrado/replicación cuando la política lo requiera;
- canary y deploy productivo;
- runbook operacional de recuperación;
- recuperación de datos/artifacts fuera del alcance MySQL.

Estos puntos pertenecen al gate
[`operacion-produccion.md`](operacion-produccion.md) y a las políticas del
producto consumidor.

## Criterio de cierre

Este pendiente se cierra sólo cuando:

```text
OWNER_EXACT_SHA_SUITE=PASS
PLATAFORMACARGA_REMOTE_PIPELINE=PASS
PLATAFORMACARGA_PRODUCT_VALIDATION=PASS
HOST_DUPLICATE_PRIMITIVES=REMOVED
POST_CUTOVER_REGRESSION=PASS
PRODUCTION_ENABLEMENT=UNCHANGED_DISABLED
```
