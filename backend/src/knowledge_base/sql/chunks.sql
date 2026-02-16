-- name: delete_by_doc_id
DELETE FROM "%%SCHEMA%%".chunks WHERE document_id = $1

-- name: get_by_section
SELECT id, content, metadata, chunk_index
FROM "%%SCHEMA%%".chunks
WHERE document_id = $1 
    AND metadata->'headings' @> $2::jsonb
ORDER BY chunk_index

-- name: get_metadata
SELECT document_id, metadata
FROM "%%SCHEMA%%".chunks
WHERE id = $1

-- name: insert
INSERT INTO "%%SCHEMA%%".chunks (document_id, chunk_index, content, embedding, metadata)
VALUES ($1, $2, $3, $4::vector, $5::jsonb)

-- name: search
SELECT 
    c.id,
    c.content,
    c.metadata,
    c.document_id,
    d.filename,
    1 - (c.embedding <=> $1::vector) as similarity
FROM "%%SCHEMA%%".chunks c
JOIN "%%SCHEMA%%".documents d ON c.document_id = d.document_id
WHERE 1 - (c.embedding <=> $1::vector) > $3
ORDER BY c.embedding <=> $1::vector
LIMIT $2

-- name: search_by_doc
SELECT 
    c.id,
    c.content,
    c.metadata,
    c.document_id,
    d.filename,
    1 - (c.embedding <=> $1::vector) as similarity
FROM "%%SCHEMA%%".chunks c
JOIN "%%SCHEMA%%".documents d ON c.document_id = d.document_id
WHERE c.document_id = $4
    AND 1 - (c.embedding <=> $1::vector) > $3
ORDER BY c.embedding <=> $1::vector
LIMIT $2

