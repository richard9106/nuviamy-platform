# Análisis de riesgos y tratamiento

## Revisión de estado — 27 octubre 2026

Richard ha aceptado la responsabilidad de seguridad y privacidad. No ha aprobado por
ello los riesgos residuales. El [expediente de cierre](closure-2026-10-27.md) contiene
la evidencia actual y criterios concretos P01–P08; esta revisión no reemplaza una
evaluación exhaustiva ni la validación clínica/de seguridad pendiente.

| Riesgo histórico | Estado actualizado |
|---|---|
| R01 Identidad | Segundo paso por correo activo, bypass de revisor retirado. Evidencia de privilegios/TOTP en expediente restringido; revisar recuperación (P02) |
| R02 Invitaciones | Enlaces de un uso implementados; revisión de cuentas antiguas y cobertura del correo pendiente (P02/P04) |
| R03 Ámbito de acceso | Permisos y pruebas existentes, rol DB restringido y 17 triggers activos; matriz integral/revisión pendientes (P08) |
| R04 Salidas | Calendar minimizado, Gmail/Drive bloqueados, Sentry estructural; dos mensajes de error externo se corrigen en código. Retención histórica y contratos no cerrados (P04) |
| R05 Proveedores | BAA activo acreditado en Artifact; auditoría AWS activa. SES TLS/IAM preparado y solicitud productiva enviada, SMTP aún sin cambiar. Restantes flujos/contratos/copias pendientes (P01/P04) |
| R06 Infraestructura | Volumen/snapshots cifrados y S3 privado/versionado reverificados por consola; CloudTrail activo y logging S3 habilitado, con límites de entrega/integridad documentados (P01) |
| R07 Continuidad | Restauración S3 reciente real en PG aislado; nueva copia cifrada de configuración AWS autenticada; monitor/alerta probados. Custodia independiente y pérdida de host/objetivos aún pendientes (P06) |
| R08 Archivos | Validación y descargas con permisos existentes; revisión de contenido activo/escaneo y superficies pendiente (P08) |
| R09 Integridad y conservación | Firmas, adendas, auditoría y acuerdos protegidos; matriz clínica/legal holds/disposición integral pendientes (P05/P08) |
| R10 Incidentes | Procedimiento adoptado y tres escenarios respondidos por Richard; pendiente ejercicio técnico cronometrado/cobertura integral y alternativa operativa (P07) |
| R11 Equipo | Protección del equipo y custodia de claves revisadas en expediente restringido; completar evidencia (P03) |

Probabilidad e impacto cualitativos originales no se recalculan automáticamente: la
aprobación del análisis residual requiere revisar estos hechos con el responsable.
No se declara cerrado un riesgo por publicar este registro o por aprobar OAuth.

## Análisis histórico — 15 octubre 2026

Fecha: 15 octubre 2026. Preparado mediante inspección del repositorio, pruebas y
consultas de configuración del VPS. Pendiente de revisión y aprobación del responsable.
Alcance: confidencialidad, integridad y disponibilidad de los datos previstos; no
se inspeccionaron controles físicos del proveedor ni se ejecutó una intrusión externa.

## Activos y flujos

Navegador → HTTPS/Nginx → Django/Gunicorn → PostgreSQL y almacenamiento de documentos.
Los registros incluyen identidad/contacto, consultas iniciales, sesiones, diagnósticos,
planes, notas y firmas. La auditoría contiene identificadores y actividad. Credenciales,
OAuth y claves son activos críticos. R2 conserva objetos/copias; SMTP entrega acceso,
soporte y recuperación; Stripe gestiona la suscripción comercial live. Las integraciones
Google y el sistema de errores son salidas adicionales. El ordenador del operador,
el VPS, las cuentas de proveedores, DNS y CI forman parte del perímetro.

## Método

