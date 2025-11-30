import asyncio
import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.vector_store import get_vector_store
from src.embeddings import get_embeddings_service

async def main():
    load_dotenv()
    
    print("--- Debugging Vector DB ---")
    
    # Initialize vector store
    try:
        store = await get_vector_store()
        stats = await store.get_stats()
        print(f"DB Stats: {stats}")
        
        docs = await store.list_documents()
        print(f"\nDocuments ({len(docs)}):")
        for doc in docs:
            print(f" - {doc['filename']} (ID: {doc['document_id']}) - Chunks: {doc['chunk_count']} - Status: {doc['status']}")
            
        if not docs:
            print("\nNo documents found. Please upload a document first.")
            return

        # Test Search
        print("\n--- Testing Search ---")
        query = "pump technical data"
        print(f"Query: '{query}'")
        
        embeddings_service = get_embeddings_service()
        query_embedding = embeddings_service.embed_text(query)
        print(f"Generated embedding of length: {len(query_embedding)}")
        
        # Search with default threshold
        results = await store.search(query_embedding, top_k=5)
        print(f"\nSearch Results (default threshold 0.5): {len(results)}")
        for r in results:
            print(f" - {r['filename']} ({r['similarity']:.4f}): {r['content'][:50]}...")
            
        # Search with low threshold
        print("\n--- Search with Low Threshold (0.0) ---")
        results_low = await store.search(query_embedding, top_k=5, threshold=0.0)
        print(f"Search Results (threshold 0.0): {len(results_low)}")
        for r in results_low:
            print(f" - {r['filename']} ({r['similarity']:.4f}): {r['content'][:50]}...")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'store' in locals() and store:
            await store.close()

if __name__ == "__main__":
    asyncio.run(main())
