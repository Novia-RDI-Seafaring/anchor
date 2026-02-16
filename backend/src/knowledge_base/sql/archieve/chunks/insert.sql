INSERT INTO "%%SCHEMA%%".chunks (document_id, chunk_index, content, embedding, metadata)
VALUES ($1, $2, $3, $4::vector, $5::jsonb)
