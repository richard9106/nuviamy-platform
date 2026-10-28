# Validación operativa interna — 28 octubre 2026

Resultado: ensayos técnicos ejecutados con datos exclusivamente ficticios y revisión
interna de las rutas indicadas. No es certificación HIPAA/RGPD, revisión independiente,
validación clínica ni acreditación de recuperación ante pérdida total de host/región.
Las evidencias completas y los artefactos cifrados se guardan fuera del repositorio
público, en el expediente privado del operador.

## Alcance ejecutado

| Área | Ejecución y resultado | Límite |
|---|---|---|
| Disposición y restauración | PostgreSQL 16 y app en contenedores sin red TCP exterior; copia cifrada de DB + archivo ficticio. Revisión de autoridad/hold, eliminación activa ficticia, restauración antigua, bloqueo por reaparición del registro/archivo, reconciliación y conservación del registro bajo hold: pasó | No es un comando de supresión de producción ni un motor universal de retención/holds |
| Versiones y backup S3 | Bucket separado, privado y versionado, sin cambiar IAM de producción. Dos versiones de un documento y una copia cifrada ficticios. La copia descargada desde S3 coincidió con su hash independiente y se restauró en otro PG aislado. El borrado ordinario dejó un marcador y las versiones; después de autorización expresa se eliminaron las cuatro entradas, incluido el backup, con cero fallos. Se verificaron cero objetos con «Show versions» activado | No se eliminaron versiones, backups o expedientes de producción. Se conserva evidencia local; el bucket queda privado y vacío |
| Incidente técnico | Sesión ficticia inicialmente autorizada, evidencia preservada con hash, revocación mediante el flujo real con contraseña y TOTP, rechazo de la sesión antigua, rotación de contraseña ficticia, rechazo de contraseña anterior, nuevo acceso con MFA y retest: pasó. Auditoría original preservada e inmutable; aviso redactado sin enviar | Ejercicio automatizado, no tiempo de reacción humano ni formación impartida a Richard; no se enviaron avisos reales |
| Rutas y permisos | 58 solicitudes GET/POST contra 29 rutas de objetos de otra consulta, más acceso anónimo, aislamiento de pacientes de otras consultas y de la misma consulta, control positivo y CSRF: pasó. Se conservan los resultados por ruta en privado | Lista de rutas definida, no cada endpoint/rol/combinación posible ni un pentest independiente |
| Roles y postura actuales | Verificación de solo lectura del rol runtime PostgreSQL en producción: pasó. `security_readiness` observó nueve controles aprobados, cero fallos y dos revisiones humanas | Los dos estados `review` no se convierten automáticamente en aprobados por estos ensayos |

## Hallazgos corregidos y ampliación de controles

1. La acción de estado de tareas heredaba GET de `TemplateView` sin plantilla y
   devolvía 500. Se restringe a POST; la matriz lo retesta como método no permitido,
   manteniendo control de permiso y consulta de la práctica para las mutaciones.
2. La verificación de roles/restauración comprobaba nueve triggers clínicos/de
   auditoría. Ahora verifica además ocho triggers de contrato por **tabla y nombre**,
   evitando perder los nombres repetidos entre tablas. El ensayo de roles deshabilita
   un trigger contractual únicamente en su DB ficticia y exige que se detecte.
3. La recuperación reconoce los campos cifrados estrictos de soporte, además de los
   campos heredados. Una clave de campo incorrecta bloqueó el ensayo. La copia
   sintética incluye un mensaje cifrado y verifica su contenido mediante hash.
4. Una copia válida puede preceder al esquema del código que se intenta recuperar.
   La herramienta comprueba las protecciones base y aplica migraciones pendientes
   **solo a la copia desechable**, antes de validar el esquema actual, contratos,
   cifrado y firmas. El ensayo simula una copia anterior a las tablas de soporte y
   comprueba esa actualización aislada. No migra la DB de producción para verificarla.

5. Las acciones de equipo podían modificar una cuenta de plataforma asociada a la
   misma consulta. Se bloquean desactivación, reactivación, eliminación, permisos e
   invitaciones de cuentas Django staff/superuser desde ese flujo, incluso con un
   POST manipulado. Esas cuentas se administran por el canal de plataforma protegido.
   La UI retira sus acciones y el test comprueba estado, permisos y auditoría de rechazo.
   Se añaden eventos estructurales de cambios de equipo autorizados: activación,
   desactivación, eliminación, permisos e inicio de reenvío de invitación, sin contenido
   de mensajes ni credenciales. Activación, desactivación, permisos y eliminación
   se guardan atómicamente con su evento; el reenvío registra la petición previa,
   sin afirmar recepción del correo.

