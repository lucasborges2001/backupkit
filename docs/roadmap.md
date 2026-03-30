# Roadmap operativo

## Estado actual

Fases reales ya implementadas:

- `precheck`
- `backup`
- `verify-artifact`

## Próximos hitos razonables

### `restore-test`

Objetivo:
- levantar una base temporal
- restaurar el dump
- comprobar que la restauración técnica funciona

Todavía no implementado.

### `validators`

Objetivo:
- validar contenido restaurado o consistencia lógica
- checks de tablas, conteos, queries, invariantes

Todavía no implementado.

### baseline histórico

Objetivo:
- comparar tamaño, duración, hash policy o señales contra historial previo
- detectar drift operativo

Todavía no implementado.

### retención

Objetivo:
- expiración de artefactos
- limpieza automática

Todavía no implementado.

## Regla de diseño

Cada fase nueva debe:

- reutilizar el modelo de reporte existente
- extender el contrato sin romper fases previas
- separar validación técnica de validación funcional
- evitar vender como soportado lo que todavía es roadmap
