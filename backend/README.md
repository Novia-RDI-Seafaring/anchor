## Backend (FastAPI)

This folder contains the Python backend for document ingestion, file-backed
storage, medallion artifacts, FMU routes, and the AG-UI agent endpoint.

### Duplicate-ingest protection (optional)

To avoid redundant rows when ingesting the same content repeatedly, enable:

- `SKIP_DUPLICATE_INGEST=1`

Behavior:
- File uploads: skips ingest if an existing document has `metadata.content_hash` matching the uploaded bytes.
- URL ingests: skips ingest if an existing URL document has `metadata.source_url` matching the URL.

If the existing document is not processed yet, the backend processes it and
returns the refreshed document record.

### Write-route guard

Write-capable routes require either a trusted loopback request or
`X-Anchor-Write-Key`.

Local development defaults:

- `ALLOW_UNSAFE_LOCAL_WRITES=true`
- `ANCHOR_WRITE_API_KEY=` unset

For shared machines or public deployments:

- set `ANCHOR_WRITE_API_KEY` to a generated secret
- set `ALLOW_UNSAFE_LOCAL_WRITES=false`
- keep the backend behind HTTPS and an application-level auth boundary
