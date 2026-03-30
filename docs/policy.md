# Policy actual soportada

Contrato vigente para `backupkit precheck`, `backupkit backup` y `backupkit verify-artifact`.

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

## Secciones soportadas hoy

### `project`

- `name` requerido

### `resource`

- `name` requerido
- `type` requerido
- `connection.host` requerido para `precheck` y `backup` con MySQL
- `connection.port` requerido para `precheck` y `backup` con MySQL
- `connection.database` requerido para `precheck` y `backup` con MySQL
- `connection.username` requerido para `precheck` y `backup` con MySQL

### `artifact`

- `output_dir` requerido
- `path` opcional para `backup`
- `path` o `metadata_path` requerido para `verify-artifact`
- `verify_path` y `verify_metadata_path` aceptados como alias explícitos para `verify-artifact`

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

## Variables de `.env`

### Requeridas para backup MySQL real

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

Nota: hoy `backup` usa `mysqldump` de forma directa para el dump y genera gzip/sha256 desde Python estándar. `verify-artifact` valida gzip y sha256 desde Python estándar también, pero mantener estos tool ids en precheck ayuda a verificar el entorno operativo completo.

## Lo que no forma parte del contrato vigente

Todavía no se soportan como fases reales ni como schema operativo:

- `restore-test`
- `validators`
- `retention`
- múltiples motores además de MySQL
- baseline histórico
