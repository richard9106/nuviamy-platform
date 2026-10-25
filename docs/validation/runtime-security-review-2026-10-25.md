# Production runtime security review — 25 October 2026

Read-only inventory and official advisory comparison. No packages, application code or services changed. This is not an incident investigation or a comprehensive vulnerability scan.

## Observed production inventory

Application container: Python 3.12.15, Django 5.2.17, Gunicorn 23.0.0, Debian 13, OpenSSL 3.5.7. Other observed packages: cryptography 46.0.3, urllib3 2.8.0, Pillow 12.3.0; these additional packages were inventoried, not fully assessed.
Host: Ubuntu 24.04.5 LTS, nginx 1.24.0-2ubuntu7.18 active. No installed PHP packages found. Gunicorn serves HTTP on container port 8000, published only to host loopback by Compose. Nginx listens on 80 and 443 ssl.

## Confirmed maintenance findings

- Django 5.2.18 was released on October 6 with security fixes. Installed 5.2.17 precedes these fixes. Issues include header-parsing denial of service and conditional formset/GeoDjango issues. No explicit GeoDjango, modelformset_factory, inlineformset_factory, accepts(), or direct affected helper use was found in the application source, but framework internals still require the patch.
- Python 3.12.16 was released October 25 as a security update. Installed application Python is 3.12.15. Rebuild from an updated base image after confirming availability; the floating python:3.12-slim tag alone does not prove the running image is current.
- Ubuntu nginx package .18 contains a backport for CVE-2026-42533. Do not infer all vulnerabilities from upstream version 1.24.0. Ubuntu still lists CVE-2026-15176, CVE-2026-93479 and CVE-2026-97629 as requiring evaluation on Noble at review time. No final all-clear for nginx is justified.
- Readable included Nginx configuration was inspected without exposing its contents: no alias, rewrite, request_filename, map, active AIO, SSI, slice, MP4 directive, HTTP/3 listener, shared SSL session cache or client certificate authentication was found. These observations reduce exposure to the corresponding configuration-dependent advisories but do not replace vendor patches. nginx -T through sudo was unavailable; configuration files were traversed read-only (five files, no read errors). Cached apt metadata offers the installed nginx revision; package indexes were not refreshed.

## Priorities

1. Upgrade Django to the patched supported 5.2 release, run regression tests and deploy.
2. Refresh the Python container base to include 3.12.16 security fixes and rebuild/test/deploy.
3. Reassess Ubuntu nginx patches and configuration against October advisories. Use vendor-supported updates or a reviewed mitigation, rather than blindly changing distribution packages.

## Official references

- https://www.djangoproject.com/weblog/2026/oct/06/security-releases/
- https://www.python.org/downloads/release/python-31216/
- https://ubuntu.com/security/CVE-2026-15176
- https://ubuntu.com/security/CVE-2026-93479
- https://ubuntu.com/security/CVE-2026-97629
- https://lists.ubuntu.com/archives/noble-changes/2026-September/058883.html
- https://nginx.org/en/security_advisories.html

## Remediation started with operator authorization

- Update Django pin from 5.2.17 to 5.2.18 on the supported LTS branch.
- CI and production builds now use --pull to resolve the official Python base image instead of relying on an old local image cache.
- Python 3.12.16-slim and 3.12.16-slim-trixie registry manifest checks both returned “no such manifest” on October 25. The source release exists, but no patched official container was available at these checks. Do not claim Python is patched merely because the base image is refreshed; inspect the runtime version after deployment. No custom interpreter build or unverified third-party image is substituted.
- Ubuntu October nginx advisories remain under evaluation; known prerequisite directives were absent from our readable configuration. No blanket immunity or complete remediation is claimed for Nginx.

Local validation: 36 account/email/Google integration tests passed on Django 5.2.18; pip check found no broken requirements; no migrations detected; shell syntax validation and four deployment-command unit tests passed. Full CI/deployment and post-deploy runtime verification are tracked separately.
