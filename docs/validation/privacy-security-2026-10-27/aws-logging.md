# AWS audit logging activation — 27 October 2026

The operator explicitly approved activation and usage charges in the project chat,
stating that AWS credits were available. No credit balance or expiry is asserted.

The approved CREATE change set added only an audit S3 bucket, its delivery policy
and a CloudTrail trail. CloudFormation reached CREATE_COMPLETE. CloudTrail was
observed Logging, multi-region, with integrity validation enabled, all management
events and the intended S3 data selectors. The first delivered log file was observed
on the activation date. The first digest was not yet delivered at that observation.

Both existing source buckets have server access logging Enabled with their separate
prefixes. The console-added broader destination-policy statement was removed; the
final saved five statements matched the approved scoped policy. The application
role was denied listing the audit bucket. Two small synthetic JSON markers were
successfully written and read back through the app's existing storage role, without
accessing patient records or deleting objects/versions.

The first delivery of both sources' S3 access logs remains a separate asynchronous
verification, not inferred from enabled settings or from CloudTrail delivery. No
digest-chain validation, incident exercise, alert delivery test or new application
deployment is claimed. Existing foundation stack drift is recorded in the runbook;
the desired template is updated but the deployed foundation stack was not updated.

The exact deployed audit template and the foundation's desired configuration passed
cfn-lint 1.57.2. Detailed screenshots, policy comparisons, resource identifiers and
synthetic request IDs remain in restricted operator storage outside Git.

See [the operational runbook](../../operations/aws-audit-logging.md) and
[remaining compliance evidence](../../compliance/closure-2026-10-27.md).
