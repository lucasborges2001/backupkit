# Deploy standalone de BackupKit

## Estado

Contrato definido en `backupkit`. El empaquetado con el builder actual de `Base` permanece bloqueado por una regla externa documentada en `docs/pendientes/base-deploy-builder-backupkit.md`.

No se ejecutó un deploy real ni se modificaron `Base` o `Pruebas`.

## Decisión arquitectónica

`backupkit` se despliega como tooling operativo de servidor y no como parte del runtime web de `Pruebas`.

```text
Pruebas app ZIP -X-> backupkit
backupkit server ZIP -> release standalone
cron/systemd/operador -> bin/backupkit
HTTP -X-> bin/backupkit
```

Clasificación:

```text
tier: tooling-server-backup
required_for_preflight: false
include_in_app_deploy: false
tooling: true
optional: true
```

El repositorio sigue sin depender de `Base`. Los manifests adoptan el contrato público de deploy de `Base` para evitar un formato alternativo, pero no se importa código ni se exige `Base` en runtime.

## Contratos de manifest

### Manifest canónico de módulo

Ruta:

```text
deploy/module.manifest.json
```

Contrato:

```text
schema_version: 1
module: backupkit
```

Este manifest es la allowlist canónica del contenido desplegable del módulo.

### Manifest standalone de servidor

Ruta:

```text
deploy/server.manifest.json
```

Contrato:

```text
project: BackupKit
profile: server
requires_public_html_in_zip: false
submodules: {}
```

El artifact no requiere `public_html`, no contiene otros submódulos y debe incluir `release-info.json` generado por el builder.

## Inventario desplegable

Familias incluidas:

```text
module.php
back/**
bin/**
core/**
adapters/**
lib/**
```

Rutas requeridas:

```text
module.php
back/bootstrap.php
bin/backupkit
core/cli.py
core/result.py
core/backup.py
adapters/mysql/adapter.py
```

Ausencia de cualquiera de estas rutas debe producir fallo de build.

## Contenido prohibido

El ZIP no puede contener:

```text
.git/
.github/
.gitmodules
.env
.env.*
docs/
tests/
examples/
scripts/
var/
releases/
__pycache__/
*.pyc
*.log
*.zip
*.sql
*.sql.gz
*.dump
*.bak
```

La regla protege secretos, policies reales, dumps, reportes runtime, locks, caches y artifacts anteriores.

No se usa una exclusión por substring genérico `*backup*`, porque `backupkit` y `core/backup.py` son código fuente requerido, no artifacts sensibles.

## Layout del servidor

Layout recomendado:

```text
/opt/backupkit/releases/<sha>/   release inmutable
/opt/backupkit/current           symlink a la release activa
/etc/backupkit/                  env y policies administradas fuera de Git
/var/lib/backupkit/              outputs y metadata
/run/backupkit/                  locks efímeros
```

Ejemplo por recurso:

```text
/etc/backupkit/mysql-main.env
/etc/backupkit/mysql-main.backup.policy.yml
/etc/backupkit/mysql-main.restore.policy.yml
/var/lib/backupkit/mysql-main/output/
/run/backupkit/mysql-main.lock
```

Los paths concretos se declaran en la policy. No deben codificarse dentro de la release.

## Modelo de release

### Build

El build debe partir de un checkout limpio y de un commit exacto.

Comandos previstos una vez corregido el blocker de `Base`:

```bash
cd /ruta/a/backupkit

git status --short
git rev-parse HEAD

bash /ruta/a/Base/bin/base-build-deploy-zip \
  --manifest deploy/server.manifest.json \
  --profile server \
  --validate-artifact
```

Resultado esperado:

```text
releases/backupkit-server-<timestamp>-<sha>.zip
```

El artifact debe contener `release-info.json` con el commit de `backupkit` utilizado.

### Instalación

La instalación debe:

1. extraer el ZIP en un directorio temporal no público;
2. rechazar symlinks y traversal durante la extracción;
3. verificar `release-info.json`;
4. verificar las rutas requeridas;
5. ejecutar los checks de sintaxis y contrato;
6. copiar la release a `/opt/backupkit/releases/<sha>`;
7. cambiar atómicamente `/opt/backupkit/current`;
8. conservar la release anterior para rollback;
9. no copiar ni sobrescribir `/etc/backupkit` o `/var/lib/backupkit`.

