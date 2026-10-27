# Decisiones por flujo — 27 octubre 2026

Inventario operativo actual. Los contratos, planes, cuentas, evidencias y revisiones
detalladas se conservan fuera de este repositorio público. «Pendiente» no autoriza PHI.

| Flujo / proveedor | Decisión operativa | Evidencia o cierre pendiente |
|---|---|---|
| App/DB/documentos/backups y auditoría AWS | AWS es el origen actual; BAA activo en Artifact comprobado. Usar solo servicios elegibles configurados y acceso mínimo | Mantener pruebas de cifrado, accesos, recuperación, entregas y revisión. El BAA no certifica la app |
| Correo de acceso a pacientes / Brevo | Cobertura contractual para PHI no acreditada. No se aprueba el flujo clínico por minimizar el cuerpo; conservar correo administrativo/operativo separado | Alternativa seleccionada: SES bajo BAA AWS. Identidad nuviamy.com creada, DKIM RSA-2048, pendiente DNS, acceso de producción, política mínima y prueba. No se ha cambiado el envío live ni asumido entrega en sandbox |
| Correo de incidencias al operador | Mensajes mínimos sin datos clínicos, tokens o credenciales. Richard autorizó prueba y avisos automáticos | SMTP aceptó la prueba y Richard confirmó recepción. Falta un canal independiente del host/proveedor |
| Calendar opcional | Solo calendario propio, bloques «Reserved time», sin nombres/notas/asistentes/ubicación/enlaces clínicos. Mantener minimización | OAuth aprobado no es BAA. Cuenta Google de cada consulta y evaluación del flujo de horarios requieren instrucción/cobertura adecuada |
| Gmail/Drive | No habilitar | Bloqueados en la integración actual; nueva función exige evaluación contractual y permisos antes de activarse |
| Stripe SaaS | Solo contacto y cobro comercial de la consulta | No remitir expedientes/diagnósticos/PHI en metadata. Evaluar por separado el pago de pacientes y las excepciones aplicables; no aprobarlo por analogía |
| Sentry | Solo diagnósticos estructurales sanitizados; trazas/breadcrumbs/contenido libre descartados | Revisar eventos/retención históricos y contrato/plan real. Sentry ofrece BAA para Business/Enterprise, pero no se ha acreditado aceptación de NuviaMy. No activar PHI ni comprar plan por este documento |
| Cloudflare DNS | DNS y autenticación del dominio; no convertir la app clínica a proxy ni habilitar analítica clínica | Verificar que raíz/www sigan DNS-only y no se habiliten servicios nuevos de tratamiento clínico por este trabajo |
| Cloudflare Email Routing/Gmail soporte | Canal administrativo con aviso de no enviar PHI | Evaluar contrato/canal alternativo antes de aceptar expedientes. El reenvío no se convierte en correo HIPAA por tener dirección corporativa |
| GitHub/CI | Código y despliegue, sin datos de pacientes ni artefactos de backups/configuración | Mantener secretos y permisos mínimos. Informes de accesos/dispositivos/contratos y resultados con agregados son privados |
| Contabo/R2 y copias locales históricas | Recuperación histórica restringida, no producción nueva | Inventario privado, decisión autorizada de retención/retirada y evidencia de disposición. No borrar ni reactivar automáticamente |

No se deduce que Brevo firme o no firme BAA de una fuente secundaria. La ausencia
de evidencia del contrato de esta cuenta basta para mantener pendiente el flujo.

Fuentes verificadas:
- [AWS, servicios HIPAA elegibles](https://aws.amazon.com/compliance/hipaa-eligible-services-reference/).
- [AWS, elegibilidad SES](https://aws.amazon.com/about-aws/whats-new/2019/07/amazon-ses-achieves-hipaa-eligibility/).
- [Sentry, acceso al BAA en planes Business/Enterprise](https://www.sentry.help/en/articles/16499798-how-can-i-get-a-pdf-copy-of-the-business-associate-agreement-baa).
- [HHS, nube y contratos según el flujo](https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html).
