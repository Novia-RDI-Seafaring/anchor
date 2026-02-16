INSERT INTO "%%SCHEMA%%".document_toc (document_id, toc_json)
VALUES ($1, $2::jsonb)
ON CONFLICT (document_id) DO UPDATE SET
    toc_json = EXCLUDED.toc_json
