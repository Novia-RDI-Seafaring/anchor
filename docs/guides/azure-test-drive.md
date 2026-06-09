# Test-drive ANCHOR with Azure OpenAI

This is the fastest safe path to running ANCHOR against a private **Azure
OpenAI** endpoint, so your documents are structured inside your own Azure tenant
and never touch public OpenAI. Every step is verifiable before you ingest
anything sensitive.

## What stays local, what leaves

With the Azure provider and the default **local** embedding model:

- **Never leaves the host:** the raw PDFs (`bronze/`), per-page text and PNGs
  (`silver/`), the structured regions (`gold/`), and the embedding vectors.
- **Sent only to your Azure endpoint:** rendered page images + text, for the
  gold region-extraction and polish stages.

If you pick a **remote** embedding model (`text-embedding-3-small/large`), page
text is also sent to your Azure endpoint for embeddings. Keep the default
`bge-small` (local) to avoid that.

## Prerequisite — create and note your deployment(s)

ANCHOR calls Azure by **deployment name**, not model name. Before configuring
it:

1. In the Azure AI Foundry portal, deploy a vision-capable chat model (for
   example `gpt-4o`). Copy the **deployment name** you chose — it may differ
   from the model name.
2. If (and only if) you want remote embeddings, also deploy
   `text-embedding-3-small` and copy that deployment name.
3. Note your resource endpoint: `https://<resource>.openai.azure.com/`.

The deployment name is what you give ANCHOR as the model. If it does not exist,
the first ingest fails with a deployment-not-found error — `anchor check
--probe` (below) catches that up front.

## 1. Install

```bash
uv tool install anchor-kb
anchor install claude-code      # register the MCP once (folder-resolving)
```

## 2. Configure the project folder

```bash
cd ~/my-azure-project
anchor init                     # interactive
```

Choose **Azure OpenAI**, paste your resource endpoint, and give your **vision
deployment name** as the model. Keep the embedding default (`bge-small`, local)
unless you deployed an embeddings model. `anchor init`:

- appends `/openai/v1/` if you pasted the bare resource URL,
- offers to save your API key to a gitignored `.env` (never the `anchor.toml`),
- prints exactly what to do next.

The endpoint ANCHOR uses is Azure's OpenAI-compatible **v1 surface**
(`https://<resource>.openai.azure.com/openai/v1/`), with the key passed as the
client's `api_key`. This is Microsoft's documented pattern for the v1 API.

## 3. Provide the key (kept out of the committed config)

If `init` did not capture it:

```bash
echo 'ANCHOR_OPENAI_API_KEY=<your-azure-key>' >> .env
```

A personal `OPENAI_API_KEY` in your shell is **not** the right credential for
Azure and is ignored for a named endpoint — use `ANCHOR_OPENAI_API_KEY`.

## 4. Verify before ingesting

```bash
anchor check            # offline: data zone, endpoint shape, key present?
anchor check --probe    # one tiny call: confirms the deployment + key work
```

`--probe` sends a one-token prompt (no document content) to confirm the chat
deployment (and the embedding deployment, if remote) resolve and authenticate.
`anchor check` exits non-zero when something would break, so you can trust a
clean run before sending real documents.

## 5. Ingest and open the canvas

```bash
anchor ingest path/to/datasheet.pdf
anchor serve                    # open the printed http://127.0.0.1:PORT
```

If `anchor serve` reports a different port than expected, another server already
holds the default — open the URL it prints, not a remembered one.

## 6. Drive it from an agent

Open your agent (Claude Code, Cursor, …) **in the project folder**. The
`anchor-mcp` server inherits that folder and resolves this project, so the agent
reads and writes the same knowledge base. No per-project reinstall.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `DeploymentNotFound` / 404 on ingest | model name ≠ a real deployment | use the deployment name; re-run `anchor check --probe` |
| 401 / auth error | wrong or missing key | set `ANCHOR_OPENAI_API_KEY` (not `OPENAI_API_KEY`) |
| calls hit `api.openai.com` | endpoint not set | `anchor check` shows the resolved endpoint; re-run `anchor init` |
| endpoint 404 on every call | missing `/openai/v1/` | `anchor check --fix` |
