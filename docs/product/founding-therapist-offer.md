# Personal founding therapist offer

Implementation prepared 2026-10-30; not deployed and no production codes issued as part of preparation. This is a separate campaign from the legacy ten-slot, twelve-month invitation mechanism, which remains unchanged.

## Offer and redemption

- At most fifty places, enforced by preallocated unique slots and a database check constraint. One code per email (case-insensitive unique constraint).
- Six calendar months from successful signup/redemption, clipping dates such as August 31 to February 28/29. This replaces the ordinary 30-day trial; it does not add six months to it.
- One active internal user, no card required, no Stripe coupon/subscription creation or automatic charge. At expiry, existing subscription access logic provides read-only/export access under normal permissions unless a paid subscription is chosen.
- Codes expire after thirty days if unused, are single use, bound to the invited owner email, generated from 96 random bits, and stored only as hashes. Codes tolerate case, hyphens and whitespace when manually entered.
- `/accounts/signup/` has an optional personal code field; a `?offer=...` invitation link prefills it. The advertised free period is based on a validated invitation, not merely the presence of a query parameter.
- Existing ordinary-trial owners can redeem in Profile settings, including an expired ordinary trial. Unrestricted complimentary workspaces, existing subscriptions (including canceled/incomplete ones), teams with more than one internal user and legacy invited access are excluded; billing/previous promises are never overwritten. Other roles cannot redeem. POST/CSRF/authentication and a bounded attempt limit apply.
- Invitation locking and practice/profile locking prevent double redemption. Failed account creation rolls back code consumption. Codes are not used at login itself: sign up with the code, or sign in and use Profile settings.

## Operator issuance (after deployment)

Run privately on the normal runtime using `python manage.py issue_founding_therapist_invitation owner@example.com`. Output is private JSON containing the code, signup link, claim deadline and allocated slot. It sends no email. Protect output as an invitation credential; never commit it or put it in public issue/CI logs. Repeated issuance for the same email fails; `--rotate` explicitly replaces an unused code for that same email and invalidates its predecessor. Redeemed slots cannot be reused. Allocated places are not automatically recycled, even if the claim deadline passes.

Issue only after a recipient has asked to join and confirmed the owner-account email. No campaign-wide public coupon exists; a forwarded code does not work with a different email. This is complimentary product access, not a Stripe checkout discount.

## Outreach preparation

The prospect list and personalized English drafts are kept privately outside the public repository. Public contact information is not evidence of consent to commercial outreach. No form submissions, mailbox verification probes, external sends or production code allocation were performed.

Before any campaign, verify the applicable outreach basis and provider rules. The operator is based in Spain, so do not assume US CAN-SPAM is the only relevant regime. Include a truthful subject/from identity, valid postal address and working opt-out; maintain suppression and honor opt-outs. Do not turn the production SES transactional sender into a scraped-address marketing campaign. Do not claim external certification, insurer enrollment, ERA automation or endorsements. Feedback is honest and voluntary, not a required positive review.

Sources:
- https://www.boe.es/buscar/act.php?id=BOE-A-2002-13758#a21
- https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- https://docs.aws.amazon.com/ses/latest/dg/faqs-enforcement.html

## Public applications — prepared 2026-11-01

Public website banner links to `/founding-therapists/`. Visitors may dismiss the banner on the current page, without additional browser storage; a footer link remains. The form collects professional name/email, optional practice name, country, role and explicit application-contact permission. Requests are encrypted SupportTickets with the founding therapist topic, visible to authorized platform support/admin; the existing generic operator notification contains no submitted details. Requests do not allocate slots, issue codes or subscribe applicants to marketing. Applications are reviewed in received order, up to fifty approved places. CSRF, shared contact rate limiting and a honeypot apply. Additive migration expands the old twenty places to fifty without replacing existing issued/redeemed invitations. Reverse migration must not be used after new places are allocated; use a reviewed forward fix. Still pending deployment.
