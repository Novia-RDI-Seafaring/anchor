INSERT INTO "%%SCHEMA%%".documents (document_id, filename, file_path, source_type, mime_type, file_size, metadata)
VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
ON CONFLICT (document_id) DO UPDATE SET
    filename = EXCLUDED.filename,
    file_path = EXCLUDED.file_path,
    source_type = EXCLUDED.source_type,
    mime_type = EXCLUDED.mime_type,
    file_size = EXCLUDED.file_size,
    metadata = EXCLUDED.metadata,
    updated_at = CURRENT_TIMESTAMP
RETURNING id, document_id, filename, status, created_at
