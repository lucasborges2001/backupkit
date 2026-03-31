# Roadmap

## Estado actual

- [x] precheck funcional
- [x] backup MySQL real
- [x] verify-artifact técnico
- [x] restore-test MySQL real sobre base temporal
- [x] validators SQL declarativos sobre restauración
- [ ] reporte final consolidado
- [ ] notificación desacoplada
- [ ] retención
- [ ] baseline
- [ ] soporte multi-engine

## Próximo paso recomendado

Con validators SQL declarativos ya incorporados en `restore-test`, el siguiente salto razonable ya no es sumar más checks sueltos sino consolidar reporte final y separar notificación del core operativo.
