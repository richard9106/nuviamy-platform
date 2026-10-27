# Privacy/security readiness review — 27 October 2026

## Scope and outcome

Read-only production observations at main 3128d7a8b2bd48839ab5c981bf180fcb7d46b66e,
source review and synthetic local tests. No patient record bodies, credentials,
tokens, outbound messages, charges, account changes or production package changes.
Detailed operational findings and account aggregates are held in the restricted
operator evidence directory outside this public repository.

The new read-only report was evaluated in memory in the existing production Django
process environment, without installing code or modifying its checkout: eight
technical checks passed, none failed, three require human evidence/review. It does
not assess every route, AWS policy, contractual duty or clinical workflow and always
reports `compliance_approved=false`. Richard confirmed responsibility for security
and privacy; this is not approval of residual risk or proof of training.

Python 3.12.16 and Django 5.2.18 are running; this supersedes those two version
findings in the October 25 review. SMTP TLS, secure sessions, required email second
step, native S3, absent reviewer bypass, no Sentry tracing and restricted runtime
PostgreSQL privileges were observed. Scheduled backup and Certbot last observed
service results were successful, without repeating restoration or alert delivery.
AWS SSO was expired; the application role cannot inspect bucket policies. Historical
October 20 infrastructure evidence is preserved, not represented as a fresh check.

## Changes

- Provider exceptions are replaced with fixed messages in the Calendar workspace
  and failed reminder storage. Regression tests use fictional patient/token markers.
  Existing historical error fields are not inspected or erased by this change.
- `python manage.py security_readiness` emits bounded JSON from configuration and
  aggregate authentication metadata, without patient data, account identifiers,
  secrets or network calls. It performs SELECTs only. Keep output restricted: account
  counts and failed operational controls should not be posted publicly.
- Failed technical checks return a nonzero exit code. `--fail-on-review` also returns
  nonzero for outstanding manual review. A normal zero exit code is not certification.
- Current compliance documents distinguish AWS/standard agreements from historical
  Contabo/R2 and bespoke-contract drafts. Owner-specific actions remain open.

## Validation

- 40 targeted tests passed in 26.035 seconds: the report, integration settings,
  Calendar exception redaction and appointment model/reminder error handling.
- Migration consistency: no changes detected.
- 92 broader authentication, contract, document, readiness and Google approval
  regression tests completed successfully in 39.337 seconds on SQLite; two
  PostgreSQL-specific tests were skipped. Full PostgreSQL CI remains required.
- PR CI is tracked with the change; no deployment is claimed by this report.

## Remaining closure

See [the current closure register](../../compliance/closure-2026-10-27.md). An executed
BAA, review of each real data flow, approved retention/holds, device and recovery-key
protection, access review, measured recovery/alerts and actual training/exercises are
separate evidence. No consent, signature, incident exercise or clinical approval was
fabricated by publishing these documents.
