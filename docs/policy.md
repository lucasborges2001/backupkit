# Policy actual soportada

Contrato vigente para `backupkit precheck`, `backupkit backup`, `backupkit verify-artifact` y `backupkit restore-test`.

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

```yaml
project:
  name: mysql-basic

resource:
  name: mysql-main
  type: mysql

artifact:
  output_dir: ./var/output
  path: ./var/output/mysql-basic__mysql-main__20260330T120000Z.sql.gz
  metadata_path: ./var/output/mysql-basic__mysql-main__20260330T120000Z.sql.gz.metadata.json

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
  path: ./var/output/mysql-basic__mysql-main__20260330T120000Z.sql.gz
  metadata_path: ./var/output/mysql-basic__mysql-main__20260330T120000Z.sql.gz.metadata.json

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

## Secciones soportadas hoy

### `project`

- `name` requerido

### `resource`

- `name` requerido
- `type` requerido
- `connection.host` requerido para `precheck`, `backup` y `restore-test` con MySQL
- `connection.port` requerido para `precheck`, `backup` y `restore-test` con MySQL
- `connection.database` requerido para `precheck` y `backup` con MySQL
- `connection.username` requerido para `precheck`, `backup` y `restore-test` con MySQL

### `artifact`

- `output_dir` requerido
- `path` opcional para `backup`
- `path` o `metadata_path` requerido para `verify-artifact`
- `path` o `metadata_path` requerido para `restore-test`
- `verify_path` y `verify_metadata_path` aceptados como alias explícitos para `verify-artifact` y `restore-test`

### `restore_test`

- `database_prefix` opcional, default `bkrt`
- `critical_tables` opcional, lista de nombres de tablas a exigir
- `smoke_queries` opcional, lista de SQL simples a ejecutar sobre la base restaurada
- `validators` opcional, lista de validators SQL declarativos a ejecutar sobre la base restaurada
  - `id` requerido y único
  - `description` opcional
  - `sql` requerido
  - `expected.rule` requerido, soporta `equals`, `greater_than`, `less_than`, `zero`, `non_zero`
  - `expected.value` requerido solo para `equals`, `greater_than`, `less_than`
  - `severity` requerida, soporta `error` y `warning`

### `runtime`

- `lock_dir` opcional
- si no existe, se crea

### `prechecks`

- `require_free_space_mb` requerido
- `warn_free_space_below_mb` opcional
- `connectivity_timeout_sec` opcional
- `require_tools` opcional pero recomendado

### `notifications.telegram`

- `enabled` opcional
- `notify_on` opcional

### `retention`

- `enabled` opcional, default `false`
- `keep_success` opcional, default `7`
- `keep_non_success` opcional, default `5`
- `delete_artifacts` opcional, default `true`
- `delete_reports` opcional, default `true`
- `require_verified_newer_backup` opcional, default `true`
- `protect_last_known_valid` opcional, default `true`
- `dry_run` opcional, default `false`

## Variables de `.env`

### Requeridas para backup y restore MySQL real

- `MYSQL_PASSWORD`

### Para verify-artifact

- ninguna adicional obligatoria respecto del artefacto en sí

### Opcionales

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Herramientas esperadas

Tool ids conocidos:

- `mysql_query_client`
- `mysql_dump_client`
- `gzip_provider`
- `hash_provider`

Nota: hoy `backup` usa `mysqldump` de forma directa para el dump y genera gzip/sha256 desde Python estándar. `verify-artifact` valida gzip y sha256 desde Python estándar. `restore-test` restaura desde Python hacia `mysql` usando stdin. Mantener los tool ids en precheck ayuda a verificar el entorno operativo completo.

## Lo que no forma parte del contrato vigente

Todavía no se soportan como fases reales ni como schema operativo:

- validators de negocio complejos o específicos de dominio
- múltiples motores además de MySQL
- baseline histórico
