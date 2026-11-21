# Client portal information and electronic signatures

The portal uses the practice name in a shared masthead, with Overview, Appointments, Documents & forms, Billing & payments and My information. Dashboard section links display the relevant existing modules; older anchors remain usable. Messaging and account security remain available. Forms use a centered responsive document layout.

## Information submissions

Authenticated active portal clients can submit contact details, optional demographics, an emergency contact and insurance details. Optional front/back insurance card uploads accept validated PNG, JPEG or PDF containers up to 10 MB each. Documents use existing private document storage and authorization. No card or banking details are collected.

The browser offers a review step while retaining selected files; the server independently validates all fields and explicit confirmation. A unique submission key prevents duplicate requests/uploads. The encrypted submission is pending until a staff member with client edit permission reviews it from the client Overview. Uploaded cards appear in the secure document area. There is no email containing these details.

Staff can mark a submission reviewed or explicitly apply supported client model fields: name, contact details, address lines, birth date, emergency contact, insurance member ID and a currently enabled payer when selected. Additional structured details remain in the submission. This action does not change login email, roles, copay, rates or existing invoices. Patient appointment-email reminder preferences take effect on submission and are enforced by both the reminder query and sender. Existing preferences default to the legacy enabled behavior. These controls do not enable an unapproved sending integration, schedule messages or enable SMS/voice.

## Optional signature requirement

The template editor offers Require electronic signature. The requirement is frozen with each new assignment. Historical assignments without that snapshot flag keep the unsigned workflow. Staff sharing reviews also bind this requirement, so a template changed after review requires another review.

A client may save a draft without signing. Final submission of a signature-required form first shows the complete answers and practice-authored introduction, then a handwritten-style preview of the typed name. An explicit checkbox and Sign & submit are required. The reviewed answers and template snapshot are bound to the client, authenticated actor and a ten-minute signed review token. Changed or expired reviews cannot submit; stale or foreign-client forms cannot be signed. Relationship is Client (self); delegated/guardian signing is not provided by this flow.

The immutable receipt records assignment, authenticated signer, typed name, relationship, signing time, consent statement and SHA256 of the frozen form and responses. Submitted copies are available to the patient and authorized practice staff. Corrections require practice follow-up; existing signatures are not overwritten. PostgreSQL rejects mutation/deletion/truncation of receipts and mutation of signed content, while allowing staff to mark responses reviewed. ORM guards supplement these constraints. The runtime guard verification includes the new triggers; only disposable test teardown temporarily disables truncate guards.

Practice clinical/all exports include information submissions and signature receipts. No standard clinical consent or payment authorization text is supplied and no payment action is triggered. The practice authors and reviews its own document content.

Deployment requires clients.0006 and portal.0014/0015 through normal CI/CD, followed by the existing runtime role grants/verification. Keep the field encryption key unchanged. Local previews use fictional records, local storage and simulated email.
