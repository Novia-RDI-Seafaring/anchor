"""Document management API routes."""
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional

from src.knowledge_base.service import get_document_service
from .schemas import URLRequest

router = APIRouter(prefix="/api", tags=["documents"])


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    preserve_images: Optional[str] = Form("true"),
    preserve_tables: Optional[str] = Form("true"),
    enable_ocr: Optional[str] = Form("false"),
    table_mode: Optional[str] = Form("fast")
):
    """Upload and process a document via DocumentService."""
    try:
        preserve_images_bool = preserve_images.lower() == "true"
        preserve_tables_bool = preserve_tables.lower() == "true"
        enable_ocr_bool = enable_ocr.lower() == "true"
        
        if table_mode not in ["fast", "accurate"]:
            raise HTTPException(status_code=400, detail="table_mode must be 'fast' or 'accurate'")

        content = await file.read()
        service = await get_document_service()
        result = await service.upload_file(
            filename=file.filename,
            content=content,
            preserve_images=preserve_images_bool,
            preserve_tables=preserve_tables_bool,
            enable_ocr=enable_ocr_bool,
            table_mode=table_mode,
        )

        return {"success": True, "document": result}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/url")
async def add_url(request: URLRequest):
    """Add a URL to the knowledge base via DocumentService."""
    try:
        service = await get_document_service()
        result = await service.upload_url(request.url)
        return {"success": True, "document": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents")
async def list_documents():
    """List all documents in the knowledge base."""
    service = await get_document_service()
    docs = await service.list_documents()
    return {"success": True, "documents": docs}

@router.post("/documents/reingest")
async def reingest_documents():
    """Re-process all documents in the knowledge base."""
    try:
        service = await get_document_service()
        result = await service.reingest_all()
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/reset")
async def reset_knowledge_base():
    """Reset (clear) the entire knowledge base."""
    try:
        service = await get_document_service()
        result = await service.reset_knowledge_base()
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete a specific document."""
    try:
        service = await get_document_service()
        success = await service.delete_document(document_id)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats():
    """Get knowledge base statistics."""
    try:
        service = await get_document_service()
        stats = await service.get_stats()
        return {"success": True, **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/pipeline-status")
async def get_pipeline_statuses(filenames: str = ""):
    """Get pipeline progress for one or more documents (comma-separated filenames)."""
    from src.knowledge_base.service import get_pipeline_status, clear_pipeline_status

    names = [f.strip() for f in filenames.split(",") if f.strip()]
    result: dict = {}
    for fn in names:
        status = get_pipeline_status(fn)
        if status:
            result[fn] = status
            # Auto-clear "done" status after the frontend has seen it
            if status.get("stage") == "done":
                clear_pipeline_status(fn)
    return result


@router.post("/documents/{document_id}/pipeline")
async def run_document_pipeline(
    document_id: str,
    polish: bool = True,
    regions: bool = True,
    model: str = "gpt-5.4",
):
    """Run the full ingestion pipeline (silver + polish + gold regions) for one document."""
    try:
        service = await get_document_service()
        result = await service.run_pipeline_for_document(
            document_id,
            polish=polish,
            regions=regions,
            model=model,
        )
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/pipeline/all")
async def run_pipeline_all(
    polish: bool = True,
    regions: bool = True,
    model: str = "gpt-5.4",
):
    """Run the full ingestion pipeline for all documents."""
    try:
        service = await get_document_service()
        result = await service.run_pipeline_all(
            polish=polish,
            regions=regions,
            model=model,
        )
        return {"success": True, **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/gold/{filename:path}")
async def get_gold_data(filename: str):
    """Get gold-layer pre-extracted product data for a document."""
    from src.agent.tools.product_data import _find_by_filename
    data = _find_by_filename(filename)
    if not data:
        raise HTTPException(status_code=404, detail="No gold data for this document")
    return data


@router.get("/documents/regions/{filename:path}")
async def get_document_regions(filename: str):
    """Get all gold regions for a document (all pages)."""
    import os
    import re
    from pathlib import Path

    data_dir = Path(os.environ.get("ANCHOR_DATA_DIR") or (
        Path(__file__).resolve().parents[2] / "data"
    ))
    gold_dir = data_dir / "gold"

    # Slugify the filename to find the gold dir
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", filename.removesuffix(".pdf")).strip("-").lower()

    # Try exact slug, then scan for prefix match
    candidates = [gold_dir / slug]
    if not candidates[0].exists():
        candidates = [d for d in gold_dir.iterdir() if d.is_dir() and slug in d.name]

    pages: dict = {}
    for gold_slug_dir in candidates:
        pages_dir = gold_slug_dir / "pages"
        if not pages_dir.is_dir():
            continue
        import json as _json
        for rf in sorted(pages_dir.glob("*.regions.json")):
            try:
                data = _json.loads(rf.read_text())
            except Exception:
                continue
            page_no = data.get("page", 0)
            pages[page_no] = data.get("regions", [])

    if not pages:
        raise HTTPException(status_code=404, detail="No regions found for this document")
    return {"filename": filename, "pages": pages}


@router.get("/documents/regions/{filename:path}/{page}/{asset:path}")
async def get_region_asset(filename: str, page: int, asset: str):
    """Serve a gold region crop file (SVG or PNG)."""
    import os
    import re
    from pathlib import Path

    from fastapi.responses import FileResponse

    data_dir = Path(os.environ.get("ANCHOR_DATA_DIR") or (
        Path(__file__).resolve().parents[2] / "data"
    ))
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", filename.removesuffix(".pdf")).strip("-").lower()
    asset_path = data_dir / "gold" / slug / "pages" / asset

    if not asset_path.exists():
        # Try scanning for prefix match
        for d in (data_dir / "gold").iterdir():
            if d.is_dir() and slug in d.name:
                candidate = d / "pages" / asset
                if candidate.exists():
                    asset_path = candidate
                    break

    if not asset_path.exists():
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset}")

    media = "image/svg+xml" if asset.endswith(".svg") else "image/png"
    return FileResponse(asset_path, media_type=media)


@router.get("/documents/query-search")
async def query_search(q: str, entity: Optional[str] = None, top_k: int = 10):
    """Search the pre-computed Q&A index by natural language query.

    Returns instant answers with region refs — no LLM in the loop.
    """
    import os
    from pathlib import Path

    from openai import OpenAI
    from src.ingestion.query_index import load_query_index, search_queries

    data_dir = Path(os.environ.get("ANCHOR_DATA_DIR") or (
        Path(__file__).resolve().parents[2] / "data"
    ))
    index = load_query_index(data_dir)
    if not index:
        return {"results": [], "message": "No query index built yet."}

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.embeddings.create(model="text-embedding-3-large", input=[q])
    query_vector = response.data[0].embedding

    results = search_queries(index, query_vector, top_k=top_k, entity_filter=entity)
    return {"results": results}
