# Adoption

A practical answer to four questions you'll get if you show Anchor to anyone outside the team:

1. How does a new user actually start?
2. How do they wire Anchor into the agent harness they already use?
3. Can they see the canvas inside that harness?
4. Can they ingest sensitive PDFs without sending anything to OpenAI?

Tone of this doc is operational. No marketing. Where something doesn't work today, it says so.

---

## 1. Onboarding — what a new user does today

Honest walk-through. The README sounds smoother than the real path because some steps are still manual.

- **Install Python 3.12+, Node 20+, uv, pnpm.** Anchor needs all four. macOS and Linux only; Windows is unverified. `uv` is the Python toolchain (`pip install uv` or `brew install uv`); `pnpm` builds the React frontend. You can skip pnpm only if you `uv tool install` a prebuilt wheel that already contains `web/dist/`.

- **Pick `~/anchor-data` as your data dir.** The README still shows `./data` in some examples, but the canonical location (and the default of `anchor install claude-code`) is `~/anchor-data`. Use it everywhere. Mixing the two is the first foot-gun: ingest writes to one, serve reads from the other, and you wonder why the canvas is empty. Pass `--data-dir ~/anchor-data` to every command or set `ANCHOR_DATA_DIR=~/anchor-data`.

- **From source, the boot story is two processes.** `uv sync` in `v2/`, then `uv run anchor serve --data-dir ~/anchor-data` in one terminal and `pnpm --filter @anchor/web dev` in another. There's a convenience script at `v2/scripts/dev.sh` but it points at `./data`, not `~/anchor-data`. If you use it, edit the path or `cd` into a folder where `./data` is what you want.

- **From a wheel, it's one command but you build the wheel first.** `uv build --wheel` produces `dist/anchor-0.2.0-py3-none-any.whl`. `uv tool install ./dist/anchor-0.2.0-py3-none-any.whl` puts `anchor` and `anchor-mcp` on your PATH. The wheel only contains the prebuilt frontend if you ran `pnpm --filter @anchor/web build` first; if you didn't, `anchor serve` boots but serves no UI. That's an easy step to miss.

- **OpenAI is optional but the defaults assume it.** No `ANCHOR_OPENAI_API_KEY` means silver builds (Docling extraction, per-page markdown, page PNGs) but gold extraction is skipped. The CLI doesn't warn you about this on first run; you only notice when `anchor regions <slug>` returns nothing. Embeddings have a local fallback (`sentence-transformers`, see section 4), so vector search works air-gapped today.

- **Mystery deps live behind extensions.** The CAD extension needs `trimesh` (already in `pyproject.toml`). The FMU extension wants `fmpy`, which is **not** in `pyproject.toml`; if you don't install it, `anchor fmu inspect` errors out at runtime with `FMU extension not available`. There's no `uv sync --extra fmus` group yet — you install fmpy yourself.

- **`anchor install claude-code` is the one-shot harness setup.** It writes `~/.claude/mcp.json` and a skill file at `~/.claude/skills/anchor/SKILL.md`. After that you restart Claude Code, type `/mcp`, and `anchor` shows up with ~17 tools. The same command exists for Cursor: `anchor install cursor`. No equivalent yet for opencode (you write the JSON by hand — see section 2).

- **The single rough edge that catches everyone:** `anchor canvas snapshot` (and `canvas_snapshot` over MCP) needs a running `anchor serve` to loop through, because the snapshotter uses headless Chromium to render the same React app you see in the browser. If serve isn't running, snapshot fails with a `RuntimeError`. The MCP server tells you, but only after the agent tries.

---

## 2. Harness install recipes

Anchor's MCP entry point is `anchor-mcp` (declared in `v2/pyproject.toml` under `[project.scripts]`), backed by `anchor.adapters.mcp.stdio_main:main`. Any harness that supports MCP-stdio can spawn it. Three popular ones:

### Claude Code

One command:

```bash
anchor install claude-code --data-dir ~/anchor-data
```

That writes `~/.claude/mcp.json` and `~/.claude/skills/anchor/SKILL.md`. Restart Claude Code (Cmd+Q, reopen) and `/mcp` lists `anchor` with the full tool set. The skill primes Claude to use Anchor when you mention PDFs, datasheets, or workspaces.

If you want to do it by hand instead, drop this into `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "anchor": {
      "command": "/Users/you/.local/bin/anchor-mcp",
      "args": ["--data-dir", "/Users/you/anchor-data"]
    }
  }
}
```

