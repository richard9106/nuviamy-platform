# Branded error pages — 26 October 2026

Added templates/404.html and templates/500.html using Django's default error handlers (production DEBUG=False). Both inherit a standalone NuviaMy template with inline CSS/SVG, explicit noindex,follow, accessible recovery links, and responsive layout. There is no redirect to a successful homepage response and no canonical pointing error URLs to the homepage.

The 500 template uses no request context processors, session/user data, URL reversal, static manifest, external font, JavaScript or asset download. Error text does not echo request paths, query parameters or exception details. Recovery links use existing public routes. This covers Django-generated 404/500 responses; upstream proxy 502/503 responses remain outside this change.

Verification:

- `manage.py test apps.dashboard.test_error_pages apps.dashboard.test_marketing_seo --noinput`: 8 tests passed, including four new error tests. SimpleTestCase forbids database queries.
- Full request handling with DEBUG=False verifies a missing URL returns branded HTTP 404 and a deliberately failing test-only route returns branded HTTP 500 with exception details hidden. HEAD 404 has an empty body.
- Direct server-error rendering succeeds with a request context processor set to raise. Inline presentation is checked so static delivery failures do not remove the error layout.
- Actual local HTTP requests returned 404 and 500 respectively. The intentional failure route exists only in an isolated /tmp preview URLconf, not production code.
- Actual browser captures: desktop 1280px and mobile 390×844; document scrollWidth equals clientWidth (390px) on both mobile pages. Viewport restored and preview tab closed after capture.
- No production error was deliberately triggered. Not deployed at time of validation.

Captures: 404-desktop.jpg, 500-desktop.jpg, 404-mobile.jpg, 500-mobile.jpg.
