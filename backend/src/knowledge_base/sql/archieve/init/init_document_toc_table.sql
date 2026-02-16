CREATE TABLE IF NOT EXISTS "%%SCHEMA%%".document_toc (
    id SERIAL PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES "%%SCHEMA%%".documents(document_id) ON DELETE CASCADE,
    toc_json JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id)
);
