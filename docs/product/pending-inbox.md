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
request body is selected. Clinical editors reuse the existing lateral panel launcher;
other actions go to their original review view. The Requests list accepts a bounded
source/item filter for opening the specific request, still scoped to the practice.
There are no emails, bulk completion buttons, automatic approvals or record changes
from opening the inbox. Its response is not stored in browser/proxy caches.

No migration or additional provider is required. Tests cover tenant and patient
isolation, permission combinations, therapist scoping, source completion, metadata
privacy, exact request routing and stable pagination. Local validation uses fictional
records and an isolated PostgreSQL database.
