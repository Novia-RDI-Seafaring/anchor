# Environments and projects

Anchor has two levels.

An **environment** is a named configuration profile: the AI provider, the
models, and the data **zone**. It is the trust and egress boundary. It decides
where a corpus's content may go. Environments live under `~/.anchor/envs/<name>/`,
with their config in `env.toml`. An environment is **not** a `.env` dotfile of
secrets; see [Environment vs `.env`](../guides/environments-and-projects.md#environment-vs-env).

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
| `local` | on-host; nothing leaves the network (bronze/silver; no gold regions or region embeddings) |
| `ollama` | your machine / LAN; no internet egress, with offline gold regions via a local vision model |
| `harness` | the connected agent reads pages; its provider policy controls any further egress |
| `openai` | public cloud |
| `azure` | your Azure tenant / region |
| `custom` | any OpenAI-compatible endpoint; you label the zone |

It scaffolds the environment's `default` project and prints the next steps. The
API key is **never** written to the profile. Keep it in `ANCHOR_OPENAI_API_KEY`
or a gitignored `.env` next to the profile. The key file does not choose a
provider and is not loaded until the environment has a valid `env.toml`.

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

## Configuration and selection

Project selection and model policy have different rules. A CLI command can
resolve a working folder's marker, explicit selectors, process selectors, or
the saved CLI session default. MCP is pinned to its named environment and uses
a per-call project or `open_project` session selection. `anchor use` does not
change the MCP session.

The environment owns provider, endpoint, and local-only policy. A project may
override permitted non-security settings, but it cannot redirect that policy.
Process variables cannot silently retarget a named environment either.
Credentials are scoped to the selected environment; its `.env` is not a second
provider profile. See [Configuration](../reference/configuration.md).

Storage normally follows the project folder's `.anchor_data/`. A raw
`--data-dir` override is available on commands that expose that flag; it is
separate from normal named project selection.

## Data zones and egress

The provider you pick governs what leaves the host:

- **`local`** runs ANCHOR extraction on this computer with cached models.
- **`ollama`** sends model input to the configured Ollama endpoint.
- **`harness`** returns page work items to your connected agent.
- **`openai`** sends page images and extracted text to OpenAI.
- **`azure` / `custom`** send the same content only to the endpoint you name.

Region embeddings use a local model by default. Choosing an allowed
`text-embedding-*` model sends embedding input text to the configured
endpoint. Vision stages and the external harness have separate content
disclosure paths; local embeddings do not make those stages local.

See [Choose a provider and enable gold](../guides/provider-setup.md) for the
setup and recovery workflow, [Configuration](../reference/configuration.md)
for the full key reference, and [Agent setup](../guides/agent-setup.md) for
connecting a harness.
