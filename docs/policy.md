# Policy soportada

Contrato vigente para `backupkit precheck`, `backupkit backup`, `backupkit verify-artifact` y `backupkit restore-test`.

## Principios

- cada concepto tiene un único nombre;
- no existen aliases de configuración;
- los campos requeridos dependen del comando y del adapter;
- las rutas relativas de artefactos se resuelven respecto de `artifact.output_dir`;
- los paths registrados por artefactos nuevos son absolutos.

## Ejemplo válido para backup

```yaml
project:
  name: mysql-basic

resource:
  name: mysql-main
  type: mysql
  connection:
    host: 127.0.0.1
    port: 3306
    database: app
    username: root

artifact:
  output_dir: ./var/output

runtime:
  lock_dir: ./var/locks

prechecks:
  require_free_space_mb: 256
  warn_free_space_below_mb: 512
  connectivity_timeout_sec: 3
  require_tools:
    - mysql_query_client
    - mysql_dump_client
    - gzip_provider
    - hash_provider

notifications:
  telegram:
    enabled: true
    notify_on:
      - WARN
      - ERROR
```

## Ejemplo válido para verify-artifact

Las rutas se expresan como nombres relativos a `artifact.output_dir`:

```yaml
project:
  name: mysql-basic

resource:
  name: mysql-main
  type: mysql

artifact:
  output_dir: ./var/output
  path: mysql-basic__mysql-main__20260330T120000Z.sql.gz
  metadata_path: mysql-basic__mysql-main__20260330T120000Z.sql.gz.metadata.json

runtime:
  lock_dir: ./var/locks

prechecks:
  require_free_space_mb: 64
  require_tools:
    - gzip_provider
    - hash_provider

notifications:
  telegram:
    enabled: true
    notify_on:
      - WARN
      - ERROR
```

También se pueden usar paths absolutos:

```yaml
artifact:
  output_dir: /srv/backupkit/output
  path: /srv/backupkit/output/mysql-basic__mysql-main__20260330T120000Z.sql.gz
  metadata_path: /srv/backupkit/output/mysql-basic__mysql-main__20260330T120000Z.sql.gz.metadata.json
```

## Ejemplo válido para restore-test

```yaml
project:
  name: mysql-basic

resource:
  name: mysql-main
  type: mysql
  connection:
    host: 127.0.0.1
    port: 3306
    username: root

artifact:
  output_dir: ./var/output
  path: mysql-basic__mysql-main__20260330T120000Z.sql.gz
  metadata_path: mysql-basic__mysql-main__20260330T120000Z.sql.gz.metadata.json

restore_test:
  database_prefix: bkrt
  critical_tables:
    - users
    - orders
  smoke_queries:
    - SELECT 1;
    - SELECT COUNT(*) FROM users;
  validators:
    - id: users_non_zero
      description: debe existir al menos un usuario
      sql: SELECT COUNT(*) FROM users;
      expected:
        rule: non_zero
      severity: error
    - id: orders_below_100000
      sql: SELECT COUNT(*) FROM orders;
      expected:
        rule: less_than
        value: 100000
      severity: warning

runtime:
  lock_dir: ./var/locks

prechecks:
  require_free_space_mb: 64
  require_tools:
    - mysql_query_client
    - gzip_provider
    - hash_provider

notifications:
  telegram:
    enabled: true
    notify_on:
      - WARN
      - ERROR
```

## Secciones soportadas

### `project`

- `name`: requerido.

### `resource`

- `name`: requerido;
- `type`: requerido;
- `connection.host`: requerido para `precheck`, `backup` y `restore-test` con MySQL;
- `connection.port`: requerido para `precheck`, `backup` y `restore-test` con MySQL;
- `connection.database`: requerido para `precheck` y `backup` con MySQL;
- `connection.username`: requerido para `precheck`, `backup` y `restore-test` con MySQL.

### `artifact`

- `output_dir`: requerido;
- `path`: requerido para `verify-artifact` y `restore-test` cuando no se informa `metadata_path`;
- `metadata_path`: requerido para `verify-artifact` y `restore-test` cuando no se informa `path`.

Resolución de rutas:

```text
path absoluto -> se usa directamente
path relativo -> artifact.output_dir / path
```

Si solo se informa `path`, el sidecar se infiere agregando `.metadata.json`.

Si solo se informa `metadata_path`, el artefacto se resuelve desde `path` dentro del sidecar.

Campos rechazados:

```text
artifact.verify_path
artifact.verify_metadata_path
```

Su presencia produce el check bloqueante:

```text
core.config.unsupported=ERROR
```

### `restore_test`

- `database_prefix`: opcional, default `bkrt`;
- `critical_tables`: opcional, lista de tablas requeridas;
- `smoke_queries`: opcional, lista de SQL simples;
- `validators`: opcional, lista de validators SQL declarativos.

Cada validator requiere:

- `id` único;
- `sql`;
- `expected.rule`;
- `severity`: `error` o `warning`.

Reglas soportadas:

- `equals`;
- `greater_than`;
- `less_than`;
- `zero`;
- `non_zero`.

`expected.value` es requerido para `equals`, `greater_than` y `less_than`.

### `runtime`

- `lock_dir`: opcional;
- si no existe, se crea.

### `prechecks`

- `require_free_space_mb`: requerido;
- `warn_free_space_below_mb`: opcional;
- `connectivity_timeout_sec`: opcional;
- `require_tools`: opcional, recomendado para validar el entorno completo.

### `notifications.telegram`

- `enabled`: opcional;
- `notify_on`: opcional.

### `retention`

- `enabled`: opcional, default `false`;
- `keep_success`: opcional, default `7`;
- `keep_non_success`: opcional, default `5`;
- `delete_artifacts`: opcional, default `true`;
- `delete_reports`: opcional, default `true`;
- `require_verified_newer_backup`: opcional, default `true`;
- `protect_last_known_valid`: opcional, default `true`;
- `dry_run`: opcional, default `false`.

## Variables de `.env`

### Requeridas para backup y restore MySQL

- `MYSQL_PASSWORD`.

### Para verify-artifact

No requiere variables adicionales para validar un artefacto local.

### Opcionales

- `TELEGRAM_BOT_TOKEN`;
- `TELEGRAM_CHAT_ID`.

## Herramientas conocidas

- `mysql_query_client`;
- `mysql_dump_client`;
- `gzip_provider`;
- `hash_provider`.

`backup` ejecuta `mysqldump` y genera gzip/SHA-256 desde Python. `verify-artifact` valida gzip y SHA-256 desde Python. `restore-test` envía el SQL restaurado al cliente `mysql` mediante stdin.

## Fuera del contrato actual

- validators de negocio complejos;
- motores distintos de MySQL;
- baseline histórico;
- cifrado;
- upload externo;
- configuración mediante nombres alternativos.
