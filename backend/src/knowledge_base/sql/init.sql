-- name: init_documents_table
CREATE TABLE IF NOT EXISTS "%%SCHEMA%%".documents (
    id SERIAL PRIMARY KEY,
    document_id TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT,
    source_type TEXT DEFAULT 'file',
    mime_type TEXT,
    file_size INTEGER,
    page_count INTEGER,
    chunk_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- name: init_schema
CREATE SCHEMA IF NOT EXISTS "%%SCHEMA%%";
SET search_path TO "%%SCHEMA%%", public, extensions;

-- name: init_vector_extension
CREATE EXTENSION IF NOT EXISTS vector;
