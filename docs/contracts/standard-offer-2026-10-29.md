# Actualización de la oferta estándar — 29 octubre 2026

Preparada en código por instrucción de Richard. Versión de paquete
`2026-10-29-standard-v2`, textos en
`apps/accounts/agreements/2026-10-29-v2/`; aviso de privacidad `2026-10-29-v6`.
Este documento no acredita despliegue ni aceptación por ningún cliente.

## Contenido

- DPA v2: contacto contractual corporativo. Se mantienen las obligaciones sustantivas.
- Schedule v2: proveedor AWS EMEA, infraestructura Virginia, administración España,
  SES y feedback privado, capacidades Google reales y límites de terceros/cifrado.
- BAA: mismo texto v1, sin modificar. Su alcance sigue condicionado a HIPAA y al
  servicio aprobado; el cambio de paquete no representa un BAA AWS nuevo.
- Privacidad: contacto corporativo y sección de ubicaciones/transferencias alineada.
  No se cambian permisos OAuth, usos de Google ni su política Limited Use.

La actualización **no cierra la evaluación clínica EEE**, no afirma cobertura
universal DPF y no convierte la aceptación del cliente en autorización para una
transferencia sin garantías. La evaluación por flujo se conserva en el expediente
de cumplimiento; esta publicación no registra su aprobación jurídica.

## Transición

El paquete anterior y las instantáneas/huellas de recibos no se modifican.
La pantalla de contratos muestra sus descargas históricas y la nueva oferta.
El dueño con aceptación previa recibe una actividad «Review updated agreements»;
se registra un recibo nuevo solo tras aceptación expresa y autenticación reciente.
No se añaden firmas automáticas, migraciones de recibos, cargos ni bloqueos nuevos
al trabajo o exportación de consultas existentes.

La revisión de nuevos textos no acredita retroactivamente aviso previo por cambios
de subencargados ya realizados. Los deberes de aviso/objeción del DPA siguen
aplicándose; no se retrofechan comunicaciones ni aceptaciones.

## Validación

Pruebas de aceptación, formulario obsoleto, aislamiento, descargas históricas,
actualización atribuible y conservación del recibo previo. Revisión del texto
público de servicios y reservas EEE. Las pruebas jurídicas se limitan a comprobar
que el producto conserva lo presentado/aceptado; no sustituyen un dictamen.

Resultado local: 78 pruebas ejecutadas, 75 superadas y 3 omitidas por requerir
PostgreSQL (entorno local SQLite). Sin errores del system check ni del diff.
Suite: aceptación estándar, avisos legales, contratos y dashboard. Las pruebas
específicas de PostgreSQL siguen pendientes de CI; no se afirma que se hayan
ejecutado en esta validación local.
