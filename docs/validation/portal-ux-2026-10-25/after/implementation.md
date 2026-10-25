# Client portal improvements — 25 October 2026

Implemented following the findings in ../review.md. Preview and browser testing used an isolated local SQLite database with fictional records, disabled external delivery/payment credentials and a disposable patient account. No production patient data was accessed or changed.

## Behavior

- The overview prioritizes the next scheduled appointment (including an ongoing session), the client's pending forms, unread messages and outstanding invoice share.
- Cancelled, completed and no-show sessions are excluded from upcoming appointments. A collapsed recent-history section preserves their status without offering a change action.
- Scheduled video sessions expose their existing HTTP/HTTPS meeting link, opening a separate tab. A missing video link has an explanatory message. Displayed appointment times explicitly identify the active application time zone; this does not introduce per-patient time zone preferences or provision a video provider.
- Shared navigation links to appointments, forms, messages, documents and payments. Account security is in the profile menu. Main actions, download links and change-request buttons have comfortable touch targets.
- Client conversations use the existing scoped detail page, which marks only the displayed conversation's staff messages read. The inbox, legacy ?open= links and client chat shortcut lead there. The staff chat drawer is unchanged.
- Forms support explicit server-side “Save and continue later.” Partial answers remain assigned, validate choice/length constraints, and are restored on reopening. They are not stored in browser local storage. Draft responses are withheld from the practice's response view until final submission.
- Final submission retains required-field validation, shows a status confirmation and adds a read-only response page. A locked status check prevents a stale submitted form from being overwritten as a draft.
- Recent submitted forms and paid invoices are visible. Appointment and paid-invoice histories show up to ten recent records; submitted-form history also shows ten recent records. This change does not generate PDF invoices/receipts or process ERAs.
- Invalid general/change requests retain the full dashboard context and form errors. Requests show a success confirmation.

## Verification

- `manage.py test apps.portal --noinput`: 90 tests passed in 102.740 seconds, including ten new regression tests (Django 5.2.18, isolated SQLite settings).
- Regression coverage: ongoing/cancelled session ordering, safe video links and ownership, selected-message read state, foreign conversation isolation, draft/resume/final validation, draft length/choice rejection, immutable and scoped submitted responses, paid-history isolation, invalid-request rendering, and withholding draft responses from the practice.
- Actual browser: partial save with required questions unanswered; resume with saved answer; page navigation; final submit and confirmation; read-only submitted responses; conversation opening and cleared unread counter.
- Mobile viewport 390 × 844: document scrollWidth and clientWidth both 375 px. Request change and Download measured 44 px tall. Desktop 1280 × 900 visually inspected.
- Manifest static collection succeeded, including the new portal stylesheet and changed intake JavaScript. No model migrations required. No browser console errors observed in the tested portal tab.
- No real payment, external video call, production deployment, screen-reader session or full accessibility certification performed.

## Captures

- portal-overview.jpg: desktop first screen.
- portal-desktop.jpg: full desktop dashboard.
- portal-mobile.jpg / portal-mobile-full.jpg: mobile dashboard.
- form-mobile.jpg: resumed draft before submission.
- submission-mobile.jpg: explicit submission status.
- responses-mobile.jpg: submitted responses.
- messages-mobile.jpg: opened secure conversation.

Screenshots contain only fictional data. Pending-form and unread counts vary because the workflow was exercised during capture.
