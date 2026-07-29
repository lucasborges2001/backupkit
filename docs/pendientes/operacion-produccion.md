# Pendiente — Operación y habilitación productiva de BackupKit

## Estado

**Pendiente operativo posterior a la integración técnica.**

Este documento no bloquea el contrato de módulo, el adapter read-only ni el empaquetado standalone. Define las fases necesarias para convertir BackupKit en un servicio operativo de producción con credenciales reales, scheduler, instalación versionada, restore-test aislado, observabilidad y controles administrativos.

No se considera autorizado por este documento:

- ejecutar backups o restores reales;
- crear usuarios o credenciales de base de datos;
- instalar archivos bajo `/opt`, `/etc`, `/var/lib` o `/run`;
- configurar cron o systemd;
- desplegar en producción;
- habilitar acciones HTTP;
- modificar `Pruebas` o `Base`;
- eliminar artifacts, releases o documentación.

## Objetivo

Cerrar de forma auditable los siguientes puntos:

1. credenciales y permisos mínimos;
2. paths persistentes y aislamiento de secretos;
3. backup MySQL real;
4. restore-test real sobre infraestructura aislada;
5. scheduler canónico;
6. instalación versionada bajo `/opt/backupkit`;
7. interfaz SuperAdmin read-only;
8. acciones operativas controladas, si se justifican;
9. deploy productivo, canary y rollback.

## Arquitectura objetivo

```text
/opt/backupkit/releases/<sha>/   release inmutable
/opt/backupkit/current           symlink a la release activa
/etc/backupkit/                  env y policies administradas fuera de Git
/var/lib/backupkit/              dumps, metadata y reportes
/run/backupkit/                  locks efímeros

cron/systemd/operador
    -> /opt/backupkit/current/bin/backupkit

Pruebas/SuperAdmin
    -> adapter read-only
    -> reportes backupkit.report.v2
    -X-> shell_exec/bin/backupkit
```

## Ownership

| Alcance | Repositorio o sistema propietario |
|---|---|
| CLI, policy, adapters, reports, validación y restore-test | `lucasborges2001/backupkit` |
| Builder ZIP reusable y validación segura de artifact | `lucasborges2001/Base` |
| Registro de submódulo, adapter host y SuperAdmin | `lucasborges2001/Pruebas` |
| Usuarios, secretos, storage, scheduler y activación | Infraestructura del servidor |
| Contratos visuales, auth y capabilities reusables | `lucasborges2001/Base` cuando aplique |

No copiar lógica del CLI en `Pruebas` ni introducir lógica MySQL o de retención en `Base`.

---

## Fase 0 — Precondiciones y decisiones operativas

### Evidencia requerida

- SHA de `backupkit/main` validado;
- SHA de `Base/main` con builder compatible;
- artifact standalone validado;
- entorno objetivo identificado;
- responsable operativo identificado;
- ventana de mantenimiento definida;
- política de retención y recuperación aprobada.

### Decisiones obligatorias

- servidor o cluster donde se ejecutará BackupKit;
- usuario Unix dedicado;
- mecanismo canónico de scheduler: cron **o** systemd timer;
- ubicación de storage local;
- necesidad de storage externo o replicación;
- RPO y RTO esperados;
- recursos MySQL incluidos;
- frecuencia de backup y restore-test;
- política de alertas;
- responsable de credenciales y rotación.

### Criterio PASS

```text
[ ] SHAs definitivos registrados
[ ] artifact validado
[ ] entorno objetivo identificado
[ ] ownership operativo asignado
[ ] RPO/RTO documentados
[ ] scheduler canónico elegido
[ ] retención aprobada
[ ] rollback aprobado
```

### Criterio FAIL

- ejecutar una fase posterior con SHAs de ramas temporales;
- no conocer el responsable de secretos;
- no definir RPO/RTO;
- configurar simultáneamente cron y systemd para el mismo recurso.

---

## Fase 1 — Credenciales, secretos y permisos mínimos

### Objetivo

Crear credenciales separadas y mínimas para backup y restore-test sin almacenarlas en Git, ZIP, reportes o argumentos visibles del proceso.

### Alcance

