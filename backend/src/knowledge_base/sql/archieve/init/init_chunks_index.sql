CREATE INDEX IF NOT EXISTS chunks_embedding_idx 
ON "%%SCHEMA%%".chunks USING hnsw (embedding vector_cosine_ops);
