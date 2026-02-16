INSERT INTO "%%SCHEMA%%".document_images 
(document_id, image_type, page_number, image_base64, caption, alt_text, bbox, width, height, metadata)
VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10::jsonb)
