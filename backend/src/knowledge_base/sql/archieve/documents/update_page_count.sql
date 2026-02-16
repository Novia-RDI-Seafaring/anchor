UPDATE "%%SCHEMA%%".documents 
SET page_count = $2, updated_at = CURRENT_TIMESTAMP
WHERE document_id = $1
