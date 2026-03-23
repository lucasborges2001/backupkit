# Precheck contract

## Estado final

- `OK`: todos los checks obligatorios pasaron
- `WARN`: no hay bloqueantes fallidos, pero sí degradaciones
- `ERROR`: falló al menos un check bloqueante

## Orden

1. config mínima
2. lock
3. output dir
4. free space
5. herramientas requeridas
6. adapter-specific checks

## Checks implementados

### Core

- `core.config.required`
- `core.lock.available`
- `core.output_dir.writable`
- `core.free_space`
- `core.tools.available`
- `core.adapter.supported`

### MySQL

- `adapter.mysql.connectivity`
- `adapter.mysql.auth`