- usuario Unix dedicado, por ejemplo `backupkit`;
- directorio `/etc/backupkit` con permisos restrictivos;
- un archivo env por recurso;
- credencial MySQL de backup con privilegios mínimos;
- credencial separada para restore-test;
- rotación y revocación documentadas;
- validación de que los reportes no contienen secretos.

### Invariantes

- no reutilizar root MySQL salvo entorno descartable explícito;
- no versionar `.env` ni policies reales;
- no pasar contraseñas por argumentos del CLI;
- no exponer secretos en SuperAdmin;
- permisos recomendados: directorio `0750`, archivos `0640` o más restrictivos;
- el usuario del proceso solo accede a los recursos necesarios.

### Evidencia

```text
usuario Unix
owner/group de directorios
permisos efectivos
privilegios MySQL concedidos
fecha de creación/rotación
prueba de conexión sin imprimir secretos
```

### Validación

```bash
namei -l /etc/backupkit
stat -c '%a %U %G %n' /etc/backupkit /etc/backupkit/*

/opt/backupkit/current/bin/backupkit precheck \
  --env /etc/backupkit/<recurso>.env \
  --policy /etc/backupkit/<recurso>.backup.policy.yml
```

### Criterio PASS

```text
[ ] usuario operativo dedicado
[ ] credenciales separadas
[ ] permisos mínimos verificados
[ ] secrets ausentes del artifact
[ ] secrets ausentes de reports y logs
[ ] rotación/revocación documentadas
[ ] precheck de autenticación PASS
```

### Rollback

- revocar las credenciales creadas;
- retirar los archivos de `/etc/backupkit`;
- conservar únicamente evidencia sanitizada;
- no eliminar releases ni artifacts no relacionados.

---

## Fase 2 — Storage persistente y backup MySQL real

### Objetivo

Ejecutar el primer backup real controlado y demostrar integridad técnica del artifact.

### Dependencias

- Fase 0 PASS;
- Fase 1 PASS;
- espacio y permisos validados;
- policy revisada;
- retención inicialmente en `dry_run`.

### Alcance

- crear `/var/lib/backupkit/<recurso>/output`;
- crear `/run/backupkit` o equivalente para locks;
- ejecutar `precheck`;
- ejecutar un backup manual supervisado;
- ejecutar `verify-artifact`;
- verificar metadata y SHA-256;
- comprobar que el dump no queda bajo `public_html`;
- conservar tiempos, tamaño y exit codes.

### Validación

```bash
/opt/backupkit/current/bin/backupkit precheck \
  --env /etc/backupkit/<recurso>.env \
  --policy /etc/backupkit/<recurso>.backup.policy.yml

/opt/backupkit/current/bin/backupkit backup \
  --env /etc/backupkit/<recurso>.env \
  --policy /etc/backupkit/<recurso>.backup.policy.yml

/opt/backupkit/current/bin/backupkit verify-artifact \
  --env /etc/backupkit/<recurso>.env \
  --policy /etc/backupkit/<recurso>.verify.policy.yml
```

### Criterio PASS

```text
[ ] precheck OK o WARN aceptado explícitamente
[ ] backup exit code 0
[ ] dump no vacío
[ ] gzip íntegro
[ ] sidecar parseable
[ ] SHA-256 coincidente
[ ] backup-report.json v2 válido
[ ] artifact fuera de public_html
[ ] lock liberado al finalizar
[ ] retención todavía en dry_run
```

### Criterio FAIL

- artifact vacío;
- hash inconsistente;
- credencial administrativa innecesaria;
- output público;
- lock residual;
- reporte legacy o inválido;
- housekeeping real habilitado antes de validar dry-run.

### Rollback

- detener nuevas ejecuciones;
- conservar el artifact fallido para diagnóstico si no contiene secretos;
- retirar la policy defectuosa;
- no marcar el backup como recuperable sin restore-test.

---

## Fase 3 — Restore-test real y aislado

### Objetivo

Demostrar recuperabilidad real sin restaurar sobre la base productiva ni reutilizar credenciales de backup.

### Dependencias

- Fase 2 PASS;
- instancia o servidor de restore aislado;
- credenciales separadas;
- prefijo de base temporal validado;
- validators y tablas críticas revisados;
- cleanup auditable.

