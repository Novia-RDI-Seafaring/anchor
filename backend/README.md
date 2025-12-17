## Backend (FastAPI)

This folder contains the Python backend that powers ingestion, retrieval (pgvector), and the AG-UI agent endpoint.

### Duplicate-ingest protection (optional)

To avoid creating redundant rows when ingesting the same content repeatedly (e.g., running eval ingests), you can enable a best-effort skip:

- `SKIP_DUPLICATE_INGEST=1`

Behavior:
- File uploads: skips ingest if an existing document has `metadata.content_hash` matching the uploaded bytes.
- URL ingests: skips ingest if an existing URL document has `metadata.source_url` matching the URL.

If the existing document is not yet processed, the backend will process it and return the refreshed document record.