La copia S3 actual del servicio también se restauró en un contenedor aislado con
el código desplegado: se verificaron los 17 triggers, campos cifrados y firmas,
y se aplicó únicamente en esa copia la migración de soporte pendiente. La DB de
producción permaneció sin modificaciones; los detalles y agregados son privados.

Los tiempos registrados son de ejecuciones automáticas acotadas: la repetición con
la copia descargada de S3 duró aproximadamente 23 segundos; la ejecución local con
contratos/cifrado/migraciones aisladas duró aproximadamente 42 segundos. El retest
contiene su propia cronología por evento. Estas cifras dependen del escenario y CPU;
no miden ni prometen RPO/RTO de producción o respuesta humana.

## Recuperación y prevención de reintroducción

El control `ops.disposition_gate` es de **solo lectura**. Verifica instrucciones
firmadas con HMAC, revisión de autoridad/holds y un hash de la versión más reciente
del registro obtenido de una fuente independiente. Rechaza un registro firmado pero
antiguo, una firma cambiada, claves insuficientes o inventarios mal formados. Informa
si el inventario restaurado contiene UUID de clientes o claves de archivos cuya
supresión figura en el registro. No imprime esos identificadores, borra registros,
cambia permisos ni activa servicios.

Para una restauración real, el operador debe:

1. Mantener la copia aislada, sin clientes, tareas, correo ni integraciones activas.
   No restaurar encima de un servicio abierto ni rehabilitarlo durante la revisión.
2. Obtener la instrucción vigente y su hash/clave desde custodia independiente de
   la copia restaurada. No fiarse del registro incluido en una copia antigua.
3. Generar un inventario completo y protegido de los datos/archivos restaurados y
   revisar las versiones y destinos aplicables. El control comprueba lo que contiene
   ese inventario; no descubre por sí mismo todos los proveedores/copias existentes.
4. Ejecutar el control y mantener bloqueada la puesta en servicio si falla o requiere
   revisión. Reconciliar únicamente instrucciones vigentes y autorizadas, respetando
   obligaciones de conservación y sin saltarse las protecciones de notas/contratos.
5. Invalidar sesiones e integraciones recuperadas; revisar las credenciales revocadas
   después de la copia. Validar roles, esquema, cifrado, firmas y el inventario de nuevo.
6. Conservar evidencia de la revisión y aprobación del operador antes de conectar
   usuarios o activar jobs. Un resultado JSON favorable no activa el servicio ni
   sustituye esa aprobación.

No hay un conmutador global de legal holds ni una ejecución automática de disposición
por este cambio. El ejemplo `ops.drill_scenario` **rechaza** bases ajenas a su patrón
sintético y configuración aislada; no debe adaptarse improvisadamente para borrar
una consulta real. Disposición por campos, obligaciones diferentes por documentos,
versiones externas y conservación legal necesitan su propio alcance verificado.

## Reproducción y mantenimiento

- Pruebas: `ops.test_disposition_gate` y `apps.accounts.test_operational_drills`.
- Ensayo acotado: `python -m ops.run_operational_drill --image IMAGEN_REVISADA --evidence-dir DIRECTORIO_PRIVADO`.
  Crea exclusivamente contenedores/bases propios, usa sockets Unix sin red exterior,
  no carga `.env` de producción y elimina solo sus contenedores/volúmenes temporales.
- La evidencia/clave actual del registro y los archivos sintéticos no se publican ni
  se suben como artefactos de CI. Las pruebas en CI usan una copia nueva y aislada.
- `ops.verify_downloaded_drill` reproduce únicamente la copia sintética cuyo hash y
  clave coinciden con el expediente independiente. No es un restaurador genérico.
- CI repite el ensayo offline, la matriz y los controles de roles/backup. La eliminación
  real en S3 requiere una autorización específica y no se automatiza en producción.
- Repetir tras cambios de autenticación, esquema, permisos, claves o almacenamiento,
  y conforme al programa de revisiones. Registrar alcance, responsable y resultados.

Pendientes fuera de este cierre técnico: instrucciones clínicas de cada consulta,
evaluación/contratos UE y respuesta de AWS, custodia y contactos alternativos,
validación clínica, revisión independiente y ensayo de pérdida total del host/región.
No ampliar el resultado a esos ámbitos ni anunciar cumplimiento integral por pasar CI.

Referencia técnica: [AWS: eliminación de versiones](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html).
