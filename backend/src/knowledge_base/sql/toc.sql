-- name: get
SELECT toc_json FROM "%%SCHEMA%%".document_toc
WHERE document_id = $1

-- name: upsert
INSERT INTO "%%SCHEMA%%".document_toc (document_id, toc_json)
VALUES ($1, $2::jsonb)
ON CONFLICT (document_id) DO UPDATE SET
    toc_json = EXCLUDED.toc_json

