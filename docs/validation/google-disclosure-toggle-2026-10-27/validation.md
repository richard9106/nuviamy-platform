# Google disclosure accordion — 27 October 2026

The connection disclosure now has a short always-visible data-use summary and native details/summary for the full text. The Calendar authorization checkbox starts unchecked inside a disabled fieldset. Opening the disclosure enables the checkbox without selecting it. The Connect Google button requires both that opening and a checked box; configured OAuth credentials are still required. Closing the disclosure after review keeps the current-page authorization selection available. Reloading starts a fresh review. Existing connected-account status and credentials are not changed by viewing this form.

This is a browser interaction requirement, not proof that a person read the text or a new legal agreement. Approved OAuth scopes, server-side permission validation and callback behavior remain unchanged. Without JavaScript, the connection stays disabled with an explanatory message. No browser storage is used for review state.

Verification:
- Three existing integration/disclosure/OAuth-request tests passed. Static manifest collection and git diff checks passed.
- Actual browser with a fictional local owner: checkbox and Connect disabled initially; opening details enables only the checkbox; checking it enables Connect; unchecking disables Connect; reopening/closing works; reload disables both again.
- Enter on the native summary opens it using the keyboard; the checkbox becomes enabled and remains unchecked.
- Screenshots: collapsed.jpg and opened.jpg. No external OAuth request was submitted and no production account was changed.
