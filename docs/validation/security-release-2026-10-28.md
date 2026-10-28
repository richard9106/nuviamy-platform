# Security operations follow-up — 28 October 2026

This updates the dated [closure record](../compliance/closure-2026-10-27.md), without
publishing private identities, account inventories, secrets or clinical records.
It does not establish full HIPAA compliance, certification or independent review.

## Applied and observed

- PR92 deployed through successful full CI and AWS deployment (40652318695). Operator
  TOTP policy, structural access logs and factual website safeguards are live.
- PR93 deployed through successful CI and AWS deployment (40653962344). Initial
  invitation/reset token URLs retain no-referrer; tokenless password forms use
  same-origin so HTTPS CSRF works when clients omit Origin. Missing CSRF tokens,
  missing origin/referrer and foreign referrers still fail. No protection exemption.
- New administrative access was activated by the operator, with password set privately,
  confirmed TOTP and recovery codes. After verifying login and operator confirmation,
  legacy privileged/test accounts were deactivated, privileges/groups removed and
  passwords invalidated. Historical rows/audit and clinical records remain intact.
  Account inventory, authorization and before/after evidence are private.
- External HTTPS availability workflow dispatched and passed (40653050281). Scheduled
  checks are on main; recipient notification delivery is a separate verification.
- CloudTrail log and digest delivery observed on 28/10. S3 access-log objects observed
  for both document and backup prefixes. This establishes delivery, not a cryptographic
  chain-validation run or a guarantee that every request is delivered.
- SES production access granted, identity Verified and DKIM Successful. The TLS-required
  configuration set is assigned as the identity default. Separate encrypted SNS/SQS
  feedback stack prepared, explicitly approved and CREATE_COMPLETE. Host permission
  only permits queue-attribute reads, never message reads/deletes; no email subscriber.
  SES notification wiring, tests and controlled SMTP cutover are tracked in the
  [runbook](../operations/transactional-email.md), not inferred from stack creation.

## Dependency review and candidate patch

`pip-audit` 2.10.1 reported known advisories for the pinned cryptography 46.0.3 and
Pillow 12.3.0. Counts include aliases/duplicates and are not a count of demonstrated
exploits in this app. Verified fixes/releases in the maintainers' primary sources:
[cryptography 50.0.2](https://cryptography.io/en/latest/changelog/),
[Pillow 13.0.0](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html).

The candidate pins cryptography 50.0.2 and Pillow 13.0.0, with no encryption-key
rotation, data rewrite or schema migration. In a fresh environment, 46 targeted
tests passed, including existing documents/image behavior and decryption of a
synthetic ciphertext generated with the old cryptography release. A modified legacy
token is still rejected. The resolved application environment (36 packages) then
reported no known advisories in the current feed. Full CI/deployment and subsequent
runtime evidence determine whether the candidate is actually active.

Bandit 1.9.4 reported ten medium warnings and no high warnings. Manual triage:
SQL construction is confined to fixed-table trigger tests; Google calls use fixed
HTTPS endpoints or the existing approved-API allowlist; operational probes use
explicit HTTPS/configured test endpoints. This is bounded source triage, not a
penetration test or a proof that all request/redirect paths are safe. No advisory
PoCs were executed. Raw scan reports remain private.

A separate weekly dependency workflow resolves app dependencies independently of
the audit tool and fails on known advisories. Review Actions failures and patch
outstanding dependencies; feed availability and zero-day limits remain.

## Remaining human/contractual closure

Verified automatic desktop lock and operator self-report do not technically prove
disk encryption. Independent key custody and loss-of-host/full-document recovery
remain unverified. The operator completed three security scenarios; a timed technical
incident drill and wider training remain. Provider flows, historical retention and
per-practice clinical/legal instructions still need explicit evaluation/acceptance.
AWS root/SSO administration is separate from application-admin enrollment.
