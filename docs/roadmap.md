# Roadmap

## Estado actual

- [x] precheck funcional
- [x] backup MySQL real
- [x] verify-artifact técnico
- [x] restore-test MySQL real sobre base temporal
- [x] validators SQL declarativos sobre restauración
- [x] reporte final consolidado `backupkit.report.v2`
- [x] notificación desacoplada del adapter
- [x] retención/housekeeping fail-closed con dry-run por defecto
- [x] hardening de artifacts/sidecars/locks y restore acotado en memoria
- [x] runtime Bash legacy duplicado retirado
- [x] suite owner ejecutada sobre SHA exacto `8d497912fc601f2d4bf8a4ce53b779dc13990b4f` desde `PlataformaCarga` r34: 51 tests Python `OK` + contrato PHP `PASS`
- [ ] validación MySQL descartable real desde `PlataformaCarga` sobre ese SHA; r34 abortó en preflight por un pin histórico del harness host, el fix quedó implementado y r35 no obtuvo claim. Pendiente: confirmar executor y reintentar con r36 o posterior
- [ ] cutover consumidor completado y duplicación host retirada
- [ ] baseline operativo/productivo
- [ ] topología 3-2-1 verificada con dos dominios de fallo y una copia offsite cifrada
- [ ] restore periódico al menos mensual ejecutado desde una copia independiente, o frecuencia más estricta según RPO/RTO
- [ ] soporte multi-engine

## Próximo gate

El implementation SHA validado y consumido por el host es:

```text
VALIDATED_OWNER_SHA=8d497912fc601f2d4bf8a4ce53b779dc13990b4f
OWNER_IMPLEMENTATION=HARDENED
OWNER_EXACT_SHA_VALIDATION=PASS_R34
OWNER_PYTHON_SUITE=PASS_51_TESTS
OWNER_PHP_CONTRACT=PASS
PLATAFORMACARGA_CUTOVER_VALIDATION=PENDING_REMOTE_RETRY_AFTER_HOST_HARNESS_FIX
REMOTE_EXECUTOR_POST_R34_ACTIVITY=NOT_OBSERVED
NEXT_VERIFICATION=CONFIRM_EXECUTOR_THEN_R36
PRODUCTION_OPERATION=PENDING
```

El implementation SHA exacto `8d497912...` quedó certificado por el request r34 de `PlataformaCarga`. Commits documentales posteriores en `main` no heredan automáticamente esa certificación.
El próximo gate no es agregar más lógica de backup al owner. Primero debe
confirmarse que el executor remoto de `PlataformaCarga` está disponible y,
recién entonces, reejecutarse `backupkit_cutover` con un request nuevo r36 o
posterior. Ese run debe alcanzar la recuperación MySQL descartable real. Un
request sin claim se clasifica como bloqueo operativo del pipeline, no como
fallo del owner. Sólo después de `PIPELINE=PASS` y `PRODUCT=PASS` puede
retirarse la implementación duplicada del host.

Detalle del cutover: [`pendientes/plataformacarga-cutover.md`](pendientes/plataformacarga-cutover.md).

La habilitación productiva de scheduler, credenciales, storage, topología
3-2-1, copia offsite cifrada, restore periódico, retención destructiva y canary
sigue separada en
[`pendientes/operacion-produccion.md`](pendientes/operacion-produccion.md).
