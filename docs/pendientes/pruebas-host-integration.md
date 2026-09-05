# Cierre histórico — Alta de backupkit en Pruebas

## Estado

```text
CERRADO
HISTORICO
NO ES BACKLOG VIVO
```

Este archivo nació como pendiente externo para `lucasborges2001/Pruebas`. El alta host ya fue implementada y este documento se conserva únicamente porque la política documental requiere autorización explícita para borrar archivos.

La fuente normativa actual es:

```text
docs/pruebas-integration.md
```

## Resultado implementado

BackupKit quedó integrado en `Pruebas` como tooling opcional del servidor con:

```text
path: submodules/backupkit
tier: tooling-server-backup
required_for_preflight: false
include_in_app_deploy: false
tooling: true
optional: true
```

El host dispone de:

- gitlink owner;
- registro en `config/submodules.php`;
- adapter PHP read-only;
- suite `backupkit_contract`;
- build standalone mediante Base;
- documentación de integración;
- exclusión explícita del app deploy.

La integración no habilita ejecución CLI desde HTTP.

## Checkpoint relevante actual

```text
backupkit: 07f9eaa97791ec904833bf32d959a903ce43eff9
Pruebas:   00531dd73c40de16a76df280e019d4a46a2cfec0
Base:      a357c4469542573fbaa4b38727a29645b3d77fde
TestKit:   b61d8b16ecba682cc8816060e657230051ea1c54
```

El SHA de BackupKit anterior incluye `.structure-audit-profile = external-tooling`.

## Fases históricas

Las fases originalmente previstas quedaron implementadas de la siguiente forma:

```text
Fase 0: owner contract              IMPLEMENTADA/MERGED
Fase 1: gitlink + manifest host     IMPLEMENTADA/MERGED
Fase 2: adapter host read-only      IMPLEMENTADA/MERGED
Fase 3: smoke/TestKit               IMPLEMENTADA
Fase 4: documentación operativa     IMPLEMENTADA
Fase 5: SuperAdmin agregado         NO IMPLEMENTADA / OPCIONAL
```

La ausencia de SuperAdmin no reabre el alta host porque esa fase era opcional y no forma parte del contrato mínimo.

## Invariantes que siguen vigentes

```text
backupkit core -X-> Pruebas
backupkit core -X-> Base
HTTP -X-> bin/backupkit
HTTP -X-> backup/restore/retention
app deploy -X-> backupkit
```

El host solo puede consumir la superficie pública read-only del owner.

## Deuda que no pertenece a este cierre

Este documento no representa backlog para:

- instalación productiva;
- scheduler;
- secrets provisioning;
- backup MySQL real;
- restore-test real;
- retención real;
- SuperAdmin opcional;
- certificación remota post-fix de Structure Audit.

La operación productiva permanece en:

```text
docs/pendientes/operacion-produccion.md
```

La certificación estructural posterior al override se gestiona desde `Pruebas` y debe probar el SHA exacto del host.

## Regla de uso

No crear nuevas tareas dentro de este archivo. Si aparece deuda real, registrarla en el documento owner correspondiente o en el repositorio propietario.

Este archivo puede eliminarse en una limpieza documental futura únicamente con autorización explícita de borrado.
