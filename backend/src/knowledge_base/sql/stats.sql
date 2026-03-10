-- name: count_documents
SELECT COUNT(*) FROM "%%SCHEMA%%".documents

-- name: count_processed_docs
SELECT COUNT(*) FROM "%%SCHEMA%%".documents WHERE status = 'processed'

-- name: reset_documents
DELETE FROM "%%SCHEMA%%".documents
