# Pendiente externo — permitir código BackupKit en el builder de Base

## Estado

Bloqueo externo verificado. No resuelto en este repositorio.

## Repositorio propietario

```text
lucasborges2001/Base
```

`backupkit` no debe copiar ni modificar internals del builder reusable.

## Evidencia

El entrypoint público de deploy de `Base` es:

```text
bin/base-build-deploy-zip
```

El motor aplica patrones globales sensibles antes de construir el inventario:

```text
*backup*
**/*backup*
*dump*
**/*dump*
```

La semántica actual compara estos patrones tanto contra el path fuente como contra el path destino.

Consecuencia para este módulo:

```text
bin/backupkit                         -> excluido
core/backup.py                        -> excluido
submodules/backupkit/module.php       -> excluido por el prefijo destino
submodules/backupkit/back/bootstrap.php -> excluido por el prefijo destino
```

Por tanto, un manifest correcto no puede producir hoy un artifact completo de BackupKit mediante el builder de `Base`.

## Objetivo

Mantener bloqueados dumps, outputs y artifacts sensibles sin bloquear código fuente o identidades de módulo que contengan la palabra `backup`.

## Cambio esperado en Base

Reemplazar la exclusión por substring genérico por reglas específicas de artifacts y ubicaciones runtime.

Familias candidatas:

```text
*.sql
**/*.sql
*.sql.gz
**/*.sql.gz
*.dump
**/*.dump
*.bak
**/*.bak
var/output/**
**/var/output/**
var/backups/**
**/var/backups/**
backups/**
**/backups/**
dumps/**
**/dumps/**
```

No convertir esta lista en cambio automático sin revisar todos los hosts consumidores y la caracterización vigente.

## Invariantes

El cambio en `Base` debe preservar:

- `.env` y secretos fuera del ZIP;
- dumps SQL y comprimidos fuera del ZIP;
- outputs y reports runtime fuera del ZIP;
- rechazo de symlinks y path traversal;
- validación de `required_paths`;
- validación de `forbidden_paths`;
- compatibilidad con manifests existentes;
- códigos de salida `0`, `1` y `2`;
- ausencia de mutaciones en el checkout productivo.

## Tests requeridos en Base

Agregar caracterización real para:

### Código allowlisted permitido

```text
bin/backupkit
core/backup.py
submodules/backupkit/module.php
submodules/backupkit/back/bootstrap.php
```

### Artifacts sensibles prohibidos

```text
var/output/mysql.sql.gz
var/backups/mysql.dump
backups/mysql.sql
dumps/mysql.bak
.env.backup
```

### Criterio PASS

```text
[ ] los paths de código quedan incluidos cuando el manifest los allowlistea
[ ] los artifacts sensibles siguen excluidos
[ ] el ZIP contiene release-info.json
[ ] la extracción segura PASS
[ ] test/deploy/run_characterization.sh PASS
[ ] git diff --check PASS
```

## Dependencias

- contrato `deploy/module.manifest.json` schema `1` en `Base`;
- manifests ya definidos en `backupkit`;
- revisión de manifests de hosts que repitan `*backup*` y `**/*backup*`;
- fase separada para cualquier cambio posterior en `Pruebas`.

## Rollback

Si el cambio en `Base` habilita contenido no deseado:

1. revertir únicamente el commit del matcher;
2. conservar los manifests de BackupKit sin usarlos;
3. volver a bloquear el build standalone;
4. revisar el inventario concreto que atravesó la regla.

## No autorizado por este pendiente

- modificar `Base` desde `backupkit`;
- agregar BackupKit al app deploy de `Pruebas`;
- incluir dumps o reports runtime en un artifact;
- ejecutar deploy productivo;
- crear aliases o excepciones hardcodeadas solo para un repositorio.
