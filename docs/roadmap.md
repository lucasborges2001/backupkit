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
- [ ] validación MySQL descartable real desde `PlataformaCarga` sobre ese SHA; r34 abortó en preflight por un pin histórico del harness host y r35 no obtuvo claim
- [ ] cutover consumidor completado y duplicación host retirada
- [ ] baseline operativo/productivo
- [ ] topología 3-2-1 verificada con dos dominios de fallo y una copia offsite cifrada
- [ ] restore periódico al menos mensual ejecutado desde una copia independiente, o frecuencia más estricta según RPO/RTO
- [ ] soporte multi-engine

## Próximo gate

El owner vigente es:

```text
BACKUPKIT_SHA=8d497912fc601f2d4bf8a4ce53b779dc13990b4f
OWNER_IMPLEMENTATION=HARDENED
OWNER_EXACT_SHA_VALIDATION=PASS_R34
OWNER_PYTHON_SUITE=PASS_51_TESTS
OWNER_PHP_CONTRACT=PASS
PLATAFORMACARGA_CUTOVER_VALIDATION=PENDING_REMOTE_RETRY_AFTER_HOST_HARNESS_FIX
PRODUCTION_OPERATION=PENDING
```

El owner exacto ya quedó certificado por el request r34 de `PlataformaCarga`.
El próximo gate no es agregar más lógica de backup al owner: debe reejecutarse
`backupkit_cutover` después del fix del harness host y alcanzar la recuperación
MySQL descartable real. Sólo después de `PIPELINE=PASS` y `PRODUCT=PASS`
puede retirarse la implementación duplicada del host.

Detalle del cutover: [`pendientes/plataformacarga-cutover.md`](pendientes/plataformacarga-cutover.md).

La habilitación productiva de scheduler, credenciales, storage, topología
3-2-1, copia offsite cifrada, restore periódico, retención destructiva y canary
sigue separada en
[`pendientes/operacion-produccion.md`](pendientes/operacion-produccion.md).
