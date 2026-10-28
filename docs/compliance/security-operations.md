# Operación de seguridad de NuviaMy

Versión 1, 27 octubre 2026. Responsable: Richard Andres Marles Bonilla.
Preparada e implantada en el alcance indicado por delegación expresa del responsable
(«encárgate de cerrar esos puntos como creas conveniente»). No firma contratos por
terceros, acredita formación no realizada ni acepta riesgos residuales desconocidos.

## Alcance y autorización

Aplicación, PostgreSQL y objetos de producción en AWS, más equipos y operadores que
puedan acceder a ellos. HIPAA se evalúa según el rol de NuviaMy y del cliente; también
se revisan RGPD, transferencias y obligaciones profesionales de la consulta.
El BAA AWS activo cubre servicios elegibles de esa cuenta, no todos los proveedores.
No se anuncian certificaciones HIPAA/HITRUST ni una revisión independiente inexistente.
El [expediente fechado](closure-2026-10-27.md) gobierna el estado de cada control.

## Identidad y equipos

- Cuenta nominativa; cada acceso privilegiado requiere motivo y responsable en el
  inventario restringido. Revisar mensualmente y al cambiar de función/incorporarse/salir.
  Retirar accesos que ya no sean necesarios mediante un cambio registrado que preserve
  al menos un operador autorizado con recuperación comprobada. No compartir cuentas.
- TOTP obligatorio para staff/superusuarios en producción; política de segundo paso por
  correo para el resto según configuración. El código exige inscripción, pero cada
  persona debe completar su autenticador y guardar códigos fuera del dispositivo.
  No pedir contraseñas, semillas ni códigos por chat o soporte.
- Gestor de contraseñas, actualización automática y equipo protegido; bloqueo tras
  cinco minutos de inactividad. Cifrado del disco y custodia de recuperación deben
  comprobarse técnicamente. Una declaración del operador se registra como tal.
- Las claves de descifrado y recuperación no se guardan en Git ni junto al único
  backup. Mantener una segunda custodia cifrada independiente y probar su uso.
  No convertir en caliente el disco del operador ni borrar claves para cumplir el papel.

## Datos y proveedores

Mantener la [matriz de flujos](vendor-decisions-2026-10-27.md). Un proveedor recibe
solo lo necesario; un DPA o el cifrado no reemplazan un BAA cuando corresponda.
Nuevos destinos clínicos requieren evaluación contractual y técnica antes de activarlos.
Soporte ordinario, GitHub y diagnósticos externos no son destinos de expedientes.
Usar identificadores estructurales para diagnosticar; no copiar historias a tickets.
Restringir el acceso a evidencia histórica de proveedores retirados hasta acordar
disposición; nunca reactivar un origen obsoleto ni borrar copias sin autorización.

## Auditoría y revisión

CloudTrail multirregión, integridad habilitada, eventos de objetos y logs S3 según
[runbook](../operations/aws-audit-logging.md). No confundir estar habilitado con haber
validado una cadena de digests o cada entrega. Los logs de acceso web nuevos omiten
URLs, consultas, referrers y user agents; la aplicación conserva auditoría de actores,
acciones y recursos sin contenido clínico. Los errores/históricos pueden ser sensibles:
acceso restringido, no exportarlos a herramientas no aprobadas ni destruirlos.

Revisión operativa diaria de salud/backups y semanal de anomalías de acceso/auditoría;
mensual de privilegios, pendientes y proveedores; extraordinaria tras incidentes,
cambios de infraestructura, funciones, personal o requisitos aplicables. Estos son
procedimientos adoptados, no pruebas de que ya se hayan ejecutado todas las revisiones.

## Continuidad y avisos

- Objetivos internos seleccionados para el inicio: RPO 24 horas, RTO 8 horas; no son
  SLA ni rendimiento acreditado. Backup PostgreSQL diario, snapshots y objetos/versiones
  conforme a su configuración real. El monitor avisa al superar 26 horas (margen
  operativo de dos horas); no demuestra por sí mismo alcanzar RPO 24 horas.
