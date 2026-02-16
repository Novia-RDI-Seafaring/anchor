-- name: delete
DELETE FROM "%%SCHEMA%%".documents WHERE document_id = $1

-- name: find_by_hash
SELECT *
FROM "%%SCHEMA%%".documents
WHERE metadata->>'content_hash' = $1
ORDER BY created_at DESC
LIMIT 1

-- name: find_by_url
SELECT *
FROM "%%SCHEMA%%".documents
WHERE source_type = 'url'
  AND metadata->>'source_url' = $1
ORDER BY created_at DESC
LIMIT 1

-- name: get
SELECT * FROM "%%SCHEMA%%".documents WHERE document_id = $1

-- name: insert
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

-- name: list
SELECT id, document_id, filename, source_type, mime_type, 
       file_size, chunk_count, status, created_at, updated_at
FROM "%%SCHEMA%%".documents
ORDER BY created_at DESC

-- name: update_chunk_count
UPDATE "%%SCHEMA%%".documents 
SET chunk_count = $2, status = 'processed', updated_at = CURRENT_TIMESTAMP
WHERE document_id = $1

-- name: update_page_count
UPDATE "%%SCHEMA%%".documents 
SET page_count = $2, updated_at = CURRENT_TIMESTAMP
WHERE document_id = $1

