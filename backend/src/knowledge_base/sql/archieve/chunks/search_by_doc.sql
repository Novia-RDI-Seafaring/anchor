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
