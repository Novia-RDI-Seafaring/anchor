For SQL table definitions and relationships.
Reading into `vector_store.py` to see all table definitions:

## Summary

**3 SQL tables** are created:

1. **`documents`** — Document metadata
   - Primary key: `id` (SERIAL)
   - Unique: `document_id` (TEXT)
   - Fields: filename, file_path, source_type, mime_type, file_size, page_count, chunk_count, status, timestamps, metadata (JSONB)

2. **`chunks`** — Document chunks with vector embeddings
   - Primary key: `id` (SERIAL)
   - Unique constraint: `(document_id, chunk_index)`
   - Fields: document_id, chunk_index, content, embedding (vector), metadata (JSONB), created_at
   - Index: HNSW on `embedding` for similarity search

3. **`page_images`** — Rendered PDF page images
   - Primary key: `id` (SERIAL)
   - Unique constraint: `(document_id, page_number)`
   - Fields: document_id, page_number, image_base64, width, height, created_at

## Relationships

- **`chunks.document_id` → `documents.document_id`** (logical, no FK)
- **`page_images.document_id` → `documents.document_id`** (logical, no FK)

Both `chunks` and `page_images` reference `documents` via `document_id` (TEXT). No foreign key constraints are enforced (see line 76 comment: "no FK constraint for simplicity"). The `search()` method joins `chunks` and `documents` on `document_id` (lines 210, 226).

# It depends on context. Here are trade-offs:

## When it's acceptable

- Performance: Avoiding FK checks can speed up bulk inserts/deletes
- Flexibility: Easier to delete documents without cascading or orphan handling
- Distributed systems: In some architectures, FK constraints can complicate scaling
- Prototyping/MVP: Faster iteration without constraint management

## When it's problematic

- Data integrity: Orphaned chunks/page_images can accumulate if documents are deleted
- Silent bugs: Referential errors may go unnoticed
- Maintenance: Harder to reason about data consistency

## In this codebase

Looking at `vector_store.py`:
- `delete_document()` (line 253) only deletes from `documents`, leaving orphaned chunks/page_images
- `add_chunks()` (line 159) deletes existing chunks before inserting, which helps
- No cascade cleanup is enforced

## Recommendation

For production, consider:
1. Adding FK constraints with `ON DELETE CASCADE` for automatic cleanup
2. Or updating `delete_document()` to explicitly delete related rows first

The current approach works but risks data inconsistency. It's a common trade-off in vector stores prioritizing write performance, but not ideal for data integrity.

