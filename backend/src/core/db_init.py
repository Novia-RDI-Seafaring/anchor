"""Synchronous DB bootstrap — runs once at startup before any async code."""

import psycopg2
from src.core.config import get_settings


def bootstrap_database() -> None:
    """
    Ensure the database is ready for the app:
      - anchor schema exists
      - vector extension is in the public schema (so SQLAlchemy can resolve the type)
      - documents registry table exists
    Ketju/LlamaIndex creates its own tables (data_ketju_vectors etc.) via
    perform_setup=True on first use — this just removes blockers.
    """
    settings = get_settings()
    conn = psycopg2.connect(
        host=settings.pgvector_host,
        port=settings.pgvector_port,
        dbname=settings.pgvector_db,
        user=settings.pgvector_user,
        password=settings.pgvector_password,
    )
    conn.autocommit = True
    cur = conn.cursor()
    try:
        schema = settings.db_schema

        # 1. Create app schema
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

        # 2. Ensure vector extension lives in public so the vector type is on the
        #    default search_path when SQLAlchemy creates ketju tables.
        cur.execute("""
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_extension e
                JOIN pg_namespace n ON e.extnamespace = n.oid
                WHERE e.extname = 'vector' AND n.nspname = 'public'
              ) THEN
                IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                  ALTER EXTENSION vector SET SCHEMA public;
                ELSE
                  CREATE EXTENSION vector SCHEMA public;
                END IF;
              END IF;
            END $$;
        """)

        # 3. Documents registry table (owned by this app, not ketju)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".documents (
                id           SERIAL PRIMARY KEY,
                document_id  TEXT UNIQUE NOT NULL,
                filename     TEXT NOT NULL,
                file_path    TEXT,
                source_type  TEXT DEFAULT 'file',
                mime_type    TEXT,
                file_size    INTEGER,
                page_count   INTEGER,
                chunk_count  INTEGER DEFAULT 0,
                status       TEXT DEFAULT 'pending',
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata     JSONB DEFAULT '{{}}'
            )
        """)

        # 4. Conversations table
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".conversations (
                id           TEXT PRIMARY KEY,
                title        TEXT NOT NULL DEFAULT 'New Conversation',
                messages     JSONB NOT NULL DEFAULT '[]',
                canvas_state JSONB NOT NULL DEFAULT '{{}}',
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4a. Add user_id column if it doesn't exist yet (migration)
        cur.execute(f"""
            ALTER TABLE "{schema}".conversations
            ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT ''
        """)

        # 5. Knowledge snippets table (reusable canvas sub-graphs)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".knowledge_snippets (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL DEFAULT '',
                name        TEXT NOT NULL DEFAULT 'Snippet',
                nodes       JSONB NOT NULL DEFAULT '[]',
                relations   JSONB NOT NULL DEFAULT '[]',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        print(f"[db_init] Ready — schema={schema!r}, vector extension in public")
    finally:
        cur.close()
        conn.close()
