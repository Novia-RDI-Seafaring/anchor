import asyncio
import os
import sys
import asyncpg
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.config import get_settings

async def reset_tables():
    settings = get_settings()
    print(f"Connecting to {settings.pgvector_host}...")
    
    conn = await asyncpg.connect(
        host=settings.pgvector_host,
        port=settings.pgvector_port,
        user=settings.pgvector_user,
        password=settings.pgvector_password,
        database=settings.pgvector_db,
        server_settings={
            "search_path": f'"{settings.db_schema}", public, extensions'
        }
    )
    
    try:
        # Drop tables that have embedding columns or depend on them
        tables_to_drop = [
            "chunks",
            "data_documents", # This is the one Ketju created (data_ + table_name)
            "data_kb_vectors", # Potential variant
        ]
        
        for table in tables_to_drop:
            print(f"Dropping table {settings.db_schema}.{table} if exists...")
            await conn.execute(f'DROP TABLE IF EXISTS "{settings.db_schema}"."{table}" CASCADE')
            
        print("Tables dropped successfully. They will be recreated with the correct dimension on next run.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(reset_tables())
