# Security policy

## Reporting a vulnerability

If you find a vulnerability in Anchor, please **do not open a public
GitHub issue**. Instead, use one of these channels:

- **Preferred:** [GitHub private security advisory](https://github.com/Novia-RDI-Seafaring/anchor/security/advisories/new) — coordinated disclosure, encrypted, audit-trailed.
- **Email:** `security@novia.fi` (or the maintainer addresses listed in
  the `authors` field of [`pyproject.toml`](./pyproject.toml)) — encrypt
  with the maintainer's public key if posting anything sensitive.

We'll acknowledge within **3 business days** and aim to have a fix or
mitigation discussed within **14 days**. Critical vulnerabilities that
allow remote code execution, data exfiltration, or privilege escalation
get same-day attention.

## What's in scope

- The Python package `anchor-kb` published to PyPI
- The web frontend bundled in the wheel
- The HTTP / MCP / CLI adapter surface
- The PDF / FMU / CAD / SysML extensions in the same wheel

## What's out of scope

- The OIP specification — report at [Novia-RDI-Seafaring/OIP](https://github.com/Novia-RDI-Seafaring/OIP)
- Third-party FMU runtimes (FMPy, etc.) — report upstream
- Vulnerabilities in user-supplied content (PDFs, FMU files) that
  trigger known parser bugs upstream — report to the parser project
  (Docling, PyMuPDF, FMPy) and we'll bump our pin once they patch

## Security model

Anchor is **unauthenticated by design** and **loopback-only by default**:

- The HTTP server binds `127.0.0.1` unless you opt in to `0.0.0.0`
- CORS is restricted to the documented dev origins
- Workspace slugs and upload filenames go through identifier-policy
  validation at every public boundary
- Filesystem stores re-validate paths defensively (`assert_within`)

If you run Anchor on a network-reachable host, you are responsible for
adding authentication and TLS via a reverse proxy. Anchor itself does
not implement user accounts, auth tokens, or transport encryption.

## Supply chain

Defences against bad-dependency attacks (npm typosquats, PyPI account
compromises, etc.):

- **Lockfiles** (`uv.lock`, `web/pnpm-lock.yaml`) are authoritative
  and frozen-installed in CI.
- **Renovate cooldown** (`renovate.json`): runtime deps must be at
  least 7 days old, GitHub Actions 14 days, majors 30 days. Catches
  the 0-7-day window where a compromised version is live but not yet
  yanked.
- **Dependency Review** action blocks PRs that introduce known-vulnerable
  deps or deps under deny-listed licences.
- **CodeQL** scans our own code on every PR.
- **PyPI trusted publishing (OIDC)** — there is no long-lived PyPI
  token in the repo, in GitHub secrets, or on maintainer laptops. The
  publish-time OIDC token is scoped to the exact workflow file and
  expires in minutes. SLSA provenance attestation is generated
  automatically.
- **GitHub Environment protection** on the `pypi` environment requires
  a second-human approval and a wait timer before any publish job
  runs. See [`PUBLISHING.md`](./PUBLISHING.md) for the configuration.
- **Hardware 2FA** is required on every account with publish or admin
  privileges.

If you operate Anchor in a regulated environment that needs an SBOM,
the published wheel includes provenance metadata; a CycloneDX SBOM
can be generated locally with `uv run cyclonedx-py environment`.

## Disclosure

Public advisories are filed in the
[GitHub Security Advisories tab](https://github.com/Novia-RDI-Seafaring/anchor/security/advisories)
and mirrored to the PyPI advisory feed. We aim to disclose within 90
days of initial report or 7 days after a fix lands, whichever comes
first.
