# InfluxDB 2 nativo — adapter BackupKit (F4-C)

Owner: backupkit. Tipo de recurso: `influxdb2`. Solamente InfluxDB OSS 2.x y ejecutable `influx` disponible donde se corre BackupKit.

## Contrato

El adapter ofrece:

- `precheck`: valida un origen explícito de loopback `http://127.0.0.1:8086` o de red privada Docker `http://influxdb:8086`, organización y presencia del CLI y token; no verifica aún autenticación al servidor.
- `backup`: ejecuta **`influx backup --host ... --org ... DIRECTORIO`**, transportando el token por la variable de proceso `INFLUX_TOKEN` y nunca por argv. Captura stdout/stderr sin registrarlos. Guarda los archivos que produjo el CLI dentro de un `tar.gz` privado, verifica el TAR, crea sidecar SHA-256 y report v2.
- `verify-artifact`: valida checksum, sidecar y contenido TAR sin extraerlo.
- `restore-test`: **ERROR explícito**. No se ofrece restauración nativa automática porque faltan una instancia aislada, validación de versión de Influx y limpieza segura.

El backup no equivale a restore-test. Un report backup `OK` acredita que el CLI devolvió éxito y el archivo quedó íntegro, no la recuperación del motor.

## Policy de captura

```yaml
project:
  name: centrologistico
resource:
  name: influx-main
  type: influxdb2
  connection:
    host: http://influxdb:8086
    org: centrologistico
artifact:
  output_dir: /ruta/privada/de/backups
runtime:
  lock_dir: /ruta/privada/de/locks
prechecks:
  require_free_space_mb: 4096
  require_tools: []
retention:
  enabled: false
```

El archivo `.env` privado debe contener `INFLUX_TOKEN=...` y permisos restringidos. No copiar token a Git, argv, logs o reportes. La retención queda deshabilitada para tipos distintos de MySQL porque el housekeeping actual sólo reconoce `.sql.gz`.

El adapter NO incorpora `--skip-verify` ni acceso externo arbitrario. No activa puertos, redes, Docker ni un servidor Influx. La conexión privada a `influxdb` requiere ejecutar el CLI desde un entorno Docker autorizado que tenga acceso a esa red sin acceso a PLC.

## Restore-test pendiente y condiciones de cierre

Se requiere una instancia Influx OSS 2.x **descartable**, con versión compatible, capturar un backup verdadero, extraerlo a una ruta privada, ejecutar la restauración en la instancia desechable y comprobar org, buckets, conteos/series y no contaminación del origen. No ejecutar `influx restore --full` sobre la instancia productiva o compartida: puede reemplazar metadatos y alterar tokens. La ausencia del restore-test mantiene F4-C y F4-D incompletas.

Fuente de sintaxis y límites: documentación oficial https://docs.influxdata.com/influxdb/v2/reference/cli/influx/backup/ y https://docs.influxdata.com/influxdb/v2/admin/backup-restore/restore/

## Pruebas del adapter

```bash
python3 -B -m unittest tests.test_influxdb2_adapter -v
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```

El test Influx solo simula el CLI dentro de fixtures: no conecta Influx real. Estos tests deben pasar sobre el **SHA final exacto** antes de actualizar el gitlink de cualquier host.