### Invariantes

- nunca restaurar sobre la base productiva objetivo;
- nunca aceptar un nombre de base temporal arbitrario desde HTTP;
- ejecutar `DROP DATABASE IF EXISTS` solo sobre el nombre temporal generado y validado;
- registrar fallo de cleanup como error operativo;
- conservar evidencia del restore y los validators;
- no declarar recuperabilidad por verificar únicamente gzip o SHA-256.

### Validación

```bash
/opt/backupkit/current/bin/backupkit restore-test \
  --env /etc/backupkit/<recurso>-restore.env \
  --policy /etc/backupkit/<recurso>.restore.policy.yml
```

Validar además desde otro proceso que la base temporal no existe después del cleanup.

### Criterio PASS

```text
[ ] restore sobre instancia aislada
[ ] base temporal única
[ ] tablas críticas presentes
[ ] smoke queries PASS
[ ] validators ejecutados
[ ] cleanup PASS
[ ] base temporal ausente al finalizar
[ ] restore-test-report.json v2 válido
[ ] artifact marcado recuperable por evidencia real
```

### Criterio FAIL

- ejecución sobre producción;
- ausencia de procesos o conexión real;
- test que solo imprime `PASS`;
- cleanup no comprobado;
- credenciales compartidas sin justificación;
- artifact declarado válido sin restore completo.

### Rollback

- detener restore-tests;
- aislar la instancia de restore;
- eliminar manualmente únicamente bases temporales verificadas;
- rotar la credencial si hubo exposición;
- conservar logs sanitizados.

---

## Fase 4 — Scheduler canónico: cron o systemd

### Objetivo

Automatizar ejecuciones sin duplicidad, solapamiento ni dependencia del runtime web.

### Decisión

Elegir un único mecanismo por recurso:

```text
cron XOR systemd timer
```

Se recomienda systemd timer cuando se requieran límites, logs estructurados, dependencias de red, timeout y control de ejecución.

### Contrato mínimo

Cada job debe declarar:

- recurso;
- env;
- policy;
- frecuencia;
- usuario;
- timeout;
- prevención de solapamiento;
- captura de stdout/stderr;
- tratamiento de exit codes `0`, `1` y `2`;
- alerta por `WARN` y `ERROR`;
- ruta exacta `/opt/backupkit/current/bin/backupkit`.

### Prohibido

- scheduler dentro de PHP;
- request HTTP como scheduler;
- `shell_exec` desde SuperAdmin;
- dos schedulers activos sobre el mismo recurso;
- usar rutas de una release concreta en lugar del symlink `current`.

### Criterio PASS

```text
[ ] un scheduler canónico por recurso
[ ] usuario dedicado
[ ] timeout configurado
[ ] solapamiento bloqueado
[ ] exit codes preservados
[ ] logs y alertas verificadas
[ ] ejecución manual y programada producen el mismo contrato v2
[ ] disable/rollback documentado
```

### Rollback

- deshabilitar el timer o cron;
- comprobar que no quedan procesos activos;
- conservar la configuración para diagnóstico;
- no eliminar artifacts automáticamente.

---

## Fase 5 — Instalación versionada bajo `/opt/backupkit`

### Objetivo

Instalar artifacts inmutables, activar mediante symlink atómico y conservar una release anterior utilizable.

### Flujo

1. construir desde un commit exacto y checkout limpio;
2. validar ZIP y `release-info.json`;
3. extraer en directorio temporal seguro;
4. ejecutar sintaxis y contrato sobre la raíz extraída;
5. copiar a `/opt/backupkit/releases/<sha>`;
6. registrar release anterior;
7. actualizar atómicamente `/opt/backupkit/current`;
8. ejecutar `precheck` post-activación;
9. conservar la release anterior.

### Validación previa

```bash
python3 -m compileall -q core adapters
php -l module.php
php -l back/bootstrap.php
./bin/backupkit --help
```

### Activación conceptual

```bash
ln -sfn /opt/backupkit/releases/<sha> /opt/backupkit/current.next
mv -Tf /opt/backupkit/current.next /opt/backupkit/current
```

### Criterio PASS

