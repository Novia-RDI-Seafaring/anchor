SELECT page_number, image_base64, width, height
FROM "%%SCHEMA%%".page_images
WHERE document_id = $1 AND page_number = ANY($2)
ORDER BY page_number
