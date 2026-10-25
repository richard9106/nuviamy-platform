# Temporary Google OAuth reviewer access

The reserved `google-oauth-review` user is a non-staff therapist in a separate fictional practice whose slug is `google-oauth-review-demo`. No existing practice membership, credentials, clinical records or Google tokens are copied. Seeded clients use reserved .invalid email addresses. No legal agreements are signed on anyone's behalf.

Email-code exemption requires all three operator-only settings: GOOGLE_REVIEW_USER_ID, GOOGLE_REVIEW_PRACTICE_ID, GOOGLE_REVIEW_ACCESS_EXPIRES_AT (timezone-aware ISO datetime). Default values disable access. Identity, tenant, therapist membership, role, active flag and expiry are checked on every request. Staff/superusers never qualify. Ordinary accounts still require email verification; MFA policy, CSRF, password authentication, rate limits, idle timeout, absolute timeout and audit logging remain intact. The reserved review identity is logged out and receives HTTP 403 when its configuration is invalid or expires, including existing sessions.

Provision a new empty practice and a unique random password, retain credentials outside the repository in an owner-readable file, and set a finite expiry. Configure calendar.events.owned only for this practice through GOOGLE_CALENDAR_OWNED_SCOPE_PRACTICE_IDS. Reviewers connect their own Google account; never provide a personal Google password or reuse the owner's NuviaMy login.

After review, deactivate the user, remove its operator settings and remove the practice ID from the Calendar demo allowlist. Any externally connected Google account must be disconnected/revoked through the normal flow. Retain or remove the fictional tenant according to operator instructions; removing config alone already blocks this reserved user. No authentication settings are disabled globally.

Validation: password login and integration access without an email challenge, ordinary user challenge, invalid/missing/expired configuration, privileged roles, tenant binding, existing-session expiry and other-practice client denial; existing email-code tests remain passing.