```text
[ ] release-info.json coincide con SHA esperado
[ ] release inmutable
[ ] /etc y /var/lib no sobrescritos
[ ] activación atómica
[ ] precheck post-activación PASS
[ ] release anterior conservada
[ ] rollback ensayado en entorno no productivo
```

### Rollback

- detener o esperar la corrida activa;
- apuntar `current` a la release anterior;
- ejecutar `precheck` controlado;
- reanudar scheduler;
- conservar la release fallida para diagnóstico.

---

## Fase 6 — Interfaz SuperAdmin read-only

### Objetivo

Exponer estado operativo sanitizado sin habilitar comandos, descarga de dumps ni cambios de policy.

### Ownership

- adapter y pantalla específica: `Pruebas`;
- auth, capability y componentes reusables: contratos públicos de `Base`;
- lectura y sanitización de reportes: contrato público de `backupkit`;
- no agregar dependencia de `Pruebas` al core de BackupKit.

### Información permitida

- estado del último precheck;
- estado del último backup;
- estado del último verify-artifact;
- estado del último restore-test;
- timestamps y duración;
- tamaño del artifact;
- presencia de hash;
- resumen de validators;
- resumen de housekeeping;
- stale/no stale;
- enlace al runbook.

### Información prohibida

- contraseñas o tokens;
- contenido de `.env`;
- SQL del dump;
- queries sensibles;
- paths absolutos innecesarios;
- nombre de base temporal;
- descarga directa de dumps;
- edición de policies.

### Criterio PASS

```text
[ ] capability específica
[ ] sesión y autorización validadas
[ ] read-only real
[ ] reporte v2 estricto
[ ] stale visible
[ ] secretos ausentes
[ ] paths internos sanitizados
[ ] ninguna ejecución CLI desde HTTP
[ ] pruebas de acceso autorizado y denegado
```

### Rollback

- retirar la entrada de navegación o adapter host;
- conservar BackupKit operativo por CLI;
- no modificar el core ni los artifacts.

---

## Fase 7 — Acciones operativas desde SuperAdmin

### Estado

**No justificadas para la primera versión.**

Los botones para ejecutar backups o restore-tests solo deben implementarse si existe una necesidad operativa demostrada y una revisión de seguridad específica.

### Prohibición arquitectónica

No implementar:

```text
request HTTP -> shell_exec('/opt/backupkit/current/bin/backupkit ...')
```

### Arquitectura mínima aceptable

```text
SuperAdmin autenticado
    -> capability específica
    -> request CSRF protegido
    -> command request persistido y auditado
    -> worker operativo fuera de HTTP
    -> allowlist de comandos y recursos
    -> ejecución idempotente con lock
    -> reporte v2
```

### Requisitos

- únicamente comandos allowlisted;
- recursos definidos en configuración, no paths libres;
- sin argumentos arbitrarios;
- sin secretos en payloads;
- capability separada de lectura;
- CSRF y reautenticación para acciones sensibles;
- idempotency key;
- rate limit;
- audit log con actor, recurso, comando y resultado;
- estado `queued/running/completed/failed`;
- timeout y cancelación controlada;
- nunca ejecutar restore-test contra producción;
- no ofrecer eliminación de artifacts en esta fase.

### Criterio PASS

```text
[ ] necesidad aprobada
[ ] threat model revisado
[ ] worker separado de HTTP
[ ] allowlist estricta
[ ] capability write separada
[ ] CSRF/reautenticación PASS
[ ] idempotencia y locks PASS
[ ] auditoría persistente
[ ] pruebas de abuso y autorización PASS
[ ] rollback a interfaz read-only probado
```

### Criterio FAIL

- `shell_exec`, `exec`, `system` o equivalente desde request web;
- paths, comandos o policies controlados por el usuario;
- ausencia de auditoría;
- permisos globales innecesarios;
- restore-test disponible sobre recursos productivos.

### Rollback

- deshabilitar capability write y worker;
- conservar pantalla read-only;
- dejar el CLI y scheduler sin cambios.

---

## Fase 8 — Deploy productivo, canary y cutover

### Dependencias

