# Product support and patient checkout — 2026-10-28

Implementation prepared for review; not a record of production deployment or full
HIPAA/RGPD approval. Existing accepted customer agreement snapshots are unchanged.

## Support boundary

- `/help/contact/` stores enquiries in the application database. Contact name, email
  and all message bodies use Fernet encryption with the existing protected
  `FIELD_ENCRYPTION_KEY`; missing/incorrect keys fail closed. The key must remain
  available for authorized recovery; this is not end-to-end encryption.
- Practice users follow their own requests at `/help/requests/`. Access requires
  both the original requester and current practice membership. Other members,
  including owners in the same practice, cannot open the conversation.
- Only active platform superusers can review support in Django admin. Existing
  privileged MFA remains required in production. Review and reply actions produce
  structural audit records without message content. Existing messages cannot be
  edited or deleted through the support admin; new replies identify their author.
- Email carries generic update notices only: no question, reply, contact details
  in the body, topic, ticket identifier, Reply-To or attachment. Sending failures
  preserve the request and record a generic failure event. Recipients' addresses
  still reach the transactional provider as required for delivery.
- Public submissions have no public conversation URL or unverified email-based
  access grant. Administrative follow-up is manual after identity verification as
  appropriate; private replies require a signed-in practice account.
- Patient portal accounts are directed to their treating practice. The feature
  does not accept attachments and warns against names, clinical records,
  passwords and card details. A support request is not authorization to inspect
  clinical records. If clinical information arrives accidentally, restrict access,
  record the incident and follow the incident-handling procedure; never copy it
  into an ordinary email reply.
- CSRF protections, POST limits, no-store caching and noindex remain in place.
  Retention/disposal is an authorized operational process, not automatic deletion
  when a ticket closes. Do not promise a universal retention period or instantaneous
  erasure from backups. Backup handling follows the existing recovery policy.

## Patient checkout boundary

`ClientInvoicePaymentView` validates portal ownership, eligible invoice status,
client balance and the practice's Connect readiness before starting Checkout.
The hosted product name is fixed to `Practice invoice payment`; the configurable
invoice number is no longer copied to Stripe's description.

The amount, currency, payer email, connected account destination and internal
invoice/practice/client references still reach Stripe. The references support
ownership matching and payment reconciliation in the signed webhook, including
insurance client-share payments. They are personal data, not anonymization.
No appointment purpose, diagnosis, clinical note, service-code description or
free-text invoice number is sent by this Checkout call. Card entry is hosted by
Stripe. This review does not cover information a practice separately enters in
its Stripe account, Stripe's own collection, or every possible financial workflow.

SaaS subscriptions remain a separate business-to-business flow. The current
[Stripe DPA](https://stripe.com/es/legal/dpa) describes both controller and
processor purposes; it does not establish a BAA or blanket permission to send
clinical records. The [HHS business-associate guidance](https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/business-associates/index.html)
distinguishes financial transactions from wider services involving PHI. Do not
extend a payment exception to all billing, practice management or EU data handling.
The previously identified EU transfer/contractual assessment remains open.

## Release and verification

- Migration `dashboard.0003_supportticket_supportmessage` adds two tables. No
  existing contact-email archive is imported or erased. Verify backups/key custody
  before release; run migrations before exposing the new routes and collectstatic.
- Privacy notice version becomes `2026-10-28-v5`, describing protected support,
  minimized Checkout, SES delivery and current Calendar-only Google capabilities.
  OAuth scopes and consent-screen configuration are not changed by this patch.
- Help text no longer advertises Gmail/Drive or temporary passwords.
- Regression tests cover encryption, fail-closed storage, tenant/requester access,
  CSRF, XSS escaping, reply limits, closed requests, generic notices, failure
  persistence, superuser-only review, immutable previous messages and privileged
  MFA. Checkout regression asserts that the free-text invoice number is absent.
- Local desktop/mobile visual review uses synthetic requests only. Production
  support operation, retention requests and accidentally submitted clinical data
  still require the responsible operator's procedures and judgment.
