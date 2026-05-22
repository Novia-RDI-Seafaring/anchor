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