The `command` is whatever `which anchor-mcp` prints.

### Cursor

One command:

```bash
anchor install cursor --data-dir ~/anchor-data
```

Writes `~/.cursor/mcp.json`. Same JSON shape as Claude Code. Restart Cursor. Open the MCP panel (Settings → Features → Model Context Protocol) and verify `anchor` is green.

By hand, into `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "anchor": {
      "command": "/Users/you/.local/bin/anchor-mcp",
      "args": ["--data-dir", "/Users/you/anchor-data"]
    }
  }
}
```

### opencode

opencode reads MCP servers from `~/.config/opencode/opencode.json` (or `./opencode.json` per-project). There's no `anchor install opencode` target yet, so you write the JSON yourself:

```json
{
  "mcp": {
    "anchor": {
      "type": "local",
      "command": ["anchor-mcp", "--data-dir", "/Users/you/anchor-data"],
      "enabled": true
    }
  }
}
```

Restart opencode. `/mcp` (or the equivalent in your shell) should list `anchor`. The tool surface is identical across all three harnesses because they all spawn the same `anchor-mcp` stdio process.

### What about Claude.ai (mobile / web)?

Not supported today. Claude.ai's hosted product only speaks **remote MCP over HTTP**, not stdio. Anchor ships an MCP-SSE endpoint inside `anchor serve` (`/mcp/sse`), but it isn't yet packaged as a Claude.ai-shaped remote MCP server (no auth handshake, no OAuth). On the roadmap, not today.

### What about Cline, Goose, Continue, etc.?

Anything that supports MCP-stdio with a `command` + `args` shape works the same way. The only knob is where that harness reads its MCP config. Find the file, drop the JSON block from above into it, restart.

---

## 3. Seeing the canvas inside an agent harness

The honest answer is **sort of**, with a strong asterisk on the demo.

The MCP host harnesses (Claude Code, Cursor, opencode) only render two things from a tool call: text and inline images (when the tool returns an MCP `ImageContent` block). They do not embed iframes, web components, or React apps. So a "live React-Flow canvas inside Cursor" is not a thing today and won't be for the foreseeable future without web-component embedding, which none of the host harnesses support.

What Anchor does have is a **snapshot** capability. `WorkspaceService.snapshot()` in `v2/src/anchor/core/services/workspace_service.py` delegates to a `SnapshotPort`; the wired implementation is `HeadlessChromiumSnapshotter`, which navigates a headless Chromium to `http://localhost:8002/c/<slug>` and screenshots the rendered canvas as PNG (or SVG).

That capability is exposed on every adapter:

- **CLI:** `anchor canvas snapshot <slug> --out canvas.png --base-url http://localhost:8002`
- **HTTP:** `POST /api/workspaces/{slug}/snapshot`
- **MCP:** `canvas_snapshot` tool, with `format=path|base64` and `image_format=png|svg`

But here's the asterisk you need to know before you demo it: the MCP `canvas_snapshot` handler returns a **JSON envelope** with a `base64` field — it does **not** return an MCP `ImageContent` block. Read `v2/src/anchor/adapters/mcp/server.py` and `v2/src/anchor/adapters/mcp/handlers_canvas.py`: every tool result is wrapped in a `TextContent`. So Claude Code or Cursor receives a base64 string inside JSON text. The agent has to decide what to do with it. Some agents will inline-render base64 PNGs when asked; many will just describe the bytes.

For a polished "the agent shows me the canvas inline" demo, the next step is to teach the MCP handler to return `ImageContent` when `format="image"`. That's a small change inside `handlers_canvas.call_tool` plus a tweak to the dispatcher in `server.py`. Until then, the path that works is:

**Demo recipe (works today):**

1. Start `anchor serve --data-dir ~/anchor-data --port 8002` in one terminal.
2. Open `http://localhost:8002/c/<slug>` in a browser, on the projector.
3. In Claude Code / Cursor, ask the agent to add nodes, draw evidence edges, place spec rows. The browser updates live via SSE — that's your "see the canvas" moment. The audience watches the agent drive the canvas in real time, without the agent ever rendering it itself.
4. If you want a static image the agent can quote in chat, ask "snapshot the canvas to disk" — the agent calls `canvas_snapshot` with `format="path"` and gets back a file path; it can read the bytes and reference them. Inline display in the chat depends on the host.

The browser projection is the demo. The MCP snapshot is the "I want a screenshot in my report" path.

