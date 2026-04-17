# Security Policy

## Supported versions

The project is pre-1.0. The `main` branch is the only supported line.
Security fixes ship as patch releases against the latest tagged
version. After 1.0, the latest minor plus the previous minor will
both receive backports.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security issues.

Email the maintainer at utsav.itsm@gmail.com with:

- a description of the vulnerability,
- steps to reproduce (ideally a minimal test case),
- the affected version / commit hash,
- any relevant logs or context,
- your preferred disclosure timeline and credit preference.

We will:

- acknowledge receipt within **48 hours**,
- confirm or contest within **7 days**,
- patch high-severity issues within **14 days**, medium-severity
  within **30 days**,
- publish a GitHub Security Advisory crediting you unless you
  prefer otherwise.

## Threat model

See [docs/security.md](./docs/security.md) for the current threat
model, scope, and what is explicitly deferred.

## Coordinated disclosure

If a vulnerability requires coordinated disclosure with other
projects or upstream vendors, we will coordinate privately before
publication.