Probabilidad cualitativa: alta (ruta habitual expuesta sin control suficiente), media
(ruta plausible con controles parciales), indeterminada (falta evidencia). Impacto
alto si puede revelar/modificar expedientes, impedir su recuperación o comprometer
cuentas. Estas son estimaciones conservadoras, no frecuencias medidas. Cada cierre
requiere prueba, decisión y fecha; revisar antes del piloto, tras incidentes, cambios
de proveedor/ubicación o nuevas funciones, y periódicamente según plan aprobado.

| Riesgo / probabilidad / impacto | Evidencia y control | Tratamiento y criterio pendiente |
|---|---|---|
| R01 Robo de credenciales / media / alto | Límites compartidos, revocación, sesiones 1 h/8 h; MFA disponible pero desactivado a petición del propietario | Richard: decidir MFA y recuperación, registrar justificación y validar acceso administrativo/equipo |
| R02 Passwords compartidos / media / alto | Nueva entrega elimina contraseñas elegidas/enviadas por administradores; tokens de un uso hasta 48 h y reenvío revocable | Pruebas y CI; verificar entrega real sin exponer credenciales. Revisar cuentas antiguas de demostración antes del piloto |
| R03 Acceso cruzado o excesivo / media / alto | Ámbito Practice, permisos, auditoría y pruebas existentes; no prueba exhaustiva de todas las rutas | Inventario de rutas y matriz terapeuta/administrador/portal, revisar admin y soporte con dos prácticas |
| R04 Exposición en errores/integraciones / media / alto | Nueva lista permitida de campos en Sentry y calendario neutro; Google Drive sigue siendo salida de documentos | Revisar datos ya exportados, logs Nginx/Gunicorn y URLs con tokens; aprobar o desactivar destinos clínicos |
| R05 Proveedor sin garantías / indeterminada / alto | DPA Contabo aportado; soporte confirma que no ofrece BAA para el VPS (Francia, soporte Alemania/Chequia). BAA de R2 y otros destinatarios pertinentes no acreditado | Migrar el alojamiento clínico previsto a servicio con BAA; verificar por separado alcance de almacenamiento/copias y restantes destinatarios |
| R06 Pérdida o robo del VPS / media / alto | Root ext4 sin mapeo dm-crypt/LUKS observado; cifrado físico del proveedor no acreditado. VPS aloja otros servicios | Documentar cifrado de DB/volumen/archivos y aislamiento; plan de migración si no basta. No cifrar en caliente ni parar aplicaciones ajenas |
| R07 Pérdida de claves/copias / media / alto | Backup DB y ensayo 13/10; nueva copia cifrada de configuración fuera del VPS recuperable | Copia histórica independiente de documentos, custodia externa adicional de clave, alertas y ensayo en otro host con RPO/RTO aprobados |
| R08 Archivo hostil / media / alto | UUID privados previos; nueva validación por contenedor y límite 10 MB. PDF por firma, DOCX sin macros/embebidos, imágenes verificadas | No equivale a antivirus; evaluar cuarentena/escaneo, PDF activo y rutas Summernote/fotos antes del piloto |
| R09 Cambio/pérdida de expediente / media / alto | Firmas, digest, protección ORM/DB, auditoría y roles separados existentes | Completar adendas/correcciones, legal holds, disposición y prueba de todas las rutas de eliminación/exportación |
| R10 Incidente no detectado / media / alto | Logs de auditoría y procedimiento escrito | Ensayar respuesta con operador, alertas y acceso alternativo; demostrar formación y cobertura operativa |
| R11 Equipo/control de operador / indeterminada / alto | Operación por una persona; permisos locales de claves restringidos | Verificar cifrado de disco, bloqueo de pantalla, actualizaciones, gestor de claves, recuperación y sustitución en ausencia |

Responsable propuesto del plan: Richard Andres Marles Bonilla. No se registra su
aceptación por inferencia. Prioridad antes del piloto: contratos, R03–R09 y control
operativo; los cambios de esta entrega reducen exposición, no cierran el conjunto.

Fuente metodológica: [HHS](https://www.hhs.gov/hipaa/for-professionals/security/guidance/guidance-risk-analysis/index.html).
