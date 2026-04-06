# Capa de Notificaciones

`backupkit` posee una capa de notificaciones desacoplada del pipeline principal y del modelo de reporte.

## Arquitectura

La arquitectura se basa en tres componentes principales:

1.  **Notifier (Base):** Una clase abstracta que define la interfaz para cualquier canal de notificación (Telegram, Slack, Email, etc.).
2.  **SummaryRenderer:** Un componente encargado de transformar un `RunReport` en un resumen corto, humano-legible y enfocado en la operatividad.
3.  **NotificationService:** Un orquestador que decide qué notificaciones enviar basándose en el estado del reporte y la configuración de la política.

## Política Operativa

Por defecto, la política de notificaciones es:
- **Estado OK:** No se envía ninguna notificación.
- **Estado WARN o ERROR:** Se envía un resumen operativo a los canales habilitados.

Esto evita el "ruido" en operaciones exitosas y asegura visibilidad inmediata ante problemas o advertencias.

## Implementaciones

### Telegram

Para habilitar Telegram, se debe configurar en la `policy.yml`:

```yaml
notifications:
  telegram:
    enabled: true
```

Y proveer las credenciales en el archivo `.env`:

```env
TELEGRAM_BOT_TOKEN="tu_token_aqui"
TELEGRAM_CHAT_ID="tu_chat_id_aqui"
```

## Resumen Operativo

El resumen enviado incluye:
- Comando ejecutado (BACKUP, RESTORE-TEST, etc.) y estado final.
- Nombre del proyecto y recurso.
- Nombre del artefacto generado (si aplica).
- Resultados de validaciones críticas.
- Lista de checks que fallaron (WARN/ERROR).

## Extensibilidad

Para sumar un nuevo canal:
1. Crear una clase que herede de `Notifier` en `core/notifier.py`.
2. Implementar el método `notify(self, report: RunReport)`.
3. Registrar el nuevo notifier en `NotificationService._setup_notifiers()`.
