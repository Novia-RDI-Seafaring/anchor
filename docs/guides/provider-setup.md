# Choose a provider and enable gold

Choose a provider before uploading a document. The provider is not just a
model setting. It is the environment's data boundary: it decides whether PDF
pages stay on the computer, go to an agent harness, or go to a configured
model endpoint.

If this is your first ANCHOR environment, start here. Do not add an API key and
assume ANCHOR will work out the rest. A key is only a credential. It does not
choose a provider or authorize document egress.

## 1. Choose where document pages may go

| Provider | Gold regions | Where page content goes | Key needed | Use it when |
| --- | --- | --- | --- | --- |
| `local` | No | Stays on this computer | No | The document must not be sent to an LLM or external model endpoint. Bronze and silver are enough. |
| `ollama` | Yes | Your Ollama server, normally this computer or your LAN | No | You need gold while keeping extraction on infrastructure you control. |
| `harness` | Yes | The connected agent harness reads every page | No ANCHOR key | The harness and its model provider are approved for the document. |
| `openai` | Yes | OpenAI | Yes | Public OpenAI processing is approved. |
| `azure` | Yes | The Azure OpenAI endpoint you specify | Yes | Processing in your Azure tenant is approved. |
| `custom` | Yes | The OpenAI-compatible endpoint you specify | Yes | You operate or approve that endpoint. |

!!! danger "Restricted documents"
    Do not choose `harness`, `openai`, `azure`, or `custom` until the receiving
    service is approved for the document. `harness` does not create an ANCHOR
    model client, but it still gives page content to the connected agent. For
    local gold, use `ollama` with an endpoint you control.

## 2. Understand the four files

For an environment named `private-gold` and its default managed project,
ANCHOR uses these locations:

```text
~/.anchor/envs/private-gold/
  env.toml                         non-secret provider and model settings
  .env                             optional endpoint credential only
  projects.toml                    project registry
  projects/default/
    anchor.toml                    project name and environment binding
    .anchor_data/                  bronze, silver, gold, and canvases
```

| File | Purpose | Secret? |
| --- | --- | --- |
| `env.toml` | Selects the provider, endpoint, models, and data zone. Created by `anchor env create`. | No |
| Environment `.env` | Holds `ANCHOR_OPENAI_API_KEY` for a keyed endpoint. It does not select the provider. | Yes; never commit it |
| Project `anchor.toml` | Binds one project folder to an environment. It cannot redirect the provider or endpoint. | No |
| `.anchor_data/` | Stores the project's documents and canvases. | Treat it as document data |

The supported `.env` location is:

```text
~/.anchor/envs/<environment-name>/.env
```

It is not the repository root and it is not the managed project's
`.anchor_data/` folder. ANCHOR loads this file only when the corresponding
environment has a valid `env.toml`. This is deliberate: an orphan key file
must not silently create a provider or enable network access.

## 3. Understand `ANCHOR_OPENAI_API_KEY`

The variable name describes the OpenAI-compatible client protocol. It does
not mean every configured endpoint is OpenAI. The provider and endpoint in
`env.toml` determine the destination.

| Environment state | What ANCHOR does with the key |
| --- | --- |
| No `env.toml` or no provider | Ignores the key for model calls and fails closed. Gold is skipped. |
| `provider = "local"` | Ignores the key. No model client is created. |
| `provider = "ollama"` | Does not require a user key. ANCHOR uses a local placeholder required by the client library. |
| `provider = "harness"` | Ignores the key. The agent performs the vision work. |
| `provider = "openai"` | Uses `ANCHOR_OPENAI_API_KEY`. A process-level `OPENAI_API_KEY` is also accepted only for public OpenAI with no custom base URL. |
| `provider = "azure"` or `"custom"` | Requires `ANCHOR_OPENAI_API_KEY` for the selected endpoint. An ambient `OPENAI_API_KEY` is not used. |

For predictable, environment-scoped configuration, always use this form in
the selected environment's `.env`:

```dotenv
ANCHOR_OPENAI_API_KEY=<credential-for-this-environment>
```

Do not put `OPENAI_API_KEY=...` in the environment's `.env`. The scoped loader
imports only `ANCHOR_` names, so a bare `OPENAI_API_KEY` in that file is
ignored. Also do not put API keys in `env.toml` or `anchor.toml`.

## 4. Create the environment

Choose one recipe. Environment names are labels; use names that make the data
boundary obvious.

!!! tip "Interactive setup versus `--yes`"
    For `openai`, `azure`, and `custom`, omit `--yes` when a person is running
    the command. ANCHOR then asks for the endpoint key with hidden input and
    saves it to `~/.anchor/envs/<name>/.env`. This is the simplest setup.

    `--yes` means no prompts. It creates the non-secret `env.toml` but does not
    ask for or save a key. Use it for automation only, then create the
    environment `.env` separately. Never put the key directly in a command-line
    argument because shell history may retain it.

