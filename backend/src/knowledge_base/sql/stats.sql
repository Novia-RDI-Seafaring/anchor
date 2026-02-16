-- name: count_chunks
SELECT COUNT(*) FROM "%%SCHEMA%%".chunks

-- name: count_document_images
SELECT COUNT(*) FROM "%%SCHEMA%%".document_images

-- name: count_documents
SELECT COUNT(*) FROM "%%SCHEMA%%".documents

-- name: count_page_images
SELECT COUNT(*) FROM "%%SCHEMA%%".page_images

-- name: count_processed_docs
SELECT COUNT(*) FROM "%%SCHEMA%%".documents WHERE status = 'processed'

-- name: reset
DELETE FROM "%%SCHEMA%%".chunks;
DELETE FROM "%%SCHEMA%%".page_images;
DELETE FROM "%%SCHEMA%%".document_images;
DELETE FROM "%%SCHEMA%%".documents;