La activación no debe crear, modificar ni borrar policies automáticamente.

### Validación previa a activación

Sobre la release extraída:

```bash
python3 -m compileall -q core adapters

php -l module.php
php -l back/bootstrap.php

./bin/backupkit --help
```

La validación funcional completa se ejecuta en el checkout antes del build:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
php tests/test_php_contract.php
```

Los tests no forman parte del ZIP productivo.

### Activación

La activación debe usar un cambio atómico de symlink, no sobrescritura in-place:

```bash
ln -sfn /opt/backupkit/releases/<sha> /opt/backupkit/current.next
mv -Tf /opt/backupkit/current.next /opt/backupkit/current
```

Antes del cambio debe registrarse la release activa anterior.

### Rollback

Rollback permitido:

1. detener o esperar la finalización de una corrida activa;
2. cambiar `/opt/backupkit/current` a la release anterior;
3. ejecutar `precheck` con una policy controlada;
4. reanudar el scheduler;
5. conservar la release fallida para diagnóstico.

No se eliminan releases ni artifacts como parte del rollback.

Ejemplo conceptual:

```bash
ln -sfn /opt/backupkit/releases/<sha-anterior> /opt/backupkit/current.next
mv -Tf /opt/backupkit/current.next /opt/backupkit/current
```

## Configuración y secretos

Reglas:

- `.env` y policies viven fuera de la release;
- permisos recomendados: directorio `0750`, archivos secretos `0640` o más restrictivos;
- usuario operativo dedicado;
- credenciales de backup y restore-test separables;
- ningún secreto en `release-info.json`, logs, reports o ZIP;
- ningún output bajo `public_html`;
- el path del último reporte para `Pruebas` se configura de forma fija por el host.

## Scheduler

El scheduler es responsabilidad operativa externa y no forma parte del ZIP de aplicación.

Puede utilizarse cron o systemd, pero debe ejecutar siempre el CLI:

```text
/opt/backupkit/current/bin/backupkit
```

No debe invocar funciones Python internas ni ejecutar el CLI desde PHP o HTTP.

El scheduler debe declarar explícitamente:

- recurso;
- env;
- policy;
- frecuencia;
- usuario;
- timeout;
- comportamiento ante solapamiento;
- captura de stdout/stderr;
- alerta por exit codes `1` y `2`.

## Observabilidad

Evidencia mínima por deploy:

```text
commit desplegado
nombre y SHA-256 del ZIP
release anterior
release activada
resultado de compileall
resultado de lint PHP
resultado de precheck post-activación
hora de activación
operador o workflow
```

Los reportes funcionales continúan bajo el contrato `backupkit.report.v2`.

## Relación con Pruebas

`Pruebas` solo debe:

- registrar el submódulo como tooling opcional;
- no incluirlo en el app deploy;
- cargar `back/bootstrap.php` para health y lectura read-only;
- configurar un report path fijo fuera de `public_html`;
- agregar smoke host sobre fixture y report real opcional.

`Pruebas` no instala, actualiza ni ejecuta BackupKit mediante requests web.

## Relación con Base

Contrato reutilizado como formato:

```text
Base/bin/base-build-deploy-zip
Base/deploy/module.manifest.json schema_version=1
profile=server
release-info.json
validación segura de ZIP extraído
```

La integración es de compatibilidad contractual. `backupkit` no declara dependencia de repositorio sobre `Base`.

## Gate de cierre

### BackupKit

```text
[ ] manifests JSON parseables
[ ] tests/test_deploy_contract.py PASS
[ ] suite Python completa PASS
[ ] contrato PHP PASS
[ ] git diff --check PASS
[ ] rama mergeada en backupkit/main
```

### Base

```text
[ ] el builder no excluye código solo por contener la palabra backup
[ ] bin/backupkit queda incluido cuando está allowlisted
[ ] core/backup.py queda incluido cuando está allowlisted
[ ] dumps y outputs continúan prohibidos
[ ] caracterización de deploy de Base PASS
```

### Artifact

```text
[ ] build profile=server PASS
[ ] release-info.json presente
[ ] rutas requeridas presentes
[ ] secretos y outputs ausentes
[ ] extracción segura PASS
[ ] validación de release extraída PASS
```

Hasta cerrar los tres gates, el deploy está definido pero no habilitado para producción.
