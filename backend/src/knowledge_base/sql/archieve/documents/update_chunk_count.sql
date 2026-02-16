UPDATE "%%SCHEMA%%".documents 
SET chunk_count = $2, status = 'processed', updated_at = CURRENT_TIMESTAMP
WHERE document_id = $1
