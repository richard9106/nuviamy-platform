# AWS audit logging

## Deployed configuration

On 27 October 2026 the operator authorized the proposed AWS audit logging resources
and usage charges. The `nuviamy-audit-logging` stack completed successfully through
the reviewed console change set. Source: `ops/aws/audit-logging.json`.

- A dedicated private, SSE-S3 encrypted, versioned log bucket, retained on stack
  deletion/replacement. No automatic object/version expiry is configured.
- A multi-region CloudTrail trail with global services and all read/write management
  events, log file integrity validation, and object data events for the specified
  documents and backups buckets.
- Audit-bucket object operations are recorded except `PutObject` to avoid recursively
  logging log deliveries. This exception also excludes other object puts there;
  versioning and digest validation are not WORM or protection against every operator.
- Delivery permissions are limited to the CloudTrail trail ARN and the two S3 source
  bucket ARNs, account and destination prefixes. There is no new runtime app role
  access to the audit bucket.
- Server access logging on documents and backups delivers to `s3-access/documents/`
  and `s3-access/backups/` in that bucket, using the simple object-key format.

Insights, Lake, a customer-managed KMS key, CloudWatch Logs and new alarms were not
enabled. The operator's statement that AWS supplied credits is not independent
verification of the credit balance, coverage or expiry. Charges remain usage-based.

## Provisioning order and existing-stack boundary

For a new environment, create the audit stack first with the intended documents and
backup bucket names. Then create the foundation with `AuditLogBucketName` set to
the audit stack's output. Selectors and source-ARN conditions do not grant the app
new permissions. Validate templates before creating and reviewing change sets.

The current source-bucket logging settings were enabled through S3's console. The
existing deployed foundation template predates them, so this is **recorded stack
drift until reconciled**. `foundation.json` now expresses the desired logging and
requires the destination parameter; there is no empty default that silently removes
logging. Do not blindly update the whole foundation stack just to reconcile it:
its SSM AMI parameter can resolve to a newer image and propose replacing the host.
Review an infrastructure change set with the deployed parameter/AMI values and
reject any unintended instance, disk, network or IAM changes. No such update was
performed during logging activation.

## Console policy side effect

Enabling server access logging in the S3 console can append a broader delivery
statement to the destination policy. During this activation the console added a
service write grant across the audit bucket without the source-bucket ARN condition.
It was removed after both sources were configured. The saved final five statements
were compared with the approved policy. Recheck this on later S3 console edits;
retain the narrow source/account/prefix grants rather than accumulating duplicates.

## Verification and ongoing review

1. Check CloudFormation `CREATE_COMPLETE`, CloudTrail `Logging`, multi-region/global
   configuration, integrity validation, selectors, latest delivery and delivery errors.
2. Check both `GetBucketLogging` targets/prefixes and the audit bucket's public blocks,
   encryption, versioning and policy. Do not enable server access logging on the log
   destination itself; AWS warns of a logging loop.
3. Use clearly labeled synthetic objects, not patient records. Initial probes wrote
   and read back small JSON markers in documents and in the backup role's allowed
   `postgres/_security-verification/` prefix. They do not represent database backups.
   No existing objects or object versions were deleted. Retain their references in
   the private operator evidence directory.
4. The application role was denied listing the audit bucket, as intended. Do not
   widen it for debugging. Access audit evidence with the authorized operator role.
5. CloudTrail's first delivered log file was observed on activation. S3 server access
   logs are asynchronous/best effort; enabled settings alone do not prove that every
   source request has arrived. Confirm delivery separately. The first integrity
   digest is not promised immediately; perform log validation after one is available.
6. Review usage, delivery, integrity, access and retention with the responsible
   operator; preserve incident evidence. No automatic expiry or hard spending cap
   was introduced. Backups, clinical retention, training, device security, alerting
   and incident exercises retain their separate evidence requirements.

Keep raw logs, full resource identifiers, request IDs and configuration screenshots
outside this public repository. They can contain sensitive identifiers even when
no clinical record bodies are included. This logging deployment is not HIPAA approval.

## Cost references

The first management-event copy delivered to S3 has no CloudTrail event charge;
data events are billed by volume, with S3 storage/request/access charges separately.
Check current prices and actual credit applicability rather than assuming all
charges are covered or that a budget notification stops spending.

- https://aws.amazon.com/cloudtrail/pricing/
- https://aws.amazon.com/s3/pricing/
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/enable-server-access-logging.html
- https://docs.aws.amazon.com/awscloudtrail/latest/userguide/create-s3-bucket-policy-for-cloudtrail.html
