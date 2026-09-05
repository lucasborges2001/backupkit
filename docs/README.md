# Documentación de BackupKit

## Contratos vigentes

| Documento | Alcance |
|---|---|
| [`policy.md`](policy.md) | Policy canónica de comandos, recursos, artifacts, restore-test, notificaciones y retención. |
| [`precheck-contract.md`](precheck-contract.md) | Prechecks, checks y clasificación de fallos. |
| [`backup-contract.md`](backup-contract.md) | Generación del dump, compresión, metadata y reporte. |
| [`verify-artifact-contract.md`](verify-artifact-contract.md) | Integridad técnica del artifact y sidecar. |
| [`restore-test-contract.md`](restore-test-contract.md) | Restore efímero, validators y cleanup. |
| [`report-format.md`](report-format.md) | Contrato público `backupkit.report.v2`. |
| [`pruebas-integration.md`](pruebas-integration.md) | Integración vigente con `Pruebas`, superficie read-only y perfil estructural `external-tooling`. |
| [`deploy.md`](deploy.md) | Artifact standalone de servidor, layout, activación y rollback. |

## Pendientes propios y operativos

| Documento | Alcance |
|---|---|
| [`pendientes/operacion-produccion.md`](pendientes/operacion-produccion.md) | Credenciales, MySQL real, restore-test aislado, scheduler, instalación `/opt`, SuperAdmin, canary, deploy productivo y retención real. |

## Pendientes externos

| Documento | Repositorio propietario |
|---|---|
| [`pendientes/base-deploy-builder-backupkit.md`](pendientes/base-deploy-builder-backupkit.md) | `lucasborges2001/Base` |

## Cierres históricos conservados

| Documento | Estado |
|---|---|
| [`pendientes/pruebas-host-integration.md`](pendientes/pruebas-host-integration.md) | `CERRADO/HISTÓRICO`: el alta host ya fue implementada; se conserva en esta ruta hasta autorización explícita de borrado documental. |

La fuente normativa para el estado actual de integración es [`pruebas-integration.md`](pruebas-integration.md), no el pendiente histórico.

## Perfil de Structure Audit

La raíz de BackupKit contiene:

```text
.structure-audit-profile
```

con valor:

```text
external-tooling
```

Este contrato evita que la presencia del bootstrap `back/` se interprete como evidencia suficiente de un módulo funcional. La certificación remota del checkpoint corregido pertenece al host `Pruebas` y no se considera PASS hasta que exista un reporte nuevo del SHA correspondiente.

## Fuente histórica

[`backupkit.txt`](backupkit.txt) conserva contexto de diseño inicial. No es contrato normativo y no prevalece sobre los documentos anteriores.

## Regla de autoridad

Para una integración o deploy nuevo:

```text
policy.md + contrato del comando + report-format.md + deploy.md + pruebas-integration.md
```

Para habilitación productiva:

```text
pendientes/operacion-produccion.md + evidencia real de backup/restore + runbook del servidor
```

No inferir campos, aliases, rutas o capacidades desde ejemplos históricos.
