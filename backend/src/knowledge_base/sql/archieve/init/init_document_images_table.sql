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
