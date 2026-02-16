SELECT *
FROM "%%SCHEMA%%".documents
WHERE source_type = 'url'
  AND metadata->>'source_url' = $1
ORDER BY created_at DESC
LIMIT 1
