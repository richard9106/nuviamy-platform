# Pending workspace inbox

`/inbox/` brings four existing follow-up workflows together. It is a live, read-only
projection, with no new completion state or background job:

- Submitted intake forms: intake-read and clinical-read permissions are both required.
  This conservative rule also covers scored questionnaires; the inbox does not load
  answers or display scores, risk labels or clinical content.
- Pending portal information submissions: client-edit permission, matching their
  existing review endpoint. Applying/reviewing changes clears the entry.
- Open portal requests (new/reviewed) and pending public bookings: requests-read
  permission. Reviewed requests remain pending until resolved. A public booking
  without a linked client displays its submitted name, without a fabricated chart link.
- Unsigned session notes: clinical-read, using the existing therapist-scoped query.
  Completed past appointments without any note are also included when clinical-create
  and appointments-read are permitted. Scheduled, cancelled, no-show and future
  sessions are not classified as undocumented just because their start time passed.
  Creating a draft replaces the missing-note item with that draft; signing removes it.

All sources and destination lookups are practice-scoped. Owners/admins see the
practice documentation queue; other clinicians see only their own notes and sessions.
Other categories follow their existing practice-wide permissions. Patient accounts
redirect to the patient portal. Platform accounts without a practice receive an empty
queue; superuser status does not grant access to another practice's records here.

The sidebar shows the actual pending-record count. The Activities menu adds this
count to unfinished setup/agreement actions and links to the inbox. Request-local
caching reuses the counts in the inbox and navigation. Different workflows for the
same person remain separate actionable records. Manual team tasks stay in Tasks.

The type filters retain the overall count, and the database paginates a union of
metadata queries in stable oldest-first order (timestamp, source, primary key),
25 records per page. No clinical response, note content, contact-detail payload or
request body is selected. Inbox actions reuse the lateral panel launcher for clinical editors and authorized
review documents. Request and read-only note details have dedicated GET views;
updates still go to the original workflow endpoints. The Requests list accepts a bounded
source/item filter for opening the specific request, still scoped to the practice.
There are no emails, bulk completion buttons, automatic approvals or record changes
from opening the inbox. Its response is not stored in browser/proxy caches.

No migration or additional provider is required. Tests cover tenant and patient
isolation, permission combinations, therapist scoping, source completion, metadata
privacy, exact request routing and stable pagination. Local validation uses fictional
records and an isolated PostgreSQL database.

## Direct actions and return to the inbox

Every follow-up action opens a same-origin lateral panel when JavaScript/dialogs
are available. New request/read-only note detail URLs independently check the
resource permission, practice and (for notes) therapist scope. Review documents
use a continuous scroll area so responses, signature receipts and action-only
forms remain visible. Intake reviews and client-information reviews reuse their
existing views; their acceptance, PHQ-9 item acknowledgement, audit and CSRF
rules are unchanged. Request review/resolve and booking approve/decline use the
existing POST endpoints. Resolving a request does not reschedule or cancel a session.

After a successful source operation, its redirect carries an explicit completion
result through the restricted drawer middleware. Only inbox-launched panels then
refresh their existing parent URL: type, pagination and browser scroll restoration
are retained. Counts come from a fresh server render; saving an unsigned draft
correctly keeps that documentation item pending. Validation redirects carry a
retry result and reopen the same source document with error feedback. Authentication
and permission redirects do not masquerade as successful completion. Other editors
retain their normal destinations, including the separate signing/reauthentication flow.

Closing without submitting keeps the same list and returns focus to its action.
Editable forms keep the existing unsaved-change confirmation. Normal links remain
available without JavaScript or through Open full page; modifier-clicks keep their
browser behavior. No iframe exception is added for sign-in, MFA, subscription payment,
clinical signing or patient endpoints. Framed POSTs preserve CSRF checks and a
bounded same-origin route allowlist. Submit controls named `action` are handled
through explicit form attributes so they cannot shadow the form destination.

Additional validation covers explicit completion versus retry, the normal full-page
fallback, CSRF rejection, authorization and tenant/therapist isolation. The existing
JavaScript lifecycle checker now exercises action-only/read-only panels, filter/page
preservation, external redirect rejection and the named-control regression. Browser
review with fictional records checked form review, request resolution, draft-note save,
unsaved-change protection, client-information review and the request panel at 390px.
