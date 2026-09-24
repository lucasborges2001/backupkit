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
- [ ] suite owner ejecutada y registrada sobre SHA exacto `89d9c9d83b00a6b01ae24af9db5f6be48b0eab8d`
- [ ] validación MySQL descartable real desde `PlataformaCarga` sobre ese SHA
- [ ] cutover consumidor completado y duplicación host retirada
- [ ] baseline operativo/productivo
- [ ] soporte multi-engine

## Próximo gate

El owner vigente es:

```text
BACKUPKIT_SHA=89d9c9d83b00a6b01ae24af9db5f6be48b0eab8d
OWNER_IMPLEMENTATION=HARDENED
OWNER_EXACT_SHA_VALIDATION=PENDING
PLATAFORMACARGA_CUTOVER_VALIDATION=PENDING_REMOTE_EXECUTOR
PRODUCTION_OPERATION=PENDING
```

El próximo gate no es agregar más lógica de backup al host consumidor. Debe
ejecutarse la suite exacta del owner y el gate `backupkit_cutover` de
`PlataformaCarga` contra MySQL descartable real. Sólo después de
`PIPELINE=PASS` y `PRODUCT=PASS` puede retirarse la implementación duplicada
del host.

Detalle del cutover: [`pendientes/plataformacarga-cutover.md`](pendientes/plataformacarga-cutover.md).

La habilitación productiva de scheduler, credenciales, storage, retención
destructiva y canary sigue separada en
[`pendientes/operacion-produccion.md`](pendientes/operacion-produccion.md).
