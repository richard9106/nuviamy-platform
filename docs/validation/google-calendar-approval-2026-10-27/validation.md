# Approved Calendar rollout validation — 27 October 2026

Approval evidence: the operator supplied Google's approval email for project nuviamy / 1086176988025, specifically calendar.events.owned. Prior production inventory contained one approved connected Calendar integration and one legacy needs-reauth configuration with a Gmail flag. The temporary fictional reviewer was still active. Only aggregate status/scope information was inspected; no credentials were printed or copied.

Implemented: approved Calendar permission for all practices, canonical identity scope spelling, no inherited broad grants, server-side capability/grant/API destination enforcement, disabled Gmail/Drive connection fields and entry points, Calendar-only workspace/disclosure, removal of the demo allowlist, and an atomic audited cleanup command with a dry run and narrowly bound reviewer guard.

Local verification:

- 62 targeted tests passed in 29.923 seconds across practices integration/policy/cleanup, documents and review access. New coverage includes scope tampering, broader grants, pending obsolete requests, network rejection, preview-only cleanup, preservation of valid connections, reviewer deactivation, idempotency and aborting a misbound reviewer.
- Migration consistency: no schema changes detected. Compose runtime/migration/bootstrap credential-isolation check passed.
- An initial broader SQLite test selection included a pre-existing PostgreSQL-only rehearsal test (current_database()) that cannot execute on SQLite. The final targeted set excludes that unrelated module; complete PostgreSQL CI remains required before deployment.
- Actual local browser login with a fictional owner verified only Calendar is offered in the Google form and the disclosure is visible before connection. No real Google consent or tokens were used for the screenshot; OAuth buttons were configured with placeholder local credentials and were not submitted.
- Screenshot: integrations.jpg. No patient data included. Preview server/tab closed after review.

Production deployment, cleanup and provider checks are recorded separately after completion. Runbook: ../../operations/google-calendar-approval.md.
