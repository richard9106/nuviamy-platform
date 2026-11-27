# NuviaMy visual identity

The selected identity combines the rounded typography of concept 3 with the
open-door symbol and greens of concept 1, supported by soft pink backgrounds. The door is a native vector drawing,
not the generated raster concept. It represents welcome and a clearer beginning.
Light pink and the sage/forest greens from concept 1 provide supporting accents.

| Role | Color |
| --- | --- |
| Primary action / symbol | Evergreen `#245548` |
| Hover / strong accent | Forest `#183E35` |
| Soft accent / threshold | Light pink `#F7E5E5` |
| Soft panels | Light pink `#F7E5E5` / blush `#FBEFF0` |
| Navigation / supporting text | Forest `#183E35` |
| Supporting borders / panels | Sage `#B7C9B0` / pale sage `#EDF2E9` |
| Background | Pink-tinted white `#FFFAFB` |
| Primary text | Espresso `#392D29` |

`static/branding/brand.css` owns the shared palette and self-hosted variable
Manrope font. Its SIL Open Font License is stored alongside the font. The public
website, staff workspace, account screens and portal import it through
`dashboard.css`; the isolated video room and Django administration import only
the branding they need. No third-party font request is required.

`templates/partials/brand_symbol.html` is the inline symbol shared by navigation,
authentication, portal attribution and error pages. `static/branding/door.svg`
is its standalone version; `static/favicon.svg` places it on a cream tile. Keep
the icon's doorway open and its pink threshold visible. The adjacent text supplies
the accessible brand name; decorative symbols are hidden from assistive technology.
Patient portal headers continue to identify the treating practice prominently.

Email templates use inline palette values and a text wordmark for broad client
compatibility, with no remote logo/tracking image. The sign-in code, label and
expiry guidance are centered using both `align` and inline `text-align`.
Error pages retain inline CSS and do not depend on static storage to render.
Printable invoices and generated practice summaries use the evergreen accent.

Success, warning, danger and information colors retain their status meanings.
Calendar past/near/future timing colors remain green/orange/blue. Do not reuse
status tokens for decorative branding or rely on color alone to communicate state.
Use the separate sage/forest brand tokens for selected navigation and supporting
panels, pink for soft backgrounds, and evergreen for primary actions.
White on evergreen has 8.51:1 contrast; forest on pale sage has 10.39:1.
These measurements cover the specified pairs, not every screen.

Public product screenshots and the short clinical-notes preview use the current
interface with fictional records. Terracotta media filenames keep these assets
distinct from earlier screenshots. The social preview remains 1200×630 pixels.
Concept boards and local validation evidence belong under `output/`, not in
production templates. The appearance preference adds one per-user field via
`accounts.0012_workspace_theme`; no clinical, permission, subscription or
authentication behavior is changed.

## Validation

- 295 dashboard, portal and account/email security tests passed against isolated
  PostgreSQL 16 with Python 3.12.
- Existing JavaScript checks passed for drawer return context, calendar dragging,
  password controls and telehealth media/security lifecycle.
- Static collection and the asset/login smoke check passed, including the shared
  palette, SVGs, self-hosted font, admin stylesheet and social preview.
- Migration consistency reports no changes.
- Local browser previews used fictional data. Home, login, signup, portal and inbox
  were checked at 390px without horizontal document overflow; desktop review also
  covered the dashboard, notes, account email and video-room presentation.
- The pink/sage refinement was visually reviewed on home, dashboard and portal;
  its additional text/background pairs were checked for contrast.
- The code verification email was rendered locally; no external test email was sent.

This validation is not production deployment. Release through the ordinary GitHub
Actions workflow.

## Personal appearance

Profile settings → Make it your workspace offers Pink & Sage (default), Rose &
Cream, and Coastal Blue. A CSRF-protected staff-only POST saves the choice on the
current user's profile. It persists across sessions and devices without changing
another user's preference or the public marketing identity. Expired subscriptions
can still change this personal preference. The selected palette is applied by
server-rendered body attributes so it does not flash the default theme on load.

A native SVG branch is masked in the palette's strong accent at 5.5% opacity along
the right edge. It has no content or pointer interaction, and is hidden on small
screens and in print. Semantic appointment and alert colors retain their meaning.

13 appearance/profile tests passed on isolated SQLite, including persistence,
user isolation, validation, login, CSRF, client-role rejection, and expired trials.
Production migration and deployment remain part of the normal release workflow.
