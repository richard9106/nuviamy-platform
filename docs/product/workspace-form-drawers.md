# Staff workspace form drawers

Create/edit entry points in the staff workspace use a right-hand drawer, retaining the current page behind it. On small screens the drawer fills the viewport. Header and save actions remain visible while fields scroll.

## Editors covered

Existing editable modal dialogs are upgraded to the common drawer geometry, including the appointment editor opened from a client record. Its original tabs, selected client, duration, recurrence and submission controller remain intact.

Full-page editor links also open in a drawer for clients, appointments, calendar events/availability, clinical notes, diagnoses, treatment plans, invoices, session packages/usage, manual payments, document uploads, intake templates, insurance payers/rates, portal access and working hours. The explicit endpoint allowlist is `apps/dashboard/form_drawers.py`; the corresponding navigation paths are in `static/workspace-drawers.js`.

This applies to staff record editors. Login, account security, contract acceptance, clinical signing, the patient portal and Stripe checkout retain their dedicated flows. Inline actions and filters stay inline. Direct URLs, new-tab links and JavaScript-free navigation still use the original full page.

## Existing form processing

Native dialogs keep their original fields and event handlers. Other editors load their original same-origin page in an iframe, hiding duplicate workspace navigation and wrapping fields into the scrolling region. This retains original form builders, validation, CSRF and multipart upload behavior. No form values are copied into browser storage. The drawer offers an Open full page fallback.

After a successful native form POST, the server returns a small escaped redirect bridge and the parent follows the same-origin destination. Validation errors remain within the editor. Unsaved changes in these framed editors show an in-panel Keep editing / Discard changes prompt; closing is disabled during submission. The existing native dialog controllers retain their own submission and close behavior.

## Framing restrictions

Django's default DENY protection remains. Only enumerated staff editor endpoints, requested as an iframe or with `_workspace_drawer=1`, may return SAMEORIGIN / `frame-ancestors 'self'` and no-store. Anonymous users and patient accounts are excluded. Authorization, subscription, MFA and CSRF checks still run. Error responses retain their protections. Redirects outside the current host are never converted into a bridge or followed by the parent. Authentication pages cannot be embedded.

## Validation

- 105 PostgreSQL tests passed: drawer response boundaries and form persistence, clients, account security/email verification and portal profiles/signatures.
- `node ops/check_workspace_drawers.cjs` exercises opening, exclusion of authentication/external links, dirty-close protection and same-origin redirects without network access.
- Browser review with fictional local records: appointment from client profile, document upload controls and pinned footer, intake template creation with a new question and successful save, existing template editing, and 360px mobile layout (content width 360px).
- Browser screenshots are local review artifacts under `output/workspace-drawers/`; they are not production assets.

Release through the normal PR checks and main deployment workflow, together with the portal onboarding migrations. This extends the earlier client workspace release (PR #115).