---

## 4. Running ingest on local / Azure / other backends

Two pipeline steps call OpenAI directly:

- `infra/llm/openai_md_polisher.py` — vision-LM polish at silver → silver
- `infra/llm/openai_region_extractor.py` — vision-LM region extraction at silver → gold

Both implement ports defined in `v2/src/anchor/extensions/anchor_pdfs/core/ports/` (`PageMdPolisher`, `RegionExtractor`). Swapping the backend means writing a new infra class next to the existing one and wiring it in `cli/main.py:_build_real_services` (the same place that picks the OpenAI client today). Core does not change.

Embeddings already have a local fallback: `LocalSentenceTransformerEmbedder` in `infra/llm/local_sentence_transformer_embedder.py` ships `BAAI/bge-small-en-v1.5` via `sentence-transformers` (install with `uv sync --extra local-embed`). No API key, no network, no Ollama. Vector search works air-gapped today.

### A. Azure OpenAI

The closest path to "still cloud, but enterprise-allowed." OpenAI's Python SDK supports an `AzureOpenAI` client that takes `azure_endpoint`, `api_key`, and `api_version`. Roughly 30 lines of delta from `openai_md_polisher.py`:

```
# v2/src/anchor/extensions/anchor_pdfs/infra/llm/azure_md_polisher.py
from openai import AzureOpenAI

class AzurePageMdPolisher:
    def __init__(self, api_key, endpoint, api_version, deployment):
        self.client = AzureOpenAI(api_key=api_key, azure_endpoint=endpoint, api_version=api_version)
        self.deployment = deployment
    # polish_page identical to OpenAIPageMdPolisher but uses self.deployment as the model id
```

Mirror the same shape for `AzureRegionExtractor`. Then in `_build_real_services`, branch on a new env var (`ANCHOR_AZURE_OPENAI_ENDPOINT`) and pick the Azure classes when it's set.

Env vars (proposed, not implemented):

```
ANCHOR_AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
ANCHOR_AZURE_OPENAI_API_KEY=...
ANCHOR_AZURE_OPENAI_API_VERSION=2024-08-01-preview
ANCHOR_AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

Quality is whatever your Azure deployment is — GPT-4o behind Azure is GPT-4o.

### B. Ollama (local)

Ollama exposes an OpenAI-compatible chat completions endpoint at `http://localhost:11434/v1`. Because the OpenAI SDK already accepts `base_url`, the existing `OpenAIPageMdPolisher` and `OpenAIRegionExtractor` accept a `base_url` argument today. So an Ollama backend is one wiring change, not a new infra class:

```python
# in _build_real_services
polisher = OpenAIPageMdPolisher(
    api_key="ollama",                     # any non-empty string
    base_url="http://localhost:11434/v1",
)
```

Env vars (proposed):

```
ANCHOR_OPENAI_BASE_URL=http://localhost:11434/v1
ANCHOR_OPENAI_API_KEY=ollama
ANCHOR_POLISH_MODEL=llava:13b
ANCHOR_REGION_MODEL=llama3.2-vision:11b
```

The model knob matters here. Polish and region extraction both pass `image_url` content blocks. Vision support in Ollama is model-dependent:

- **Works:** `llava` (7B/13B/34B), `llama3.2-vision` (11B/90B), `bakllava`, `moondream`, `minicpm-v`.
- **Does not work** for vision (text-only): `llama3.1`, `qwen2`, `mistral`, plain `llama3`. They will accept the request and silently ignore the image, or error out.

Practical reality on quality: region extraction has to read tiny labels in spec tables on rendered PDF pages at 150 DPI. GPT-4o reads them well. LLaVA-7B will produce structurally plausible output but often hallucinates values or misses rows. LLaVA-34B and llama3.2-vision-90B are closer but slower and need a lot of VRAM. If you're using local vision for compliance, you're trading accuracy for sovereignty — measure it on your own PDFs before deciding it's good enough.

### C. Local vLLM / LM Studio / llama.cpp server

All three expose OpenAI-compatible endpoints. Same single-line swap as Ollama:

```python
polisher = OpenAIPageMdPolisher(api_key="dummy", base_url="http://localhost:8000/v1")
```

Env vars (proposed):

```
ANCHOR_OPENAI_BASE_URL=http://localhost:8000/v1
ANCHOR_OPENAI_API_KEY=dummy
ANCHOR_POLISH_MODEL=qwen2-vl-7b-instruct        # whatever you've loaded
ANCHOR_REGION_MODEL=qwen2-vl-7b-instruct
```

