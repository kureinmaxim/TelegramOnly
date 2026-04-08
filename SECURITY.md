# Security Policy

## Scope

This repository is a public server-side project that includes:

- a Telegram bot control plane
- a FastAPI-based application API
- transport management helpers
- export flows for client interoperability

Because the project handles networking, credentials, and deployment automation, security
issues should be treated seriously even if they look operational rather than purely code-related.

## Supported Versions

Security fixes are expected only for the latest public state of the `main` branch.

Older commits, forks, or private customized deployments may not receive coordinated fixes.

## Reporting a Vulnerability

Please do not open a public GitHub issue for vulnerabilities involving:

- leaked secrets or credentials
- remote code execution
- authentication bypass
- broken access control
- secret exposure in exports, logs, or admin flows
- unsafe deployment defaults

Instead, report privately to the repository maintainer first and include:

- a short description of the issue
- affected files or flows
- reproduction steps
- impact assessment
- suggested fix if you have one

If a private security contact channel is later added to the repository profile, prefer that
channel over public discussion.

## What Counts As Sensitive

The following data must be treated as secrets or server-only material:

- `.env` contents
- `BOT_TOKEN`
- `API_SECRET_KEY`
- `ENCRYPTION_KEY`
- `HMAC_SECRET`
- `app_keys.json`
- transport private keys
- client passwords that should not be exposed broadly

These values should never be committed to the repository and should not be posted in public issues.

## Secure-By-Default Expectations

This repository aims to keep public defaults conservative:

- full secret reveal should be opt-in, not default
- server-only secrets should stay out of client-facing exports
- deployment scripts should avoid printing long-lived secrets into shell output
- public docs should not contain real personal infrastructure data

## Operator Hardening Recommendations

For real deployments, operators should additionally:

- keep `.env` and JSON config files readable only by the service owner
- rotate secrets after accidental exposure
- avoid sharing Telegram admin access broadly
- review exported client artifacts before sending them to users
- keep VPS packages and transport binaries updated
- prefer separate environments for testing and production

## Out Of Scope

The following are generally out of scope unless they demonstrate a real security impact:

- missing rate limits on non-sensitive local-only utilities
- cosmetic information disclosure without operational value
- issues that require full server shell access first
- vulnerabilities only present in heavily modified private forks

## Disclosure Process

After a valid report:

1. The issue should be reproduced and scoped.
2. A fix or mitigation should be prepared.
3. Sensitive details should remain private until users have a reasonable chance to update.

## Notes For Contributors

When contributing to this repository:

- never commit secrets
- treat credentials and runtime config files as sensitive
- avoid adding features that expose full secrets by default
- prefer masking, opt-in reveal, and least-privilege behavior
