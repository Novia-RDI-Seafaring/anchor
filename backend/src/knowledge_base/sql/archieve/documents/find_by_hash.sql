SELECT *
FROM "%%SCHEMA%%".documents
WHERE metadata->>'content_hash' = $1
ORDER BY created_at DESC
LIMIT 1
