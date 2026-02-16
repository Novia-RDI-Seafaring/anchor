-- name: doc_delete_by_doc_id
DELETE FROM "%%SCHEMA%%".document_images WHERE document_id = $1

-- name: doc_get
SELECT id, image_type, page_number, image_base64, caption, alt_text, 
       bbox, width, height, metadata, created_at
FROM "%%SCHEMA%%".document_images
WHERE document_id = $1
ORDER BY page_number, id

-- name: doc_get_by_pages
SELECT id, image_type, page_number, image_base64, caption, alt_text, 
       bbox, width, height, metadata
FROM "%%SCHEMA%%".document_images
WHERE document_id = $1 AND page_number = ANY($2)
ORDER BY page_number, id

-- name: doc_get_by_type
SELECT id, image_type, page_number, image_base64, caption, alt_text, 
       bbox, width, height, metadata, created_at
FROM "%%SCHEMA%%".document_images
WHERE document_id = $1 AND image_type = $2
ORDER BY page_number, id

-- name: doc_insert
INSERT INTO "%%SCHEMA%%".document_images 
(document_id, image_type, page_number, image_base64, caption, alt_text, bbox, width, height, metadata)
VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10::jsonb)

-- name: page_delete_by_doc_id
DELETE FROM "%%SCHEMA%%".page_images WHERE document_id = $1

-- name: page_get
SELECT image_base64, width, height
FROM "%%SCHEMA%%".page_images
WHERE document_id = $1 AND page_number = $2

-- name: page_get_batch
SELECT page_number, image_base64, width, height
FROM "%%SCHEMA%%".page_images
WHERE document_id = $1 AND page_number = ANY($2)
ORDER BY page_number

-- name: page_get_batch_multi_doc
SELECT document_id, page_number, image_base64, width, height
FROM "%%SCHEMA%%".page_images
WHERE document_id = ANY($1) AND page_number = ANY($2)

-- name: page_insert
INSERT INTO "%%SCHEMA%%".page_images (document_id, page_number, image_base64, width, height)
VALUES ($1, $2, $3, $4, $5)

