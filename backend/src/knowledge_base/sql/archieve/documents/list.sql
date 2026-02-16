SELECT id, document_id, filename, source_type, mime_type, 
       file_size, chunk_count, status, created_at, updated_at
FROM "%%SCHEMA%%".documents
ORDER BY created_at DESC
