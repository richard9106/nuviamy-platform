# Embedded video pilot — 2026-11-05

Status: implemented locally; disabled by default. Not deployed, not activated in AWS,
no real media call tested yet. Existing external appointment links are preserved.

## User flow

Create a video appointment with an assigned therapist and **no external meeting URL**.
The assigned therapist sees “Open video room”; its client sees the same entry in the
portal. Both must sign in. Administrators and other therapists cannot join simply
because they have administrative permissions.

The room offers a local camera/microphone preview or microphone-only participation.
Nothing is shared during preview or waiting. The therapist opens the room, the client
enters a waiting room, and the therapist admits that client. Only then are that client's
AWS credentials issued. Camera/microphone can be disabled; the therapist can end the
room for everyone. No recording, transcription, screen sharing, chat or group calls.

Joining is allowed from 15 minutes before the appointment until 15 minutes after its
end. A room lasts at most 120 minutes. The initial global capacity is five concurrent
rooms. These limits are operational safeguards, not a guaranteed billing budget.
An ended room cannot be restarted for the same appointment schedule. Rescheduling
creates a new generation. After a long disconnection, arrange another appointment or
use the practice's alternative contact method.

## Authorization and privacy

Explicit practice allowlist, active subscription/trial, current accepted standard
agreements or a signed clinical contract, scheduled video appointment, assigned
active therapist and active client portal access are all required.

Django creates meetings and attendees through the EC2 role; browsers receive only
their own attendee credentials over authenticated, CSRF-protected, non-cacheable POST.
No join token is stored in the database, browser storage, audit log or application
error messages. Meeting metadata and opaque participant identifiers are stored;
appointment names, clinical notes, emails and client names are not sent as Chime IDs.
The SDK is bundled locally; optional SDK event-ingestion telemetry is disabled.

Chime JoinToken has **no application-configured short TTL**. Revocation requires
DeleteAttendee/DeleteMeeting. New browser sessions rotate credentials and require
patient readmission. Appointment changes close the room after commit; bulk changes,
removed privileges, expired rooms and abandoned connections are caught by cleanup.
Browser heartbeat is every five seconds; it stops local media after two failed checks.
The worker closes abandoned participants after 90 seconds without a heartbeat.
Closing failures retain the meeting ID and are retried. A cleanup failure prevents
refreshing the safety heartbeat; joins fail closed after 150 seconds without success.
Revocation therefore has a bounded polling delay under normal operation and depends
on AWS/network availability. It is not instantaneous or guaranteed during an outage.

## Activation runbook — still pending

1. Review AWS BAA/service eligibility, control/media regions, practice contracts,
   privacy notice and international-transfer assessment for the pilot geography.
   This feature does not itself establish HIPAA/GDPR compliance.
2. Review `ops/aws/telehealth.json` for the existing host role and selected control
   region. Execute only the reviewed IAM change; do not attach the broad Chime SDK
   managed policy. Validate tagging/resource conditions in AWS before enabling.
   No capture/transcription/SIP/S3 permissions are included.
3. Deploy code and migrations with `TELEHEALTH_ENABLED=false`. Static assets include
   the pinned SDK bundle. Rebuild with `npm ci --ignore-scripts && npm run build`
   inside `frontend/telehealth` when changing SDK dependencies; retain license files.
4. Install `ops/systemd/nuviamy-video-cleanup.service` and `.timer` on the host,
   daemon-reload and enable the timer. Run cleanup once and check its successful
   timestamp. The timer runs 30 seconds after the preceding run finishes; the
   service times out after 55 seconds. Alternatively, install a managed per-minute
   cron entry as deploy, using flock and timeout 55, without overwriting other jobs.
   Install the matching operational_health.py after the app is deployed: it checks
   the non-identifying `video_health` flags every 15 minutes and uses the existing
   deduplicated operator alerts. New joins fail closed sooner (150 seconds) if the
   worker stops. Do not install both cron and timer or overwrite notification cron.
5. Enable only an isolated fictional practice with `TELEHEALTH_PRACTICE_IDS`, global
   flag true, and reviewed region variables from `.env.example`. Recreate web to
   apply settings. Run Django checks. Verify host-role IAM by opening a synthetic
   room, then test two real browsers/devices: waiting admission, mute/camera,
   browser permission denial, Safari/iOS, reconnect, duplicate tabs, cancellation,
   expiry, worker outage and final deletion. No clinical records in the test.
6. Confirm no attendee tokens appear in logs or persisted data, AWS rooms are
   deleted, timer is running, usage/cost alerts work and the call's region is correct.
   Then approve pilot practices individually. A broader rollout is a separate step.

Rollback: turn the feature off, keep the cleanup timer running and run cleanup until
all native rooms are ended and their external IDs cleared. Verify failed deletions
in AWS before removing the IAM policy or worker. Existing external links still work.

## Verification

Synthetic Django tests cover tenant/role isolation, admission, token rotation,
CSRF, scheduling/contract/subscription gates, stale worker, cleanup failures and
botocore API shapes. PostgreSQL tests race two requests on the same appointment
and two separate appointments against capacity one. Browser-controller tests use
fake devices/SDK; they are not a substitute for the pending two-device live test.

Official references:
- https://docs.aws.amazon.com/chime-sdk/latest/APIReference/API_meeting-chime_CreateMeeting.html
- https://docs.aws.amazon.com/chime-sdk/latest/APIReference/API_meeting-chime_CreateAttendee.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_chime.html
- https://aws.github.io/amazon-chime-sdk-js/

Local validation completed on 2026-11-05: 815 Django tests passed on an isolated
PostgreSQL 16 instance; the dedicated module has 35 tests, including two real
row-lock races. The JavaScript synthetic-device checks, production Django checks,
migration consistency, CloudFormation lint and deployment-image asset smoke test
passed. Desktop and 390px mobile prejoin views were checked in the browser; mobile
has no horizontal overflow. No camera/microphone permission or live AWS media test
was performed. The test database was separate from development and production.
