# Environments and projects

Anchor has two levels.

An **environment** is a named configuration profile: the AI provider, the
models, and the data **zone**. It is the trust and egress boundary. It decides
where a corpus's content may go. Environments live under `~/.anchor/envs/<name>/`.

A **project** is one corpus (its ingested documents) plus its canvases. A
project is contained inside one environment at
`~/.anchor/envs/<name>/projects/<project>/` and inherits the environment's
configuration.

Define an environment once and reuse it across many projects. Change the
endpoint in one place and every project on that environment follows. This is
the `nvm` model (named, listable, picked by name), and the environment also
behaves like an Azure subscription: projects live inside it, inherit its zone,
and moving one out is a deliberate act.

For the full command reference, see
[Environments and projects](../guides/environments-and-projects.md).

## Create one with `anchor init`

```bash
anchor init local               # create an environment named "local"
anchor init work --provider azure --base-url … --vision-model …
```

`anchor init` asks the question that matters first, **where may document
content go?**, and writes a non-secret `env.toml`. The provider is the zone:

| Provider | Data zone |
| --- | --- |
| `local` | on-host; nothing leaves the network (bronze/silver + local search; no gold regions) |
| `ollama` | your machine / LAN; no internet egress, with offline gold regions via a local vision model |
| `openai` | public cloud |
| `azure` | your Azure tenant / region |
| `custom` | any OpenAI-compatible endpoint; you label the zone |

It scaffolds the environment's `default` project and prints the next steps. The
API key is **never** written to the profile. Keep it in `ANCHOR_OPENAI_API_KEY`
or a gitignored `.env` next to the profile.

## How adapters resolve

Selection is by name, not by working directory:

```
env name : --env  >  ANCHOR_ENV  >  anchor use  >  the default environment
project  : --project  >  ANCHOR_PROJECT  >  anchor use  >  "default"
```

- **CLI / server** read `--env` / `--project`, the `anchor use` session
  selection, or the defaults.
- **MCP / agents** pin one environment per server (`anchor-mcp --env <name>`)
  and pass the `project` per call. Two environments are two named servers, so
  an agent never crosses a zone by accident.

```json
{ "mcpServers": {
    "anchor":      { "command": "anchor-mcp", "args": ["--env", "local"] },
    "anchor-work": { "command": "anchor-mcp", "args": ["--env", "azure-work"] }
}}
```

## Configuration precedence

Highest priority first:

1. Explicit flags / constructor args
2. `ANCHOR_*` environment variables
3. A `.env` file (next to the environment profile)
4. The project `project.toml`
5. The environment `env.toml`
6. Built-in defaults

So an operator's `ANCHOR_*` override always wins over a committed default, and a
malformed config is ignored with a warning rather than crashing the CLI.
Storage location is structural (the project directory), not a setting, so
`ANCHOR_DATA_DIR` does not move a project.

## Data zones and egress

The provider you pick governs what leaves the host:

- **`local` / `ollama`** keep document content on your machine or LAN.
- **`openai`** sends page images and extracted text to OpenAI.
- **`azure` / `custom`** send the same content only to the endpoint you name.

Embeddings stay **local** (`bge-small`) by default, so text never leaves the
host even when the vision model is remote. Choosing a `text-embedding-*` model
opts those vectors into the endpoint.

See [Configuration](../reference/configuration.md) for the full key reference
and [Agent setup](../guides/agent-setup.md) for connecting a harness.
