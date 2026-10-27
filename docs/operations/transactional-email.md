# SES transactional mail — controlled transition

27 October 2026. SES is HIPAA eligible under the existing AWS BAA, but this is not
automatic approval of every mail flow or the recipient's mailbox. Keep messages
minimal and keep clinical documents in the authenticated portal.

## Applied and verified

- Domain identity `nuviamy.com`, Easy DKIM RSA-2048. Three CNAME records published
  DNS-only in Cloudflare and independently resolved. Existing web A records and
  inbound MX remain unchanged; no new clinical proxy or analytics was enabled.
- Separate stack `nuviamy-transactional-email`, approved change set executed and
  CREATE_COMPLETE. Template: `ops/aws/transactional-email.json`. It adds only a
  TLS-required SES configuration set and SendEmail permission on the existing host
  role, restricted to the sender and current region. No access keys/SMTP passwords,
  new user, broad SES administration or EC2 replacement.
- Configuration `nuviamy-transactional`: delivery TLS REQUIRE, BOUNCE/COMPLAINT
  suppression, no engagement tracking or dedicated IP/VDM subscription activated.
- Operator explicitly approved service terms/AUP and submission of production access
  for transactional requested mail, with the corporate site and operator contact.
  AWS confirmed successful submission and in-progress review (up to 96 hours shown).
  This is not production-access approval.

## Cutover gates — do not skip

1. Confirm identity/DKIM status Verified/Successful and AWS production access approved
   in us-east-1. A resolvable CNAME alone is not an SES approval signal.
2. Review bounce/complaint handling, feedback forwarding and their actual destinations.
   Suppression is automatic, but avoid sending recipient data through an unapproved
   support mailbox. Assign dashboard review and escalation; test rejection behavior.
3. Check the existing host role is scoped as the reviewed template; no static key.
   Test delivery to the operator with approved minimal content and confirm receipt.
   SES API acceptance is not inbox delivery.
4. In the protected production env set:

   ```dotenv
   EMAIL_BACKEND=apps.accounts.ses_backend.EmailBackend
   AWS_SES_REGION=us-east-1
   AWS_SES_CONFIGURATION_SET=nuviamy-transactional
   DEFAULT_FROM_EMAIL=NuviaMy <noreply@nuviamy.com>
   ```

   Deploy/recreate the web container deliberately and verify login, email second
   step, invitations and password-reset delivery without sharing codes or tokens.
   The host monitor sends through the same app backend; verify it again after cutover.
5. Preserve the previous protected config for rollback. Do not silently fall back to
   Brevo for patient mail on SES failure; that bypasses the intended provider control.
   Avoid resending batches blindly after partial acceptance.

The prepared backend uses boto3 HTTPS and the instance role, requires the TLS
configuration set, enforces the configured sender, rejects attachments and redacts
provider errors. No patient notes, diagnoses or files should enter transactional mail.
These checks do not inspect arbitrary message bodies to certify absence of PHI.

Do not rerun the account foundation stack to add this policy: it may resolve a new
AMI and replace the host. Email and audit stacks are separate deliberately.

Sources: [AWS SES security protocols](https://docs.aws.amazon.com/ses/latest/dg/security-protocols.html),
[production access](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html).