- Monitor cada 15 minutos: HTTPS válido, salud, resultado de backup/Certbot, timer y
  existencia de backup cifrado reciente en S3. Avisa al responsable por tipo de fallo,
  sin PHI/secretos, al cambiar el fallo o cada 24 h si persiste. Fallar el envío conserva
  el fallo local. Revisar el estado aun cuando no haya correos.
- El monitor está en el mismo host y usa el mismo correo: no detecta ni avisa de su
  propia pérdida total. El workflow `Public availability check` consulta HTTPS desde
  GitHub cada 30 minutos una vez en main; no usa credenciales AWS ni PHI. Sus avisos
  dependen de las notificaciones de Actions del operador y pueden retrasarse: probar
  ese canal y la custodia alternativa antes de cerrar pérdida del host/cuenta.
- Ensayar restauración aislada mensualmente y tras cambios de claves/esquema/storage.
  `ops/verify_s3_recovery.py` restaura la copia S3 autenticada en PG sin red exterior,
  comprueba guards, lectura de campos cifrados y firmas, y destruye solo su contenedor
  temporal. No escribe la DB de producción. Evidencias y agregados van fuera de Git.
- El ensayo en el mismo servidor no prueba pérdida de región/servidor ni recuperación
  integral de documentos, claves, identidad y DNS. Ensayar eso antes de prometer RTO.

## Conservación, derechos y salida

Aplicar [retention.md](retention.md). Cada consulta fija su matriz según jurisdicción,
profesión, adultos/menores, contratos y obligaciones, antes del uso clínico. Registrar
la instrucción y quién puede autorizarla; no inventar un plazo clínico universal.
La cancelación no borra expedientes. Verificar identidad/autoridad de cada solicitud;
registrar ticket, alcance, exportación/rectificación/devolución, verificación y respuesta.
Correcciones de notas firmadas por adenda; nunca sobreescribir el original.

Los legal holds se registran y se ejecutan operativamente bloqueando cualquier
disposición afectada, incluidas copias. No existe motor universal de holds; no anunciarlo.
La eliminación requiere revisar objetos/versiones/backups, obligaciones y reaplicación
tras restauración. No ejecutar borrados masivos como parte de esta implantación.
Conservar documentación exigida de seguridad al menos seis años desde creación o
última vigencia, la fecha posterior; este plazo no define la historia clínica.

## Incidentes, formación y evaluación

Aplicar [incidents.md](incidents.md): preservar evidencia, contener sin destruir,
determinar alcance, informar al cliente sin demora injustificada y conforme al contrato,
evaluar obligaciones legales, recuperar y registrar retest. No esperar al plazo máximo
legal para empezar a informar. El canal de soporte recibe solo avisos mínimos.

Antes de acceso a datos clínicos: repasar phishing, mínimo privilegio, MFA, equipo,
soporte sin PHI, exportación, retención y aviso de incidentes; registrar fecha,
participantes y comprensión en privado. Realizar el escenario de credencial expuesta
con el responsable: la revisión del guion por un agente no acredita formación humana.

Revisar el análisis de riesgos al menos anualmente y ante cambios/incidentes; priorizar
por probabilidad/impacto, responsable, fecha y evidencia de retest. El análisis debe
cubrir todo el entorno, no solo este listado de código. La revisión independiente
y validación clínica siguen siendo criterios de salida del proyecto, no un certificado
HIPAA oficial ni una auditoría independiente ya terminada.

Referencias: [HHS Security Rule](https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html),
[HHS análisis de riesgos](https://www.hhs.gov/hipaa/for-professionals/security/guidance/guidance-risk-analysis/index.html),
[HHS contratos](https://www.hhs.gov/hipaa/for-professionals/covered-entities/sample-business-associate-agreement-provisions/index.html).
