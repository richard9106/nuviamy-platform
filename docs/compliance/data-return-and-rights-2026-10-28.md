# Conservación, derechos y salida — revisión del 28/10/2026

Estado: procedimiento y correcciones preparados; no acredita cierre integral de
retención ni autorización para eliminar producción. No se han borrado expedientes,
objetos, versiones ni copias reales. Las reglas definitivas de una consulta piloto
requieren país/estado/comunidad, profesión, edades y tipos documentales confirmados.

## Flujo operativo

1. Recibir una solicitud en soporte autenticado, sin adjuntar expedientes ni datos
   clínicos. El inicio de sesión acredita una cuenta; no acredita por sí solo la
   representación de la consulta ni la autoridad sobre un expediente concreto.
2. Richard verifica identidad, representación, alcance y la instrucción. Las
   solicitudes de pacientes se remiten a su consulta responsable. Registrar recepción,
   norma/plazo aplicable, vencimiento, responsable y actuaciones sin esperar al cierre
   de la cuenta. Usar la [plantilla de caso](templates/data-rights-case.json) en el
   expediente restringido; no completar ese JSON con datos personales en Git.
3. Completar la matriz de conservación por clase de registro: jurisdicción,
   profesión, adultos/menores, fundamento, inicio del cómputo, plazo/excepciones,
   responsable de custodia y holds. No deducir un plazo único de HIPAA o RGPD ni
   convertir el mínimo español en una fecha automática de eliminación.
4. Para devolución a una consulta, el propietario/admin autorizado descarga el
   archivo ZIP con el alcance acordado. Verificar inventario, recuentos, relaciones,
   documentos y hashes; confirmar recepción por el destinatario correcto. Este ZIP
   de toda la consulta **no** se entrega sin revisar a un paciente individual.
5. Una respuesta individual requiere selección de datos pertinentes y revisión de
   información de terceros y límites clínicos aplicables por el responsable. La
   exportación general no es un motor automático de respuesta a derechos. Mantener
   notas firmadas y sus adendas; no reescribir el original para resolver una corrección.
6. Solo después de instrucciones verificadas, deberes de conservación/holds
   resueltos y un plan autorizado se programa disposición. Distinguir DB activa,
   archivos actuales, versiones históricas, copias, snapshots, datos de proveedores
   y evidencias sujetas a conservación propia. Conservar motivo, alcance, ejecutor,
   verificador, fechas y las excepciones legalmente retenidas.
7. No cerrar el caso de supresión con un simple `DELETE` de la app o una eliminación
   de archivo actual: en almacenamiento versionado puede quedar una versión anterior.
   Registrar expiración efectiva de copias y cómo impedir reintroducción al restaurar.
   Un hold puede exigir preservar copias fuera de su ciclo ordinario. No ejecutar un
   borrado que pueda entrar en conflicto con un hold sin revisión específica.
8. Confirmar por canal autenticado qué se devolvió, eliminó o sigue conservándose,
   con fundamento y alcance. No afirmar borrado irreversible ni completo sin pruebas
   de todos los destinos. La cancelación no instruye por sí sola la supresión.

La ley española exige conservar documentación clínica con las condiciones de su
[artículo 17](https://www.boe.es/buscar/act.php?id=BOE-A-2002-22188#a17); también hay
que considerar reglas territoriales y profesionales. La determinación jurídica
concreta no se sustituye por esta plantilla. Véanse el [marco de conservación](retention.md)
y la evaluación UE, que sigue pendiente en el expediente del proyecto.

## Correcciones del producto

La exportación anterior omitía contactos de emergencia/direcciones, respuestas y
plantillas de formularios, solicitudes y conversaciones del portal, datos de autoría,
uso de paquetes y otros registros de la consulta. Además, omitía un documento que
no pudiera abrir sin informar de que el ZIP estaba incompleto.

La revisión amplía los campos mediante una lista explícita por modelo. Incluye los
registros del alcance elegido y los archivos actuales de documentos/fotos capturados.
El ZIP contiene `practice-data.json`, `manifest.json`, archivos con rutas basadas en
IDs y `README.txt`. El manifiesto identifica recuentos, correspondencias de archivos,
tamaños y SHA-256. Una referencia de documento vacía, archivo ausente o error de
almacenamiento impide entregar un ZIP parcial; se conserva todo y se registra el
fallo estructural, sin nombres ni rutas en el mensaje ni en auditoría.

Las contraseñas, MFA, tokens OAuth y conversaciones privadas de soporte quedan fuera
de la exportación de la consulta. Los servicios externos, backups y versiones
históricas requieren el proceso de salida separado. Las cadenas de Excel se escriben
como texto cuando podrían interpretarse como fórmulas; el JSON conserva el original.
PDF/SVG son resúmenes; Excel no incluye archivos binarios. Los hashes comprueban los
bytes capturados, no la autenticidad del emisor ni una instantánea coordinada frente
a cambios simultáneos. Coordinar una ventana sin modificaciones para una devolución.
Para volúmenes que excedan la descarga síncrona actual se necesita una devolución
operativa planificada, no se promete exportación ilimitada.

El vencimiento de prueba o la cancelación mantienen lectura/exportación conforme a
permisos. La conversación de soporte queda disponible para seguimiento de salida,
incluido enviar respuestas, sin reactivar la suscripción ni permitir nuevas altas
clínicas. Los controles de identidad, permisos y MFA correspondientes siguen vigentes. Una
exportación requiere autenticación reciente, incluso para usuarios sin TOTP obligatorio;
la confirmación vuelve al formulario para repetir la descarga, sin reproducir un POST
como GET ni almacenar su contenido.

## Evidencia y límites de cierre

El ensayo automatizado usa exclusivamente datos ficticios y almacenamiento local
temporal: documento y foto, datos de contacto, formularios con snapshot/respuestas,
solicitudes y conversaciones del portal. Comprueba contenido devuelto, hashes,
separación entre consultas, ausencia de credenciales, control de roles, fallo de
archivo y persistencia de datos tras expiración/cancelación. No envía correos reales,
no cobra y no toca producción.

Pendientes que no se consideran cerrados:

- Matriz clínica y aprobación de instrucciones concretas de la consulta piloto.
- Motor integral de legal holds/retención y prevención de todas las eliminaciones
  incompatibles. Las acciones existentes de borrado de registros/archivos no han
  pasado a ser un flujo completo de disposición por esta revisión.
- Ejecución autorizada y verificación de supresión en DB, objetos/versiones, copias,
  proveedores y reintroducción tras restauración. No se ha hecho una eliminación
  integral ficticia sobre versiones S3/backups por este ensayo local.
- Validación clínica de una respuesta individual y recepción/importación del archivo
  por una consulta/destinatario independiente.
- Simulacro técnico cronometrado de incidentes y revisión final de seguridad.

La implantación del exportador no permite marcar todos esos puntos como completados.
