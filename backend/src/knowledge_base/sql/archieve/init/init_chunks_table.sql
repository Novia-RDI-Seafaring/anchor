CREATE TABLE IF NOT EXISTS "%%SCHEMA%%".chunks (
    id SERIAL PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES "%%SCHEMA%%".documents(document_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(%%DIMENSION%%),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, chunk_index)
);
