# Security Policy

Atlas ERP handles financial, inventory, and HR data; security reports are taken seriously.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Use GitHub's private vulnerability reporting: go to the repository's **Security** tab → **Report a vulnerability** ([direct link](https://github.com/Taha-Mahmoodi/atlas-erp/security/advisories/new)). Include affected component/endpoint, reproduction steps, and impact (especially anything touching tenant isolation, authentication/RBAC, or financial-data integrity).

You can expect an acknowledgment within 7 days. Confirmed vulnerabilities are fixed under a `severity:blocker` issue per the project workflow, and credited in the release notes unless you prefer otherwise.

## Scope notes

- Tenant-isolation bypasses, auth/RBAC bypasses, and anything allowing modification of posted financial records are always in scope and treated as blockers.
- The demo seed data is fictional; reports about demo credentials in documentation are out of scope.

## Supported versions

Pre-1.0: only the latest release on `main` receives fixes.
