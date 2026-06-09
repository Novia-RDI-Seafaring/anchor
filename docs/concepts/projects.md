# Projects

A **project** is a folder with an `anchor.toml` in it. That one file makes the
folder self-describing: it records the data directory, the AI provider (and so
the data zone), and the models. Every ANCHOR adapter — the `anchor` CLI,
`anchor serve`, and an agent-launched `anchor-mcp` — resolves the project from
that file, so you configure once and run from inside the folder.

## Create one with `anchor init`

```bash
cd ~/my-project
anchor init
```

`anchor init` asks the question that matters first — **where may document
content go?** — and writes a non-secret `anchor.toml`. The choice of provider
is the choice of data zone:

| Provider | Data zone |
| --- | --- |
| `local` | on-host; nothing leaves the network (bronze/silver + local search; no gold regions) |
| `ollama` | your machine / LAN; no internet egress, with offline gold regions via a local vision model |
| `openai` | public cloud |
| `azure` | your Azure tenant / region |
| `custom` | any OpenAI-compatible endpoint; you label the zone |

It then picks the embedding model and the data directory (default
`<project>/anchor-data`), and prints the next steps. The API key is **never**
written to `anchor.toml` — keep it in `ANCHOR_OPENAI_API_KEY` or a gitignored
`.env` so a committed config carries no secret.

## How adapters find the project

`anchor.toml` is discovered by **walking up from the working directory**, or by
an explicit `ANCHOR_CONFIG` path. So:

- **CLI / server** — run `anchor ingest`, `anchor serve`, etc. from inside the
  folder (or a subfolder) and they use the project automatically. No repeated
  `--data-dir`.
- **MCP / agents** — `anchor-mcp` resolves the project from the directory the
  agent launches it in. Name one explicitly with `anchor-mcp --project <folder>`.

Because resolution happens at runtime, you register the MCP server **once**
(`anchor install claude-code`, with no baked data dir) and it serves every
project: open the agent in a project folder and its tools target that project.
No reinstall when you switch projects.

```json
{ "mcpServers": { "anchor": {
    "type": "stdio", "command": "anchor-mcp"
} } }
```

## Configuration precedence

Highest priority first:

1. Explicit flags / constructor args (e.g. `--data-dir`)
2. `ANCHOR_*` environment variables
3. A `.env` file
4. The project `anchor.toml`
5. Built-in defaults (data dir `~/anchor-data`, embeddings `bge-small`, …)

So an operator's `ANCHOR_*` override always wins over a committed project
default, and a malformed `anchor.toml` is ignored with a warning rather than
crashing the CLI.

## Data zones and egress

The provider you pick governs what leaves the host:

- **`local` / `ollama`** keep document content on your machine or LAN.
- **`openai`** sends page images and extracted text to OpenAI.
- **`azure` / `custom`** send the same content only to the endpoint you name.

Embeddings stay **local** (`bge-small`) by default, so text never leaves the
host even when the vision model is remote; choosing a `text-embedding-*` model
opts those vectors into the endpoint.

See [Configuration](../reference/configuration.md) for the full key reference
and [Agent setup](../guides/agent-setup.md) for connecting a harness.
