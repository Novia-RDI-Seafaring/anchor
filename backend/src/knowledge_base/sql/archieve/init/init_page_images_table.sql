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
