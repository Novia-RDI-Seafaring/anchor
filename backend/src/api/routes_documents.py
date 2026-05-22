"""Document management API routes."""
import os
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends
from typing import Optional

from src.core.config import get_settings
from src.knowledge_base.service import get_document_service
from .schemas import URLRequest
from .security import require_write_access

router = APIRouter(prefix="/api", tags=["documents"])


@router.post("/documents/upload", dependencies=[Depends(require_write_access)])
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


@router.post("/documents/url", dependencies=[Depends(require_write_access)])
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

@router.post("/documents/reingest", dependencies=[Depends(require_write_access)])
async def reingest_documents():
    """Re-process all documents in the knowledge base."""
    try:
        service = await get_document_service()
        result = await service.reingest_all()
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/reset", dependencies=[Depends(require_write_access)])
async def reset_knowledge_base():
    """Reset (clear) the entire knowledge base."""
    try:
        service = await get_document_service()
        result = await service.reset_knowledge_base()
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{document_id}", dependencies=[Depends(require_write_access)])
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


@router.get("/documents/pipeline-detail/{filename:path}")
async def get_pipeline_detail(filename: str):
    """Return a summary of all pipeline artifacts for a document.

    Shows what exists in bronze / silver / gold so the frontend can render
    a pipeline-inspector modal.
    """
    import re
    import json as _json
    from pathlib import Path

    settings = get_settings()
    data_dir = settings.data_dir
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", filename.removesuffix(".pdf")).strip("-").lower()

    detail: dict = {
        "filename": filename,
        "slug": slug,
        "bronze": None,
        "silver": None,
        "gold": None,
    }

    # Bronze
    bronze_path = data_dir / "bronze" / filename
    if bronze_path.exists():
        detail["bronze"] = {
            "path": str(bronze_path),
            "size_kb": round(bronze_path.stat().st_size / 1024, 1),
        }

    # Silver
    silver_dir = data_dir / "silver" / slug
    if silver_dir.exists():
        silver: dict = {"pages": [], "has_index": False, "has_docling": False}
        silver["has_index"] = (silver_dir / "index.json").exists()
        silver["has_docling"] = (silver_dir / "docling.json").exists()

        # index summary
        index_path = silver_dir / "index.json"
        if index_path.exists():
            try:
                idx = _json.loads(index_path.read_text())
                silver["page_count"] = idx.get("document", {}).get("page_count", 0)
                silver["outline_count"] = len(idx.get("outline", []))
                silver["table_count"] = len(idx.get("tables", []))
                silver["figure_count"] = len(idx.get("figures", []))
            except Exception:
                pass

        # per-page files
        pages_dir = silver_dir / "pages"
        if pages_dir.exists():
            page_nums = sorted({
                int(p.stem.split(".")[0])
                for p in pages_dir.iterdir()
                if p.stem.split(".")[0].isdigit()
            })
            for pg in page_nums:
                entry: dict = {"page": pg}
                entry["has_png"] = (pages_dir / f"{pg}.png").exists()
                entry["has_raw_md"] = (pages_dir / f"{pg}.raw.md").exists()
                entry["has_md"] = (pages_dir / f"{pg}.md").exists()
                md_path = pages_dir / f"{pg}.md"
                if md_path.exists():
                    text = md_path.read_text(encoding="utf-8")
                    entry["md_preview"] = text[:300] + ("..." if len(text) > 300 else "")
                silver["pages"].append(entry)
        detail["silver"] = silver

    # Gold
    gold_dir = data_dir / "gold" / slug
    if not gold_dir.exists():
        # scan for prefix match
        parent = data_dir / "gold"
        if parent.exists():
            for d in parent.iterdir():
                if d.is_dir() and slug in d.name:
                    gold_dir = d
                    break

    if gold_dir.exists():
        gold: dict = {"pages": []}
        pages_dir = gold_dir / "pages"
        if pages_dir.is_dir():
            for rf in sorted(pages_dir.glob("*.regions.json")):
                try:
                    rdata = _json.loads(rf.read_text())
                    regions = rdata.get("regions", [])
                    gold["pages"].append({
                        "page": rdata.get("page", 0),
                        "region_count": len(regions),
                        "region_kinds": [r.get("kind", "?") for r in regions],
                    })
                except Exception:
                    pass
        detail["gold"] = gold

    # Current pipeline status (in-memory)
    from src.knowledge_base.service import get_pipeline_status
    status = get_pipeline_status(filename)
    if status:
        detail["status"] = status

    return detail


