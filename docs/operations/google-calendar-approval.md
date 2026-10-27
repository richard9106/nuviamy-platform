# Approved Google Calendar production rollout

Google's 27 October 2026 notice approves project nuviamy (1086176988025) for calendar.events.owned. New connections request exactly openid, https://www.googleapis.com/auth/userinfo.email, and https://www.googleapis.com/auth/calendar.events.owned. The old per-practice demo allowlist is removed. Gmail and Drive capabilities remain unavailable pending a separate review. No Google Cloud consent-screen configuration changes are needed for this rollout.

The connection form and authorization builder allow only the approved Calendar capability. Consent requests do not merge previously granted scopes. The callback rejects obsolete pending scope selections before token exchange and rejects grants containing extra permissions before fetching user data or persisting credentials. API requests are restricted to the primary Calendar events endpoint. Gmail sending and Drive export endpoints are disabled, while document ownership checks remain enforced. Existing external files/events are not deleted.

After deploying the reviewed revision:

1. Run `python manage.py finalize_google_verification` to preview cleanup.
2. Run the same command with `--apply`. It disables the precisely bound fictional reviewer identity, removes obsolete Google capability flags and credentials, preserves approved connected Calendar grants/tokens, and marks connected legacy integrations as needing reauthorization. Dropbox is unchanged. Changes are atomic and audited; a misbound reviewer aborts cleanup. Repeating the command makes no further changes.
3. Remove GOOGLE_CALENDAR_OWNED_SCOPE_PRACTICE_IDS and GOOGLE_REVIEW_USER_ID / GOOGLE_REVIEW_PRACTICE_ID / GOOGLE_REVIEW_ACCESS_EXPIRES_AT from the production operator environment; recreate the web container to reload configuration. Keep normal email verification and MFA policies.
4. Verify exact scopes for an ordinary practice, approved connection preservation, inactive review account and absence of review bypass settings. Existing sessions cannot authenticate the deactivated user through Django's ModelBackend.
5. Test the current approved Calendar connection with generic synthetic events, no attendees/default reminders and sendUpdates=none. Remove only the synthetic event created by this test. Never use client names/notes or copy access/refresh tokens into logs or verification documents.

This cleanup does not revoke the Google-side grant for old authorizations, remove historical clinical/audit records, or erase Google-hosted files/events. Users can remove obsolete grants through their Google Account connections page. If access or refresh credentials are invalid, the affected owner must reconnect through the normal OAuth flow; no personal password or authentication code should be collected by an operator.
