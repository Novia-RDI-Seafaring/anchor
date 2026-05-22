# Security Policy

## Supported Use

Anchor is currently designed for trusted local or self-hosted use. Do not expose
the backend directly to the public internet without adding an application-level
auth boundary, HTTPS, and deployment-specific hardening.

## Local Secrets

- Store LLM provider credentials in `backend/.env`.
- Store frontend-only local settings in `.env.local`.
- Do not commit real keys, tokens, passwords, private documents, or generated
  data containing private content.

## Write Routes

Write-capable backend routes allow localhost requests by default so a local
developer can run the app with `npm run dev`.

For shared or public deployments:

- set `ANCHOR_WRITE_API_KEY` in `backend/.env`
- set `ALLOW_UNSAFE_LOCAL_WRITES=false`
- proxy the backend behind HTTPS and application auth
- send `X-Anchor-Write-Key` only from trusted server-side or controlled local
  clients

## Reporting Issues

Open a private security advisory or contact the maintainers before publishing
details of a vulnerability. Include reproduction steps, affected routes or
files, and any known impact.
