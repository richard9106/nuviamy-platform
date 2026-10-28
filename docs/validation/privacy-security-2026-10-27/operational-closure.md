# Controles operativos adicionales — 27 octubre 2026

Trabajo autorizado por Richard para cerrar privacidad/seguridad. Evidencias sensibles,
inventarios, configuración anterior y resultados con agregados quedan en el expediente
privado del operador. No se publican logs, secretos, datos clínicos ni contratos.

## Cambios activos fuera del despliegue de aplicación

- Bloqueo GNOME habilitado; espera de inactividad corregida de desactivada a cinco
  minutos, con bloqueo sin demora. La inspección no acredita cifrado de disco aunque
  el responsable lo declara; no se ha convertido ni formateado el disco.
- Nginx: configuración comprobada con `nginx -t` y recargada. Nuevas entradas de
  acceso contienen tiempo, método, estado, bytes y duración; no URL/query/referrer/UA.
  Probe ficticia HTTPS y comprobación del último registro confirmaron omisión del
  marcador y consulta. Históricos conservados, sin purga ni exportación externa.
- Recuperación: descarga de copia PostgreSQL cifrada de S3 con rol existente,
  descifrado GPG autenticado, restauración real en contenedor PG con red `none`,
  sin puertos/volúmenes de producción y con recursos limitados. Se comprobó esquema,
  guards requeridos habilitados, lectura de valores cifrados y firmas de notas.
  Solo se retiró el contenedor temporal creado por la prueba. Salud productiva 200
  tras el ensayo; no se escribió la base de producción.
- Alertas: Richard autorizó un mensaje de prueba y confirmó recepción; después
  autorizó avisos automáticos mínimos. Timer cada 15 minutos habilitado, servicio
  ejecutado con éxito y cinco comprobaciones correctas: HTTPS/salud, resultado
  backup y Certbot, timer de backup activo y copia cifrada reciente en S3.
  Correos deduplicados por fallo con repetición diaria. La prueba acredita canal,
  no una caída real inducida. No se paró la aplicación ni se provocó un backup fallido.
- Correo SES: creada identidad del dominio, Easy DKIM RSA-2048. No se activó VDM,
  IP dedicada, plan premium ni cambio del proveedor SMTP en producción. Tres CNAME
  DNS-only publicados y resueltos; pila independiente TLS/IAM mínima CREATE_COMPLETE
  tras autorización expresa. Solicitud de producción enviada con aceptación autorizada
  de términos; AWS muestra en revisión. Aprobación AWS/feedback y entrega condicionan el corte.
- Nueva copia cifrada de configuración del origen AWS, incluyendo claves de aplicación,
  Compose, TLS, Nginx y unidades operativas: descifrado autenticado a memoria y rechazo
  de alteración comprobados. Clave privada permaneció local, sin extraer texto a disco.
  No constituye una segunda custodia independiente de esa clave.
- Richard respondió correctamente tres escenarios sobre soporte con PHI, credencial
  expuesta y conservación/holds. Registrado como ejercicio breve de concienciación y
  decisiones de escritorio; no simulacro técnico cronometrado ni formación integral.

## Cambios de aplicación preparados

- TOTP obligatorio para staff/superusuarios en producción aunque MFA global esté
  desactivado. El usuario debe inscribirse y custodiar recuperación; no se crean
  semillas ni se rellenan códigos por él. No se retiran privilegios sin revisión.
- Gunicorn: formato de acceso estructural sin URL/query/referrer/UA/IP; se mantiene
  auditoría detallada de acciones dentro de la aplicación.
- Web pública: tres mensajes factuales — almacenamiento cifrado, conexiones seguras,
  BAA AWS — y aclaración del alcance, sin certificaciones HIPAA/HITRUST.
- Scripts repetibles y procedimientos versionados. Tests de redacción usan átomos
  reales de Gunicorn; selección de backup rechaza copias ausentes/antiguas/futuras/
  vacías/excesivas; deduplicación de avisos probada. Tests MFA cubren redirección
  antes del dashboard, disponibilidad de inscripción y usuarios no privilegiados.

El estado de CI/despliegue debe consultarse en el PR y su ejecución; este documento
no transforma cambios locales en controles activos. El despliegue se registra después.

## Límites de cierre

El ensayo comparte host/región con producción y no restaura documentos históricos,
DNS ni credenciales desde una custodia independiente. El monitor tampoco alerta si
desaparece el propio host. Faltan inscripción MFA, inventario/decisiones sobre cada
privilegio, evidencia de cifrado/custodia del equipo, contratos por flujo, matrices
clínicas reales de conservación, formación/simulacro humano y evaluación de cierre.
No se interpreta la delegación como firma por clientes, formación completada o
aceptación de cualquier riesgo. No se declara cumplimiento HIPAA integral.
