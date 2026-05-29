# Security policy

## Reporting a vulnerability

If you find a vulnerability in ANCHOR, please do not put exploit details
in a public issue, discussion, or pull request.

Use the repository's
[GitHub private security advisory form](https://github.com/Novia-RDI-Seafaring/anchor/security/advisories/new)
so maintainers can discuss the report privately.

This repository does not publish a separate security email address. If
the private advisory form is unavailable, open a public issue that only
asks for a private reporting channel. Do not include vulnerability
details in that issue.

## What's in scope

- The Python package `anchor-kb` published to PyPI
- The web frontend bundled in the wheel
- The HTTP / MCP / CLI adapter surface
- The PDF / FMU / CAD / SysML extensions in the same wheel

## What's out of scope

- The OIP specification - report at [Novia-RDI-Seafaring/OIP](https://github.com/Novia-RDI-Seafaring/OIP)
- Third-party FMU runtimes (FMPy, etc.) - report upstream
- Vulnerabilities in user-supplied content (PDFs, FMU files) that
  trigger known parser bugs upstream - report to the parser project
  (Docling, PyMuPDF, FMPy). ANCHOR can update dependency pins after
  upstream fixes are available.

## Security model

ANCHOR is **unauthenticated by design** and **loopback-only by default**:

- The HTTP server binds `127.0.0.1` unless you opt in to `0.0.0.0`
- CORS is restricted to the documented dev origins
- Workspace slugs and upload filenames go through identifier-policy
  validation at every public boundary
- Filesystem stores re-validate paths defensively (`assert_within`)

If you run ANCHOR on a network-reachable host, you are responsible for
adding authentication and TLS via a reverse proxy. ANCHOR itself does
not implement user accounts, auth tokens, or transport encryption.

## Supply chain

Repository-level supply-chain controls:

- **Lockfiles** (`uv.lock`, `web/pnpm-lock.yaml`) are authoritative
  and frozen-installed in CI.
- **Renovate cooldown** (`renovate.json`) delays new dependency versions
  before opening update PRs.
- **Dependency Review** checks dependency changes in pull requests.
- **CodeQL** scans Python and TypeScript code.
- **PyPI trusted publishing** is configured through GitHub Actions. See
  [`PUBLISHING.md`](./PUBLISHING.md) for the release process.

## Disclosure

Maintainers coordinate disclosure through GitHub Security Advisories.
Public disclosure timing depends on impact, fix availability, and any
upstream projects involved.
