# Client/patient portal UX review — 25 October 2026

Scope: current source, local running Django application, fresh isolated SQLite database and fictional practice/patient. No production records accessed or changed, no product implementation changed. Settings and fixtures live under /tmp; email delivery and payment/provider credentials disabled. Captures are actual browser screenshots, not design mockups. Desktop: 1280 px; mobile: 390 px (375 px usable content). Browser viewport restored after testing.

## Summary

The portal covers basic appointment visibility/change requests, intake forms, secure conversations, outstanding invoices, packages and shared document downloads. Consistent colors, cards, responsive layout and emergency-use disclaimer are useful foundations. The main page does not yet prioritize the next patient action well enough. It should not be considered a complete UX or accessibility certification.

## High priority findings

1. Cancelled future appointments appear as the next appointment and in Upcoming appointments, with a green status badge and Request change action. Reproduced with a cancelled Oct 27 session and scheduled Oct 28 session. Source: apps/portal/views.py:135 only filters date, client and practice; templates/portal/dashboard.html:72 uses a success badge for every status. Exclude non-actionable states from upcoming/next and move them to history.
2. Video appointment has no Join session link despite an existing meeting_url. Current appointment card does not render the URL or explain connection instructions. Provide a clear action for eligible scheduled video appointments, with explicit time zone and availability rules.
3. Opening a conversation from the list opens an already-rendered dialog without a request to mark it read. The unread badge remained 1 after viewing and returning home. Source: templates/portal/conversations.html uses showModal only; the view marks read only for ?open= or detail-page GET. Mark read through an authenticated scoped endpoint when the conversation is actually opened, and update counters.

## Medium priority findings and recommendations

- Citas appear below messages, forms and recent requests. Move the next confirmed appointment and pending patient actions to the top. Current mobile page is ~2639 CSS px even with one pending-form section empty; avoid requiring a long scan.
- Summary cards are non-interactive metrics. Use meaningful links to the corresponding appointment/form/billing sections and provide persistent navigation for appointments, forms, documents, messages and payments.
- The form validates required inputs and pages correctly. Submission changes the pending count from 1 to 0 but provides no explicit success message or submitted-form history in this portal. Add a clear receipt/status, saved progress for long forms, and a review path for submitted packets. Current form saves only at final submission; no draft mechanism found.
- Request change is 18 CSS px high on mobile. Download is also 18 px high. Enlarge important touch controls, rather than declaring compliance from visual inspection alone. WCAG 2.5.8 specifies 24x24 px or qualifying spacing/exceptions; not all undersized controls automatically fail. Consider 44px high primary actions.
- Only open invoices are shown. Consider paid-invoice history, receipts and invoice detail/download. Online checkout is conditional on the practice's Stripe readiness; the disabled-payment message in these local captures reflects intentionally absent credentials, not proof that production payments are broken.
- Secure messages are available both as a standalone page and floating drawer; clarify which is the canonical inbox and make unread/seen state consistent. Conversation dialog lacks an accessible name and the Reply label in conversations.html is not explicitly associated with its textarea; review keyboard focus and screen-reader announcements.
- Account security is a link at the bottom; the top profile menu only exposes sign out. Put account/security/help access in a predictable location.

## Verification

- Actual local password login as a patient redirects to /portal/.
- Desktop portal and mobile layout captured. No document-level horizontal overflow at the tested mobile width (scrollWidth=clientWidth=375).
- Required empty form prevents Next; completing required fields enables Page 2; final submission succeeds and pending count updates.
- Existing staff conversation opens and content renders; unread badge issue reproduced.
- Appointment reschedule request for the scheduled session submits and displays a success confirmation. This is a request to the practice, not direct calendar rescheduling.
- Existing portal suite: 80 tests passed, including tenancy/ownership, forms, requests and mocked checkout scenarios. Passing tests did not cover the next-cancelled-appointment bug or guarantee usability.
- No real Stripe charge, external email/message delivery, screen-reader session, clinical workflow certification or full WCAG audit performed.

## Captures

- portal-desktop.jpg: entire desktop dashboard before submitting the example intake.
- portal-mobile.jpg / portal-mobile-full.jpg: mobile dashboard after successful form submission (pending count is therefore 0).
- portal-form.jpg: first page of an actual two-page intake form.
- portal-messages.jpg: actual conversation dialog.
- portal-change-request.jpg: appointment request modal, before local test submission.

## Reference criteria

- https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
- https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html