vLLM with `Qwen2-VL-7B` or `InternVL2-8B` is currently the strongest open-weights vision-language combination for document understanding. Still not GPT-4o, but in the right ballpark for spec tables.

### What's not yet wired up

A small lift to fully enable the above:

- `AnchorConfig` doesn't expose `openai_base_url`, `openai_endpoint_type`, or Azure-specific knobs. They're easy to add (Pydantic Settings, prefix `ANCHOR_`), and `_build_real_services` then branches on them.
- The polisher and extractor classes accept `base_url` but `_build_real_services` doesn't pass one. So the user can write a one-line monkey-patch today, or wait for the config plumb-through.
- No `local-vision` extras group in `pyproject.toml` (the way there's a `local-embed` group). If you go local-vision you bring your own runtime — Ollama, vLLM, LM Studio — installed outside Anchor.

---

## 5. Open gaps for full local-air-gap mode

Where Anchor stands today on full air-gap operation, by step:

| Step | Today | Air-gap path |
|---|---|---|
| PDF → bronze | Local (`pymupdf` + filesystem) | Already air-gap. |
| Bronze → silver (Docling) | Local. Docling runs CPU-only by default, optional GPU. | Already air-gap. |
| Silver → polished markdown | OpenAI vision LLM | Swap to Azure / Ollama / vLLM via `base_url` (see section 4). Not wired through config yet. |
| Silver → gold regions | OpenAI vision LLM | Same swap as above. Quality drop on small open models is real. |
| Region → embedding | Local sentence-transformers (default) or OpenAI | Already air-gap with the local extra. |
| Workspace state | Local (`canvases/<slug>/state.json` + `events.jsonl`) | Already air-gap. |
| HTTP / SSE / MCP-stdio | All local | Already air-gap. |
| Canvas snapshot | Local (headless Chromium against local `anchor serve`) | Already air-gap. |
| Agent harness | External (Claude Code / Cursor talk to Anthropic's API) | Out of Anchor's scope. Use a local-model harness (Ollama-coder, Aider-with-local-LLM, opencode with a self-hosted gateway) if the agent itself must also be air-gap. |

The honest summary: Anchor's substrate is already local-first. Two pipeline steps still default to OpenAI, both behind ports, both swappable with a single-file infra implementation. Adding Azure + a `base_url` env var to the existing OpenAI classes closes most of the gap. Quality of local vision models is the unsolved practical problem, not Anchor's wiring.

A reasonable order of work to get to a clean air-gap mode:

1. **`ANCHOR_OPENAI_BASE_URL` config knob.** Five-line change in `infra/config.py` plus pass-through in `_build_real_services`. Unlocks Ollama / vLLM / LM Studio with zero new code.
2. **`AzurePageMdPolisher` + `AzureRegionExtractor` infra classes.** Two new files, one branch in `_build_real_services`. Unlocks enterprise OpenAI.
3. **`pyproject.toml` extras group `local-vision`** that pins a recommended vision model wrapper (none today, but room for one).
4. **A small note in the SKILL telling the agent to call `list_documents()` first and surface "gold missing"** when the polish backend was unavailable, so the user knows ingest ran in degraded mode.

Until all four land, the user-facing rule is: ingest produces a useful silver layer with no API key; gold is best-effort and depends on which backend you wire in.

---

## Where to look in the code

- Harness installer: `v2/src/anchor/adapters/cli/install.py`
- MCP stdio entry: `v2/src/anchor/adapters/mcp/stdio_main.py`
- MCP canvas handlers: `v2/src/anchor/adapters/mcp/handlers_canvas.py`
- Snapshot service: `v2/src/anchor/core/services/workspace_service.py` (search `def snapshot`)
- Snapshot port + impl: `v2/src/anchor/infra/snapshot/headless_chromium_snapshotter.py`
- OpenAI polish: `v2/src/anchor/extensions/anchor_pdfs/infra/llm/openai_md_polisher.py`
- OpenAI region extract: `v2/src/anchor/extensions/anchor_pdfs/infra/llm/openai_region_extractor.py`
- Local embedder: `v2/src/anchor/extensions/anchor_pdfs/infra/llm/local_sentence_transformer_embedder.py`
- Wiring: `v2/src/anchor/adapters/cli/main.py:_build_real_services`
- Config: `v2/src/anchor/infra/config.py`
