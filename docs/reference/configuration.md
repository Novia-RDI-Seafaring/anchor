# Configuration

ANCHOR uses command-line flags for server location and data-directory
selection. Environment variables configure optional extraction and local
runtime behavior.

## Command-line settings

| Setting | Default | Description |
| --- | --- | --- |
| `--data-dir DIR` | `~/anchor-data` | Storage root for documents, canvases and snapshots. |
| `--host HOST` | `127.0.0.1` | HTTP bind address for `anchor serve` and `anchor demo`. |
| `--port PORT` | `8002` | HTTP port for `anchor serve` and `anchor demo`. |

Use loopback unless you provide authentication and TLS through your own
deployment layer.

## Supported environment variables

| Variable | Purpose |
| --- | --- |
| `ANCHOR_DATA_DIR` | Default storage root for CLI and MCP commands. An explicit `--data-dir` takes priority. |
| `ANCHOR_OPENAI_API_KEY` | Credential for an OpenAI-compatible endpoint used by LLM-backed extraction. |
| `ANCHOR_OPENAI_BASE_URL` | OpenAI-compatible endpoint base URL, including local services. |
| `ANCHOR_POLISH_MODEL` | Vision-capable model used for markdown polishing. |
| `ANCHOR_REGION_MODEL` | Vision-capable model used for region extraction. |
| `ANCHOR_EMBED_MODEL` | Local embedding model identifier. |
| `ANCHOR_DPI` | PDF rendering DPI for silver pages and region crops. |
| `ANCHOR_CORS_ORIGINS` | Additional browser origins allowed by the HTTP server. |
| `ANCHOR_FMU_DEMO` | Enables synthetic FMU demo behavior when explicitly set. |

Copy [`.env.example`](https://github.com/Novia-RDI-Seafaring/anchor/blob/main/.env.example)
to `.env` in the directory where you launch ANCHOR and set only the values
you need.

## Example: OpenAI-compatible extraction

```bash
ANCHOR_OPENAI_API_KEY=<your-key>
ANCHOR_OPENAI_BASE_URL=https://api.openai.com/v1
ANCHOR_POLISH_MODEL=<vision-capable-model>
ANCHOR_REGION_MODEL=<vision-capable-model>
```

Without these LLM settings, local document storage, page rendering and canvas
operations continue to work; gold-region extraction is not available.