- Fases 0 a 5 PASS;
- Fase 6 opcional;
- Fase 7 opcional y separada;
- backup y restore-test reales validados;
- alertas verificadas;
- rollback ensayado.

### Estrategia

1. instalar release sin activarla;
2. validar artifact extraído;
3. ejecutar precheck con credenciales productivas;
4. activar con scheduler deshabilitado;
5. ejecutar backup canary manual;
6. verificar artifact;
7. ejecutar restore-test aislado;
8. habilitar scheduler para un recurso;
9. observar al menos un ciclo completo;
10. ampliar a otros recursos;
11. habilitar retención real solo después de revisar `dry_run`.

### Evidencia mínima

```text
SHA de release
SHA-256 del ZIP
release anterior
release activada
precheck
backup canary
verify-artifact
restore-test
cleanup
alertas
scheduler
retención dry-run
operador y timestamps
```

### Criterio PASS

```text
[ ] canary PASS
[ ] artifact verificable
[ ] restore-test aislado PASS
[ ] cleanup PASS
[ ] alertas PASS
[ ] scheduler sin solapamiento
[ ] reporte v2 consumible por el host
[ ] rollback disponible
[ ] retención real aún bloqueada o aprobada explícitamente
```

### Rollback

1. deshabilitar scheduler;
2. esperar o detener ejecución activa de forma controlada;
3. cambiar `current` a la release anterior;
4. ejecutar precheck;
5. conservar artifacts y release fallida;
6. abrir incidente con evidencia sanitizada;
7. no borrar dumps durante el rollback.

---

## Fase 9 — Retención real y recuperación continua

### Objetivo

Habilitar housekeeping real únicamente después de caracterizar sus decisiones en `dry_run` y demostrar que nunca elimina el último backup recuperable.

### Dependencias

- al menos un backup recuperable validado por restore-test;
- varias corridas históricas disponibles;
- dry-run revisado por un operador;
- política de conservación aprobada;
- storage monitoreado.

### Criterio PASS

```text
[ ] dry-run coincide con la política esperada
[ ] último backup recuperable protegido
[ ] reports y sidecars correlacionados
[ ] borrado parcial recuperable
[ ] housekeeping idempotente
[ ] alertas por fallo
[ ] prueba de recuperación periódica programada
```

### Rollback

- volver a `retention.dry_run=true`;
- detener housekeeping;
- no intentar reconstruir artifacts eliminados sin una fuente externa verificada;
- documentar cualquier pérdida como incidente.

---

## Roadmap recomendado

```text
F0 decisiones y ownership
  -> F1 credenciales
  -> F2 backup real
  -> F3 restore-test real
  -> F4 scheduler
  -> F5 instalación versionada
  -> F8 canary/deploy productivo
  -> F9 retención real

F6 SuperAdmin read-only puede avanzar después de F2
F7 acciones SuperAdmin es opcional y posterior a F6
```

No adelantar botones operativos por delante de la validación CLI, el restore-test real y el scheduler.

## Gate global de cierre

```text
[ ] credenciales mínimas y separadas
[ ] paths y permisos validados
[ ] backup MySQL real PASS
[ ] verify-artifact PASS
[ ] restore-test aislado PASS
[ ] cleanup comprobado
[ ] scheduler canónico PASS
[ ] instalación /opt versionada PASS
[ ] canary productivo PASS
[ ] rollback ensayado
[ ] reportes v2 visibles y sanitizados
[ ] retención real caracterizada antes de habilitarse
[ ] documentación operativa actualizada
```

El pendiente solo puede cerrarse cuando la recuperabilidad haya sido demostrada mediante restore real y no únicamente por la creación de un dump.

## Comandos que este documento no ejecutó

No se ejecutaron:

```text
backupkit precheck
backupkit backup
backupkit verify-artifact
backupkit restore-test
mysqldump
mysql
systemctl
crontab
useradd
chmod/chown sobre servidor
instalación en /opt
creación o rotación de credenciales
deploy productivo
```

## Resultado esperado al cierre

```text
BACKUPKIT_PRODUCTION_OPERATION_PASS
```

Este resultado exige evidencia de backup, verificación, restore-test, cleanup, scheduler, activación y rollback. No puede sustituirse por un script que únicamente imprima `PASS`.
