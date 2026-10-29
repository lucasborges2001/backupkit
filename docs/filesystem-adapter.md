# Adapter filesystem — BackupKit (F4-C)

Owner: backupkit. Perfil: tooling operativo, fuera de HTTP y fuera del ZIP App.

## Capacidad implementada

El adapter `filesystem` reutiliza los comandos públicos BackupKit:

- `precheck`: comprueba existencia de directorio absoluto y que su inventario no contiene symlinks, hardlinks de archivos, dispositivos ni FIFOs.
- `backup`: comprime un snapshot de archivos regulares en `.tar.gz`, publica el artefacto de manera exclusiva, registra SHA-256 y sidecar canónico, report v2 y lock.
- `verify-artifact`: valida gzip/SHA-256/sidecar mediante core.artifact y comprueba el inventario TAR con lectura completa, sin extracción.
- `restore-test`: crea un directorio temporal privado en artifact.output_dir, restaura cada archivo por streaming, compara SHA-256 de los bytes extraídos y elimina el directorio al terminar. Jamás restaura archivos en el directorio de origen.

La política de **retención se rechaza** para filesystem porque el motor de housekeeping actual está limitado a `.sql.gz` de MySQL. No habilitar borrado de archivos por un cambio de nombre o extensión.

## Policy mínima

```yaml
project:
  name: centrologistico
resource:
  name: ingest-state
  type: filesystem
  source_dir: /ruta/absoluta/de/ingest-state-desde-snapshot-consistente
artifact:
  output_dir: /ruta/privada/de/backups
runtime:
  lock_dir: /ruta/privada/de/locks
prechecks:
  require_free_space_mb: 1024
  require_tools: []
retention:
  enabled: false
```

Archivo env: puede ser un archivo vacío protegido de BackupKit; el adapter no requiere credenciales propias. Nunca versionar `.env` ni policies privadas que incluyan secretos o rutas sensibles.

Para `verify-artifact` o `restore-test`, agregar `artifact.path` con la ruta del TAR creado. No aplicar `restore_test.critical_tables`, `smoke_queries` o `validators`: son contratos del adapter MySQL.

## Limitaciones críticas

- El adapter verifica cambios de `inode/size/mtime` en los archivos que enumera, pero **no garantiza un snapshot consistente** si otro proceso crea/elimina archivos durante el recorrido. Debe ejecutarse sobre datos quiescentes o una copia/snapshot atómico proporcionado por el host.
- El backup se guarda sin cifrado; el archivo TAR contiene datos potencialmente sensibles. Custodia `0700/0600`, acceso limitado, cifrado externo y retención verificada son responsabilidades operativas pendientes.
- El restore-test comprueba TAR a un directorio temporal; **no** prueba recuperación de la aplicación, integridad semántica de eventos, credenciales ni estado de PLC.
- InfluxDB 2 necesita `influx backup` (API nativa). **No** respaldar copiando el volumen Influx activo con este adapter: un TAR de ese volumen no acredita consistencia.
- No se ejecutaron aún capturas reales ni restores contra servicios reales de CentroLogistico.

## Validación

```bash
python3 -B -m unittest tests.test_filesystem_adapter -v
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```

Los tests usan directorios temporales y no tocan bases, Docker ni PLC. Comprobar el resultado exact-SHA antes de avanzar a actualizar el gitlink del host.
