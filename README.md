# backupkit

Starter operativo de `backupkit` con **precheck funcional** y core preparado para múltiples adapters.

## Qué trae

- CLI: `backupkit precheck`
- `.env` + `policy.yml`
- motor genérico de prechecks
- registry de adapters
- adapter MySQL inicial
- reporte JSON siempre
- Telegram solo para `WARN` y `ERROR`
- lock de ejecución
- checks de:
  - config mínima
  - output dir escribible
  - espacio libre
  - herramientas requeridas
  - conectividad
  - auth MySQL

## Qué no trae todavía

- dump real
- restore test
- validators SQL
- retención

## Uso

```bash
./bin/backupkit precheck \
  --env ./examples/mysql-basic/backup/.env.backup \
  --policy ./examples/mysql-basic/backup/backup.policy.yml
```

## Exit codes

- `0` => OK
- `1` => WARN
- `2` => ERROR

## Diseño

El core **no** queda atado a MySQL.
La resolución del adapter se hace por `resource.type`, con una registry simple en `adapters/__init__.py`.

## Notificación

Telegram se envía **una vez por corrida** y solo si el estado final es `WARN` o `ERROR`.
