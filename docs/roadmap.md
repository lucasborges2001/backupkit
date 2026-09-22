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
- [ ] baseline
- [ ] soporte multi-engine

## Próximo paso recomendado

Con el core funcional consolidado, el próximo gate es validar el SHA exacto contra MySQL descartable real desde el host consumidor antes de habilitar scheduler, retención destructiva o cutover productivo.
