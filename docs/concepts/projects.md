# Environments and projects

Anchor has two levels.

An **environment** is a named configuration profile: the AI provider, the
models, and the data **zone**. It is the trust and egress boundary. It decides
where a corpus's content may go. Environments live under `~/.anchor/envs/<name>/`.

A **project** is one corpus (its ingested documents) plus its canvases. A
project is a *folder*. It carries an `anchor.toml` marker that binds it to an
environment, and keeps its corpus in a hidden `.anchor_data/` subfolder. It is
registered by name in its environment's `projects.toml`. A project inherits the
environment's configuration.

Define an environment once and reuse it across many projects. Change the
endpoint in one place and every project on that environment follows. This is
the `nvm` model (named, listable, picked by name), and the environment also
behaves like an Azure subscription: projects live inside it, inherit its zone,
and moving one out is a deliberate act.

For the full command reference, see
[Environments and projects](../guides/environments-and-projects.md).

## `anchor env create` vs `anchor init`

Two commands set things up. `anchor env create` makes an environment. `anchor
init` makes a project.

```bash
anchor env create local         # create an environment named "local" + its default project
anchor env create work --provider azure --base-url … --vision-model …
```

`anchor env create` is the provider and data-zone picker. It asks the question
that matters first, **where may document content go?**, and writes a non-secret
`env.toml`. The provider is the zone:

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

`anchor init` runs inside a working folder and starts a project there. With no
name it uses the folder's basename. It binds to an environment via `--env
<name>`, defaulting to the default env. It drops an `anchor.toml` marker and a
hidden `.anchor_data/`, then registers the project by name. If the target
environment does not exist yet, init prompts you to pick a provider (or you pass
`--provider`); it never invents a trust boundary silently.

```bash
cd ~/work/pumps
anchor init                     # project "pumps" here, bound to the default env
anchor init --env work --description "LKH pump datasheets"
```

## Two homes for a project

A project lives in one of two places, registered the same way either way.

A human runs `anchor init` in a working folder and the project lives there.

An agent (or `anchor project create`) has no working folder, so its project is
*managed* under `~/.anchor/envs/<env>/projects/<name>/`.

Both keep the corpus in `.anchor_data/`, and the env's `projects.toml` maps the
name to the folder.

## On disk

A project is a folder with an `anchor.toml` marker and a hidden `.anchor_data/`
holding its corpus. The environment keeps a `projects.toml` registry mapping
each project name to its folder.

```
~/.anchor/envs/<env>/
├── env.toml                     # the profile: provider, models, zone
├── .env                         # gitignored API key
├── projects.toml                # registry: project name -> folder path
└── projects/                    # managed projects (agent/CLI created)
    └── <project>/
        ├── anchor.toml          # marker: env, name, [meta], rare overrides
        └── .anchor_data/
            ├── bronze/ silver/ gold/
            └── canvases/<slug>/

~/work/pumps/                    # a project created with `anchor init` here
├── anchor.toml                  # env = "<env>", name = "pumps", [meta]
└── .anchor_data/
    ├── bronze/ silver/ gold/
    └── canvases/<slug>/
```

## How adapters resolve

Inside a project folder, selection is automatic. Otherwise it is by name:

```
project marker : run inside a project folder -> its anchor.toml (corpus + env)
env name       : --env  >  ANCHOR_ENV  >  anchor use  >  the default environment
project        : --project  >  ANCHOR_PROJECT  >  anchor use  >  "default"
```

- **CLI / server** walk up from the current folder to the nearest `anchor.toml`
  and resolve that project with no flags. Otherwise they read `--env` /
  `--project`, the `anchor use` session selection, or the defaults.
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
4. The project `anchor.toml` marker
5. The environment `env.toml`
6. Built-in defaults

A project usually has no overrides and inherits the environment. It overrides a
value by adding it to its own `anchor.toml` marker, alongside the `env` and
`name` keys. So an operator's `ANCHOR_*` override always wins over a committed
default, and a malformed config is ignored with a warning rather than crashing
the CLI. Storage is structural (the project folder's `.anchor_data/`), not a
setting. There is no `data_dir` key to keep in sync.

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