@router.get("/documents/silver/{filename:path}/page/{page}")
async def get_silver_page(filename: str, page: int, kind: str = "md"):
    """Serve a silver page asset: md, raw, or png.

    ?kind=md   → polished markdown (text/markdown)
    ?kind=raw  → raw markdown (text/markdown)
    ?kind=png  → page image (image/png)
    """
    import re
    from pathlib import Path
    from fastapi.responses import FileResponse, PlainTextResponse

    data_dir = get_settings().data_dir
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", filename.removesuffix(".pdf")).strip("-").lower()
    pages_dir = data_dir / "silver" / slug / "pages"

    if kind == "png":
        path = pages_dir / f"{page}.png"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Page PNG not found")
        return FileResponse(path, media_type="image/png")
    elif kind == "raw":
        path = pages_dir / f"{page}.raw.md"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Raw markdown not found")
        return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown")
    else:
        path = pages_dir / f"{page}.md"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Polished markdown not found")
        return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown")


@router.get("/documents/gold/{filename:path}/page/{page}/regions")
async def get_gold_page_regions(filename: str, page: int):
    """Get all regions for a specific gold page, with full detail."""
    import re
    import json as _json
    from pathlib import Path

    data_dir = get_settings().data_dir
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", filename.removesuffix(".pdf")).strip("-").lower()
    gold_dir = data_dir / "gold" / slug

    if not gold_dir.exists():
        parent = data_dir / "gold"
        if parent.exists():
            for d in parent.iterdir():
                if d.is_dir() and slug in d.name:
                    gold_dir = d
                    break

    regions_path = gold_dir / "pages" / f"{page}.regions.json"
    if not regions_path.exists():
        raise HTTPException(status_code=404, detail="No regions for this page")

    data = _json.loads(regions_path.read_text())
    return data


@router.post("/documents/{document_id}/pipeline", dependencies=[Depends(require_write_access)])
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


@router.post("/documents/pipeline/all", dependencies=[Depends(require_write_access)])
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


@router.get("/documents/index/{filename:path}")
async def get_document_index(filename: str):
    """Get the silver index (outline, tables, figures) for a document."""
    import re
    import json as _json
    from pathlib import Path

    data_dir = get_settings().data_dir
    silver_dir = data_dir / "silver"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", filename.removesuffix(".pdf")).strip("-").lower()

    index_path = silver_dir / slug / "index.json"
    if not index_path.exists():
        # Scan for prefix match
        for d in silver_dir.iterdir() if silver_dir.exists() else []:
            if d.is_dir() and slug in d.name:
                candidate = d / "index.json"
                if candidate.exists():
                    index_path = candidate
                    break

    if not index_path.exists():
        raise HTTPException(status_code=404, detail="No index found for this document")

    return _json.loads(index_path.read_text())


@router.get("/documents/region-asset/{slug}/{asset:path}")
async def get_region_asset(slug: str, asset: str):
    """Serve a gold region crop file (SVG or PNG).

    ``slug`` is the document slug (e.g. ``sample-pump-datasheet``).
    ``asset`` is the page-relative path (e.g. ``1/r5.svg``).
    """
    from fastapi.responses import FileResponse

    data_dir = get_settings().data_dir
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


