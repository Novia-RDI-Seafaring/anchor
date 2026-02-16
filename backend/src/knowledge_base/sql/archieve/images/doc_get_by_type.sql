SELECT id, image_type, page_number, image_base64, caption, alt_text, 
       bbox, width, height, metadata, created_at
FROM "%%SCHEMA%%".document_images
WHERE document_id = $1 AND image_type = $2
ORDER BY page_number, id
