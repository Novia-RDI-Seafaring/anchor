import os
import json
from ketju.config import DOCS_DIR, DATA_DIR
from ketju.examples._cli import missing_optional_deps_message

try:
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route, Mount
    from starlette.requests import Request
    from starlette.responses import Response as StarletteResponse
    from pydantic import BaseModel, Field
    from typing import List, Optional
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.ag_ui import StateDeps
    from llama_index.core.base.response.schema import Response as LlamaResponse
except ModuleNotFoundError as e:
    raise SystemExit(
        missing_optional_deps_message(
            extras="--extra rag --extra docling --extra agent --extra agui",
            run_as_module="ketju.examples.agui_agent",
            run_tail="--path <PATH>",
        )
    ) from e

import argparse
from pathlib import Path

def get_folder_and_files() -> tuple[Path, list[Path]]:
    parser = argparse.ArgumentParser(description="Run AG-UI agent backend.")
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Path to the documentation directory.",
    )
    args = parser.parse_args()
    if args.path is not None:
        try:
            _path = Path(args.path)
            if not _path.exists():
                raise FileNotFoundError(f"Path {_path} does not exist")
            if _path.is_file():
                _folder = _path.parent
                _files = [_path]
                return _folder, _files
            elif _path.is_dir():
                _folder = _path
                _files = list(_path.glob("*.pdf"))
            else:
                raise ValueError(f"Path {_path} is not a file or directory")
        except Exception as e:
            raise ValueError(f"Error parsing path {_path}: {e}")
        return _folder, _files
    else:
        _folder = DOCS_DIR / "interdimensional-systems"
        _files = [f for f in _folder.glob("*.pdf") if f.is_file()]
        return _folder, _files 


from ketju.core.instrumentation import instrument_ketju, configure_otlp_tracing
try:
    configure_otlp_tracing(service_name="rag-agent", otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317/v1/traces"))
    instrument_ketju(service_name="rag-agent", enable_logfire=False, instrument_pydantic_ai=True, instrument_llamaindex=True, quiet=True)
except Exception as e:
    print(f"Error configuring instrumentation: {e}")


def setup_rag(ingest: bool = False):
    from llama_index.llms.openai import OpenAI
    from llama_index.core import Settings
    from llama_index.embeddings.openai import OpenAIEmbedding
    from ketju.rag.llama_index.variants.simple_docling_full_ctx import SimpleDoclingFullCtxRag
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    Settings.llm = OpenAI(model="gpt-4o-mini")

    persist_dir = DATA_DIR / "agui_app"
    
    srag = SimpleDoclingFullCtxRag(name="agui_app", persist_dir=persist_dir)
    
    return srag
rag = setup_rag(ingest=True)

class DocSnip(BaseModel):
    id: str
    page: int
    bbox: list[int]

class SnipNote(BaseModel):
    snippet: DocSnip
    note: Optional[str] = None
    user_comments: List[str] = Field(default_factory=list)

class DocRef(BaseModel):
    id: str
    snippets: list[SnipNote]
    title: str
    description: str
    user_comments: List[str] = Field(default_factory=list)


class AgentState(BaseModel):
    docrefs: List[DocRef] = Field(default_factory=list)

async def healthz(request: Request):
    return JSONResponse({"status": "ok"})

DepsType = StateDeps[AgentState]

agent = Agent(
    model="gpt-4o-mini",
    deps_type=DepsType,
)
@agent.instructions
def instructions(ctx: RunContext[StateDeps[AgentState]]) -> str:
    return """
    You are a helpful assistant that help answer questions from documents.
    when youuse facts from a pdf file, refere nce the source like this (as the user will be able to click on them and see the full document with that piece highlighed):

    Example:
    The transport lengths of the Wärtsilä 32 engine generating set are as follows: 

    12V32: <pdffact file="wartsila-32.pdf" title="W32 PG Leaflet" page="3" bbox="[100, 100, 200, 200]">10,226 mm</pdffact>
    16V32: <pdffact file="wartsila-32.pdf" title="W32 PG Leaflet" page="3" bbox="[100, 200, 300, 300]">11,189 mm</pdffact>
    20V32: <pdffact file="wartsila-32.pdf" title="W32 PG Leaflet" page="3" bbox="[100, 300, 400, 400]">13,072 mm</pdffact>
    Assuming you know the data and it is from the response you got from consulting the documents. Do not hallucinate the props.


    """

agent.history_processors



@agent.tool
def consult_documents(ctx: RunContext[StateDeps[AgentState]], query: str) -> LlamaResponse:
    print(f"Consulting documents: {query}")
    return rag.query(query)

@agent.tool
def get_model(ctx: RunContext[StateDeps[AgentState]]) -> str:
    """Get the model name"""
    print(f"running tool, Using model: {ctx.model.model_name}")
    return "Using model: " + ctx.model.model_name + " when replying tella joke..."


@agent.tool
def foo(ctx: RunContext[StateDeps[AgentState]]) -> str:
    """Get the model name"""
    print(f"running tool, FOOOO: {ctx.model.model_name}")
    from devtools import debug
    debug(ctx)
    import sys
    print(ctx)
    sys.stdout.write(f"Foo is {ctx.model.model_name}")

    return "Foo is " + "".join(ctx.model.model_name.split()[::-1]) + ""

# Build the AG-UI ASGI app
rag_agent_app = agent.to_ag_ui(
    deps=StateDeps(AgentState()),

    
)

async def serve_pdf(request: Request):
    file_name = request.query_params.get("file")
    folder, files = get_folder_and_files()
    for file in files:
        if file.name == file_name:
            return StarletteResponse(file.read_bytes(), media_type="application/pdf")
    return StarletteResponse(b"File not found", status_code=404, media_type="text/plain")

# Main Starlette app
app = Starlette(
    routes=[
        Route("/healthz", healthz, methods=["GET"]),
        Route("/serve_pdf", serve_pdf, methods=["GET"]),
        Mount("/agent", rag_agent_app),
    ]
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0", # due to ipv6 only project. see https://docs.railway.com/guides/private-networking
        port=int(os.getenv("PORT", "8080")),
        log_level="info",
    )