@router.get("/documents/regions/{filename:path}")
async def get_document_regions(filename: str):
    """Get all gold regions for a document (all pages)."""
    import re
    import json as _json

    data_dir = get_settings().data_dir
    gold_dir = data_dir / "gold"

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", filename.removesuffix(".pdf")).strip("-").lower()

    candidates = [gold_dir / slug]
    if not candidates[0].exists():
        candidates = [d for d in gold_dir.iterdir() if d.is_dir() and slug in d.name]

    pages: dict = {}
    for gold_slug_dir in candidates:
        pages_dir = gold_slug_dir / "pages"
        if not pages_dir.is_dir():
            continue
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


@router.get("/documents/gold-map/{filename:path}")
async def get_gold_map(filename: str):
    """Get all gold regions + page metadata for rendering a region map overlay.

    Returns pages with regions, bbox coordinates (PDF points, BOTTOMLEFT origin),
    and the page size in PDF points (inferred from bbox_union in pages.meta.json
    or defaulting to A4).
    """
    import re
    import json as _json

    data_dir = get_settings().data_dir
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", filename.removesuffix(".pdf")).strip("-").lower()

    # Load gold regions
    gold_dir = data_dir / "gold" / slug
    if not gold_dir.exists():
        parent = data_dir / "gold"
        if parent.exists():
            for d in parent.iterdir():
                if d.is_dir() and slug in d.name:
                    gold_dir = d
                    break

    pages_data: dict = {}
    if gold_dir.exists():
        pages_dir = gold_dir / "pages"
        if pages_dir.is_dir():
            for rf in sorted(pages_dir.glob("*.regions.json")):
                try:
                    data = _json.loads(rf.read_text())
                except Exception:
                    continue
                page_no = data.get("page", 0)
                pages_data[page_no] = data.get("regions", [])

    # Load page metadata for dimensions
    silver_dir = data_dir / "silver" / slug
    if not silver_dir.exists():
        sr = data_dir / "silver"
        if sr.exists():
            for d in sr.iterdir():
                if d.is_dir() and slug in d.name:
                    silver_dir = d
                    break

    page_count = 0
    # Default A4 in points
    page_width = 595.0
    page_height = 842.0

    index_path = silver_dir / "index.json"
    if index_path.exists():
        try:
            idx = _json.loads(index_path.read_text())
            page_count = idx.get("document", {}).get("page_count", 0)
        except Exception:
            pass

    # Try to get actual page dimensions from pages.meta.json bbox_union
    meta_path = silver_dir / "pages.meta.json"
    if meta_path.exists():
        try:
            meta = _json.loads(meta_path.read_text())
            pages_meta = meta.get("pages", {})
            if pages_meta:
                first_key = next(iter(pages_meta))
                bbox_union = pages_meta[first_key].get("bbox_union", [])
                if len(bbox_union) == 4:
                    # bbox_union is [left, top, right, bottom] in BOTTOMLEFT coords
                    # top is the highest y, which approximates page height
                    # right approximates page width
                    page_width = max(bbox_union[2], page_width)
                    page_height = max(bbox_union[1], page_height)
        except Exception:
            pass

    return {
        "filename": filename,
        "slug": slug,
        "page_count": page_count,
        "page_width": page_width,
        "page_height": page_height,
        "pages": pages_data,
    }


@router.get("/documents/query-search")
async def query_search(q: str, entity: Optional[str] = None, top_k: int = 10):
    """Search the pre-computed Q&A index by natural language query.

    Returns instant answers with region refs — no LLM in the loop.
    """
    import os
    from pathlib import Path

    from openai import OpenAI
    from src.ingestion.query_index import load_query_index, search_queries

    data_dir = get_settings().data_dir
    index = load_query_index(data_dir)
    if not index:
        return {"results": [], "message": "No query index built yet."}

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.embeddings.create(model="text-embedding-3-large", input=[q])
    query_vector = response.data[0].embedding

    results = search_queries(index, query_vector, top_k=top_k, entity_filter=entity)
    return {"results": results}
