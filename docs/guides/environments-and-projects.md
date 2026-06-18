# Environments and projects

Anchor has two levels: **environments** and **projects**. This page defines
both, shows where things live on disk, and lists the commands.

## Terms

| Term | Definition |
| --- | --- |
| **environment** (env) | A named, reusable configuration profile: the AI provider, the models, and the data **zone**. An environment is the trust and egress boundary. It decides where a corpus's content may go. Environments live under `~/.anchor/envs/<name>/`. |
| **project** | One corpus (its ingested documents) plus its canvases. A project is contained inside one environment and inherits that environment's configuration. |
| **documents** | A project's ingested corpus on disk: the bronze, silver, and gold stages. |
| **canvas** | A board inside a project. |
| **zone** | The data egress and privacy boundary (on-host, public cloud, your tenant). A property of the environment, inherited by its projects. |
| **default environment / default project** | Used when a command names neither. The default environment is recorded in `~/.anchor/default` (falls back to `local`). The default project is `default`. |

Two mental models help. An environment is like an `nvm` version: named,
listable, and selected by name. It also carries a privacy policy, so an
environment is also like an Azure subscription or resource group: resources
(projects) live inside it and inherit its zone, and moving one out is a
deliberate act.

## On disk

```
~/.anchor/
├── default                      # the default environment's name (one line)
├── use.toml                     # optional CLI session selection (env + project)
└── envs/
    └── <env>/
        ├── env.toml             # the profile: provider, models, zone, [meta]
        ├── .env                 # gitignored API key (never the profile)
        └── projects/
            └── <project>/        # documents + canvases, inherits the env config
                ├── project.toml   # optional: metadata and rare overrides
                ├── bronze/ silver/ gold/
                └── canvases/<slug>/
```

The environment's `projects/` directory is the project list. There is no
separate registry. Storage location is structural (the project directory), so
there is no `data_dir` pointer to keep in sync. The API key stays in
`ANCHOR_OPENAI_API_KEY` or the gitignored `.env`, never in the profile.

## Configuration layering

```
built-in defaults  <  env.toml  <  project.toml  <  ANCHOR_* env vars / flags
```

Settings live in the environment's `env.toml`. A project usually has none and
inherits. A project overrides a value by writing its own `project.toml`. The
CLI and the MCP server resolve the same layered config, so `anchor check` can
audit the active provider and zone.

## Selecting an environment and project

```
env name : --env  >  ANCHOR_ENV  >  anchor use  >  the default environment
project  : --project  >  ANCHOR_PROJECT  >  anchor use  >  "default"
```

`anchor use <env> [project]` records a session default so later commands can
omit the flags. It only affects the human CLI. The agent (MCP) path is pinned
per server and is never retargeted by `anchor use`.

## CLI

Environments:

```bash
anchor init local                    # create an environment (provider picker) + default project
anchor init work --provider azure …  # create a named environment
anchor env create work --provider …  # same as `anchor init work`
anchor env list                      # name, zone, description (* marks the default)
anchor env show work                 # the profile and its projects
anchor env default work              # set the default environment
anchor use work pumps                # session default env + project
```

Projects:

```bash
anchor project create pumps --env work --description "LKH pump datasheets"
anchor project list --env work
anchor project set-description pumps "Centrifugal pump family" --env work
anchor project move pumps --to local --env work     # deliberate, zone-confirmed
```

Documents and canvases follow the selected project:

```bash
anchor use work pumps
anchor ingest datasheet.pdf          # into work/pumps
anchor serve                         # open the canvas for work/pumps
```

`anchor migrate` folds a pre-existing `~/anchor-data` into
`envs/local/projects/default/`.

## Moving a project across environments

A project's environment is its zone. Moving a project changes where its
content may go, so it is a deliberate operation:

```bash
anchor project move pumps --to azure-work --env local
```

The command relocates the corpus and confirms the zone change before doing so
(for example "this changes the data zone from on-host to your Azure tenant.
Proceed?"). Editing a file will not move a project across a boundary.

## MCP (the agent path)

One MCP server serves one environment, named by `--env`:

```json
{ "mcpServers": {
    "anchor":      { "command": "anchor-mcp", "args": ["--env", "local"] },
    "anchor-work": { "command": "anchor-mcp", "args": ["--env", "azure-work"] }
}}
```

Project-scoped tools take an optional `project` argument
(`ingest_pdf(project="pumps", …)`). Lifecycle tools manage the environment:

- `create_environment(name, provider?, …)` — peer of `anchor env create`.
- `create_project(name, description?)`, `update_project(name, description)`.
- `list_projects()` — name and description for each project in the environment.
- `open_project(name)` — set a session default so `project` may be omitted.

A missing or unknown project returns a self-correcting error rather than
writing to a zone nobody chose:

```json
{ "error": "no_project",
  "message": "project 'ghost' does not exist in this environment. Create one with create_project(name), or pick one: [...]." }
```

Two environments are two named servers, set up on purpose. The agent can never
cross from one environment into another, and moving a project across
environments is not an MCP operation. That is the human, zone-confirmed
`anchor project move`.

`anchor install claude-desktop --env <name>` writes a named pointer entry. It
is additive (other servers are preserved), collision-safe (an existing name
pointing at a different environment is refused, use `--name` to add a second or
`--force` to repoint), and it echoes the egress zone before wiring.

## Claude Desktop walkthrough

1. One time: `anchor install claude-desktop --env local`, restart Desktop. The
   only terminal step.
2. First ask: "Ingest this pump datasheet and pull specs onto a canvas." If the
   environment is not set up, the agent runs `create_environment` (asking: on
   your machine, or via an API?), then `create_project("pumps")`, then ingests
   and builds the canvas. Two plain questions, no config file touched.
3. Second corpus: "New project for my paper." The agent runs
   `create_project("paper")` in the same environment. Same zone, separate
   documents and canvases.
4. Second environment: `anchor install claude-desktop --env azure-work --name
   anchor-work`, restart. Now "search my work docs" routes to the work server.

## Back-compat

A pre-existing `~/anchor-data` keeps working as the default environment's
`default` project until you run `anchor migrate`, which folds it into
`envs/local/projects/default/`. Nothing breaks in the meantime.
