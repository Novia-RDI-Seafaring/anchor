# Quickstart

From nothing to a source-grounded value in about five minutes. No API key.

This is the opinionated path. It uses the `harness` provider, so your agent
reads the PDF pages and ANCHOR keeps every byte on your machine. When you want
server-side extraction later, [step 6](#6-optional-server-side-gold-with-openai)
adds it.

## 1. Install

```bash
uv tool install anchor-kb
```

You now have two commands on your PATH: `anchor` (the CLI) and `anchor-mcp`
(the MCP server your harness talks to). The wheel bundles the web UI, so no
Node toolchain is needed to run it.

Requires Python 3.12+. `pipx install anchor-kb` and `pip install anchor-kb`
also work. Installing from a git checkout needs an extra build step; see
[Install](installation.md).

## 2. Pick an environment

An **environment** is a named trust boundary: it decides where your document
content may go. You pick a provider once, and that choice is the environment's
data zone.

| Provider | What extracts gold regions | Data leaves your machine? | Key needed? |
|---|---|---|---|
| `harness` | Your agent reads pages, ANCHOR embeds locally | No | No |
| `local` | Nothing (silver only: page text + search) | No | No |
| `openai` | OpenAI vision, server-side | Yes (to OpenAI) | Yes |
| `azure` | Azure OpenAI vision, server-side | Yes (to your Azure) | Yes |
| `ollama` | A local vision model you run | No | No |

Start with `harness`. It produces gold regions (structured values with page +
bbox provenance) with no key and no new egress:

```bash
anchor env create home --provider harness --yes
```

This creates an environment named `home`. Gold regions still come out, because
your agent does the reading. ANCHOR embeds them locally with a bundled model.

## 3. Wire ANCHOR into your harness

Point your agent at the environment. Each install writes one named MCP server,
so the entry name tells you which environment it serves.

=== "Claude Desktop"

    ```bash
    anchor install claude-desktop --env home
    ```

=== "Claude Code"

    ```bash
    anchor install claude-code --env home
    ```

=== "Cursor"

    ```bash
    anchor install cursor --env home
    ```

Restart the harness. In Claude Code or Cursor, `/mcp` should now list `anchor`
with its tools. For Codex, OpenCode, and generic stdio clients, see
[Agent configuration](../guides/agent-configuration.md).

## 4. Ingest a PDF, no key

Drag a PDF into your harness chat, or point it at a file, and ask it to ingest.
On the `harness` provider the agent runs the page-by-page session itself:
`ingest_begin` -> `ingest_get_page` -> `ingest_submit_page` (once per page) ->
`ingest_finalize`. The agent reads each page; ANCHOR computes the region boxes
and embeds them locally on finalize. Nothing is sent to a cloud model.

> Ingest the PDF at ~/Downloads/lkh-pump.pdf into ANCHOR, then tell me the
> max inlet pressure with its source page.

When it finishes you have bronze (the raw PDF), silver (per-page text and
images), and gold (structured regions with page + bbox), all on disk under the
project's `.anchor_data/`.

## 5. See the grounding

Start the canvas server and open a document:

```bash
anchor serve            # http://127.0.0.1:8002
```

Open a spec value in the viewer and it points back to its exact page and
region. That link, value to page to bbox, is the whole contract: if a value
has no source ref, treat it as ungrounded.

Confirm the environment resolved the way you expect at any time:

```bash
anchor check --env home
```

It prints the data zone, the provider, and whether a key is present.

## 6. Optional: server-side gold with OpenAI

Prefer ANCHOR to do the extraction with a cloud vision model instead of your
agent? Create an `openai` environment and give it a key. The key lives in the
environment's gitignored `.env`, and it must use the `ANCHOR_` name:

```bash
anchor env create cloud --provider openai --yes
echo 'ANCHOR_OPENAI_API_KEY=sk-...' >> ~/.anchor/envs/cloud/.env
anchor check --env cloud --probe
```

`--probe` makes one tiny live call to confirm the key and endpoint work. Then
ingest through the built-in path (`anchor ingest file.pdf`, canvas drag-drop,
or MCP `ingest_pdf`) and ANCHOR extracts gold server-side.

For Azure OpenAI, the base URL and deployment-name specifics are in the
[Azure OpenAI test-drive](../guides/azure-test-drive.md).

## Troubleshooting

**Ingest finished but there are 0 gold regions or no embeddings.**
The environment has no vision provider or no key. Two fixes:

- Use the no-key path: switch to a `harness` environment and let the agent do
  the reading (steps 2 to 4). This is the recommended default.
- Or configure a keyed provider: `openai` / `azure`, with the key in
  `~/.anchor/envs/<name>/.env` named `ANCHOR_OPENAI_API_KEY` (not a bare
  `OPENAI_API_KEY`).

Run `anchor check --env <name> --probe` to see which one you are missing.

**`/mcp` does not list `anchor`.**
Restart the harness fully (quit and reopen, not just close the window). MCP
servers load on startup.

**Port 8002 is taken.**
Pass `anchor serve --port 8003`. If you use canvas snapshots, add a matching
`--base-url http://localhost:8003` to the installed `anchor-mcp` arguments.

## Next steps

- [First-day tutorial](tutorial.md): the `anchor demo` canvas and the
  "agent fills the placeholders" flow.
- [Environments and projects](../guides/environments-and-projects.md): the full
  trust-boundary and project model.
- [Many interfaces](../concepts/interfaces.md): why CLI, MCP, and HTTP are
  peers, not one wrapping another.
