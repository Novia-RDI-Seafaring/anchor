SELECT id, content, metadata, chunk_index
FROM "%%SCHEMA%%".chunks
WHERE document_id = $1 
    AND metadata->'headings' @> $2::jsonb
ORDER BY chunk_index
