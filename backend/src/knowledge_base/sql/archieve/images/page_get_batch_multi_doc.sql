SELECT document_id, page_number, image_base64, width, height
FROM "%%SCHEMA%%".page_images
WHERE document_id = ANY($1) AND page_number = ANY($2)
