-- name: init_chunks_index
CREATE INDEX IF NOT EXISTS chunks_embedding_idx 
ON "%%SCHEMA%%".chunks USING hnsw (embedding vector_cosine_ops);

-- name: init_chunks_table
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

-- name: init_document_images_index
CREATE INDEX IF NOT EXISTS document_images_doc_id_idx 
ON "%%SCHEMA%%".document_images(document_id);

-- name: init_document_images_table
CREATE TABLE IF NOT EXISTS "%%SCHEMA%%".document_images (
    id SERIAL PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES "%%SCHEMA%%".documents(document_id) ON DELETE CASCADE,
    image_type TEXT DEFAULT 'figure',
    page_number INTEGER,
    image_base64 TEXT NOT NULL,
    caption TEXT,
    alt_text TEXT,
    bbox JSONB,
    width INTEGER,
    height INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- name: init_document_toc_table
CREATE TABLE IF NOT EXISTS "%%SCHEMA%%".document_toc (
    id SERIAL PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES "%%SCHEMA%%".documents(document_id) ON DELETE CASCADE,
    toc_json JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id)
);

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

-- name: init_page_images_table
CREATE TABLE IF NOT EXISTS "%%SCHEMA%%".page_images (
    id SERIAL PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES "%%SCHEMA%%".documents(document_id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    image_base64 TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, page_number)
);

-- name: init_schema
CREATE SCHEMA IF NOT EXISTS "%%SCHEMA%%";
SET search_path TO "%%SCHEMA%%", public, extensions;

-- name: init_vector_extension
CREATE EXTENSION IF NOT EXISTS vector;

