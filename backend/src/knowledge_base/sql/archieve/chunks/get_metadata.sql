SELECT document_id, metadata
FROM "%%SCHEMA%%".chunks
WHERE id = $1