### Local, no model and no gold

```bash
anchor env create private-silver --provider local --yes
anchor check --env private-silver
```

This produces bronze and silver. Gold extraction is intentionally disabled.
Because semantic vectors are currently derived from gold regions, a
silver-only document also has zero region embeddings. Page text and rendered
pages remain available.

### Local gold with Ollama

First start Ollama, or another local service exposed through Ollama's
OpenAI-compatible endpoint, and make a vision-capable model available. Then:

```bash
anchor env create private-gold --provider ollama \
  --base-url http://localhost:11434/v1 \
  --vision-model llava --yes
anchor check --env private-gold --probe
```

Ollama does not need `ANCHOR_OPENAI_API_KEY`. The probe checks the configured
local endpoint without sending a document.

### Gold through an agent harness

```bash
anchor env create agent-gold --provider harness --yes
anchor check --env agent-gold
anchor install codex --env agent-gold
```

Restart the harness after installation. During ingest, the harness reads the
page work items and submits grounded regions back to ANCHOR. The harness's own
provider and retention policy decide where those pages may go.

### Gold with public OpenAI

```bash
anchor env create cloud-openai --provider openai \
  --vision-model gpt-5.4
```

Enter the OpenAI key at the hidden prompt. ANCHOR saves it to
`~/.anchor/envs/cloud-openai/.env`.

For non-interactive setup, add `--yes` to the command and then create the
credential file yourself. Add the credential to the environment, not the
project:

=== "PowerShell"

    ```powershell
    $envFile = Join-Path $HOME ".anchor\envs\cloud-openai\.env"
    Add-Content -LiteralPath $envFile -Value "ANCHOR_OPENAI_API_KEY=<your-key>"
    ```

=== "bash"

    ```bash
    printf '%s\n' 'ANCHOR_OPENAI_API_KEY=<your-key>' \
      >> ~/.anchor/envs/cloud-openai/.env
    ```

Then verify the endpoint before uploading:

```bash
anchor check --env cloud-openai --probe
```

### Gold with Azure OpenAI

Use the Azure OpenAI v1 base URL and a vision-capable deployment name:

```bash
anchor env create work-azure --provider azure \
  --base-url https://<resource>.openai.azure.com/openai/v1/ \
  --vision-model <deployment-name>
```

Enter the Azure resource key at the hidden prompt. For non-interactive setup,
add `--yes`, then add `ANCHOR_OPENAI_API_KEY=<azure-resource-key>` to
`~/.anchor/envs/work-azure/.env`. Verify the result:

```bash
anchor check --env work-azure --probe
```

For Azure-specific validation, see
[Azure OpenAI test-drive](azure-test-drive.md).

## 5. Start or restart the server

The server resolves its provider when it starts. If `anchor serve` is already
running, stop it with `Ctrl+C` and start it again after creating or changing an
environment:

```bash
anchor serve --env <environment-name> --project default
```

Example:

```bash
anchor serve --env private-gold --project default
```

Do not assume the browser changed environments because an `env.toml` or `.env`
file changed on disk. Restart the server and confirm the environment shown by:

```bash
anchor check --env private-gold
```

## 6. Reingest documents that are already silver-only

Gold is created during ingestion. ANCHOR does not automatically backfill an
existing silver-only document after you configure a vision provider.

Select the environment and reingest the original PDF:

```bash
anchor use private-gold default
anchor ingest "/path/to/document.pdf" --force
```

On Windows PowerShell:

```powershell
anchor use private-gold default
anchor ingest "C:\path\to\document.pdf" --force
```

`--force` recomputes the document and overwrites derived artifacts for the
same slug. With a paid endpoint, this repeats billable model calls.

You can also restart the correctly configured server and upload the document
again in the browser. The CLI route is clearer for recovery because it reports
the ingestion result directly.

## 7. Verify that gold exists

```bash
anchor list
anchor gold-map <document-slug>
```

A completed gold extraction reports:

```json
{
  "has_gold": true,
  "region_count": 1
}
```

`region_count` can be greater than `1`; it must not be assumed from the
example. If `has_gold` is `false`, run:

```bash
anchor env list
anchor check --env <environment-name>
```

Check these items in order:

1. The environment exists and has the provider you intended.
2. `anchor check` shows the correct data zone and endpoint.
3. A keyed provider reports `ANCHOR_OPENAI_API_KEY` as present.
4. Ollama is running and the configured vision model is available.
5. The server was restarted after the environment changed.
6. The document was reingested after gold was enabled.
