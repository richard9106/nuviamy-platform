# Therapist email alerts and SMS assessment — 2026-10-30

## Implemented email behavior

Profile settings → Email alerts has two independent, initially unchecked preferences:

- **Session updates**: new sessions and persisted changes to time, end time, status, assigned therapist or session type. Notes/calendar sync/reminder metadata saves do not generate alerts.
- **Client change requests**: cancellation/reschedule requests linked to a session. A request does not cancel or reschedule a session; the practice still reviews it.

Only the currently assigned therapist with an active internal account, matching practice membership and appointments read permission receives an alert. Request alerts also require requests read permission. Practice owners/admins receive alerts only for sessions assigned to them, not every session in the practice. No client-facing messages or general-message alerts are added in this change. Preferences are personal and remain editable after subscription expiry. No Gmail connection is needed: the configured transactional backend (SES in production) handles delivery.

The subject and HTML/plaintext body contain a fixed event description and authenticated application links, without client names, session times, subject/message text, notes or meeting links. There are no login tokens, tracking pixels or attachments. Email addresses are read from the current account at delivery and are not copied into the outbox.

A minimal `SessionEmailNotification` outbox is written with the event. Delivery starts only after transaction commit. Pending delivery rechecks active account, permissions, membership, assignment and opt-in; resolved requests and alerts older than 24 hours are skipped. Up to five provider attempts with exponential backoff. PostgreSQL row locks serialize workers, and each event/recipient key is unique. A provider acceptance is recorded as `sent`; this does not prove inbox delivery. A crash after provider acceptance and before database commit can cause a retry duplicate: SES/SMTP does not provide an exactly-once guarantee here. Do not use these emails as an emergency channel.

## Deployment/runbook

Deployment does not enable user preferences or send live test messages. No SMS provider is activated.

1. Deploy through the normal reviewed CI workflow; apply the additive accounts/appointments migrations.
2. Production may run the command from the deploy user’s crontab every minute, protected by a private `flock` lock and a 90-second execution timeout. This uses the existing runtime container and application database role. Preserve all unrelated cron entries, activate only after the new revision is live, and verify the cron service is running. Alternatively install the included `ops/systemd/nuviamy-session-notifications.{service,timer}` with the other host units and enable/start the timer. Neither scheduler is automatically installed by `ops/deploy.sh`; use one, not both.
3. Immediate delivery works on commit; retries/backlog recovery require the timer (or another scheduler running `python manage.py send_session_notifications` every minute). The command processes at most 100 due records per run. Failed delivery does not roll back the client request/session change.
4. Optional trusted link origin: `NOTIFICATION_SITE_URL`, default `https://nuviamy.com`. Keep HTTPS and the canonical host in production. No user-supplied Host headers are used.
5. Monitor outbox state counts/oldest pending age privately without printing identifiers, addresses or content. Provider feedback remains in the existing private SES feedback circuit. Clear an exhausted alert only after investigating; do not indiscriminately replay old clinical workflow events.
6. On restored backups, leave the retry scheduler stopped until pending outbox records are reviewed/skipped; an old backup can contain already-delivered pending events.

Opt-ins default off for both existing and new accounts. No paid SMS resource, number purchase, provider account or sending permission is created.

## SMS research (official sources, checked 2026-10-30)

SMS is a separate paid channel. A phone number in an account is not consent to receive text alerts. Initially prefer staff operational alerts with the same minimal content: “NuviaMy: a session update needs your attention. Sign in at https://nuviamy.com/.” Patient reminders require a separately designed consent/notification flow.

| Provider | Indicative outbound SMS price | Additional considerations |
| --- | --- | --- |
| AWS End User Messaging SMS | Official CSV: US 10DLC $0.00774 base + $0.00421 carrier fee = $0.01195/segment; Spain $0.07/segment | Current published US toll-free number $2/month. 10DLC number $1/month + campaign $2/month low volume or $10 regular; company registration $4.50, optional/required vetting depending route. Registration/verification applies to sender type. |
| Twilio Programmable Messaging | US $0.0083/segment base, plus carrier fees; Spain $0.0875/segment | Number rental, applicable registration fees and contracts are additional. Check the chosen route rather than treating the base rate as an all-in cost. |

Illustration: 1,000 one-segment outbound messages at the AWS CSV US 10DLC rates are $11.95 in base/carrier usage, or $70 for Spain, excluding sender rental, registration/campaign fees, taxes, optional protection and any other applicable charges. Multi-segment messages cost more. No assumption is made about Activate credit eligibility for any of these items.

AWS is the first candidate to evaluate because the infrastructure and vendor relationship already exist, not because SMS is free or automatically approved. The current HIPAA-eligible service reference lists Amazon Pinpoint and End User Messaging with stated exclusions; this is not a substitute for confirming the account BAA/service scope, message flow, telecommunications limitations and the EU transfer assessment. Twilio describes SMS healthcare support under its eligible services and executed BAA; its HIPAA architecture document limits eligible SMS traffic to/from US area codes. Do not send patient details over an unreviewed SMS route.

Before implementation/activation:

- Confirm recipient countries, staff versus patient use, volume and maximum monthly spend.
- Verify numbers in E.164 and capture explicit, separate opt-in with timestamp/text version, plus revocation and STOP/HELP handling where supported/required by the route.
- Register/verify the chosen sender (US 10DLC or verified toll-free; supported Spain sender identity), leave sandbox only after approvals, restrict destination countries and IAM sends, and set spend/volume limits.
- Handle delivery events, suppression/opt-out, idempotency, rate limits and bounded retries without exposing message content in logs. Define quiet hours/time zones and no automatic paid SMS fallback from email.
- Add provider-specific processing/contract/transfer review before clinical usage. Display pricing/conditions and obtain the owner's approval before provisioning anything paid.

### Sources

- [AWS pricing and sender/campaign fees](https://aws.amazon.com/end-user-messaging/pricing/)
- [AWS official outbound SMS CSV](https://d1.awsstatic.com/onedam/marketing-channels/website/aws/en_US/business-applications/approved/documents/End-User-Messaging-SMS-Prices.ebc340b4d416d90832dd59629c4792b0deb6f8bc.csv)
- [AWS US 10DLC registration](https://docs.aws.amazon.com/sms-voice/latest/userguide/registrations-10dlc.html)
- [AWS opt-in and messaging best practices](https://docs.aws.amazon.com/sms-voice/latest/userguide/best-practices.html)
- [AWS HIPAA eligible services reference](https://aws.amazon.com/compliance/hipaa-eligible-services-reference/)
- [Twilio US prices](https://www.twilio.com/en-us/sms/pricing/us)
- [Twilio Spain prices](https://www.twilio.com/en-us/sms/pricing/es)
- [Twilio SMS healthcare guidance](https://help.twilio.com/articles/360059959413)
- [Twilio HIPAA architecture](https://www.twilio.com/content/dam/twilio-com/global/en/other/hipaa/pdf/Architecting-for-HIPAA.pdf)
