# Environments and projects

Anchor has two levels: **environments** and **projects**.

An environment is the directory you `anchor init`. It holds the
configuration (provider, models, data zone) and any number of projects.
It is the trust boundary. The global default lives at `~/.anchor`.

A project lives inside an environment. It owns its own documents
(bronze/silver/gold) and canvases. It inherits the environment config
unless it overrides.

```
<environment>/                 # `anchor init`, or the global default ~/.anchor
├── config.toml                # provider, models, data zone, environment metadata
└── projects/
    └── <name>/                # a project: its own documents + canvases
        ├── project.toml        # optional: metadata + rare config overrides
        ├── bronze/ silver/ gold/
        └── canvases/<slug>/
```

One project is a cheap namespace inside one trust boundary. One
environment is the boundary itself. Two environments are two MCP servers
you set up on purpose, so an agent never crosses from a private corpus
into a cloud tenant by accident.

## Why two levels

The same setup with many separate corpuses is many projects under one
environment. A different setup for one corpus is a `project.toml`
override. The provider choice (where document content may go) is set once
per environment, so every project under it shares the same data zone.

## Config layering

```
built-in defaults  <  environment config.toml  <  project project.toml  <  ANCHOR_* env vars / flags
```

The MCP config never stores settings. It points at the environment, and
the settings live in the environment config. The CLI and the MCP server
resolve the same config, so `anchor check` can audit the active provider
and zone.

## CLI

```bash
anchor init                          # make this folder an environment
anchor project create pumps          # add a project
anchor project create pumps --description "LKH pump datasheets"
anchor project list                  # name + description, for picking
anchor project set-description pumps "Centrifugal pump family"
anchor migrate                       # move ~/anchor-data into ~/.anchor/projects/default
```

Every `anchor ... --env <dir>` selects an environment explicitly. Without
it, Anchor walks up from the current directory to a config file, then
falls back to the global default `~/.anchor`.

## MCP

One server serves one environment. The project is a per-call argument.

```bash
anchor-mcp --env ~/.anchor            # serves every project in the environment
```

Project-scoped tools take an optional `project` argument
(`ingest_pdf(project="pumps", ...)`, `search_documents(query, project="pumps")`).
Lifecycle tools manage the environment:

- `create_environment(directory?, provider?, ...)` — peer of `anchor init`
- `create_project(name, description?)`
- `list_projects()`
- `open_project(name)` — set a session default so `project` may be omitted

A missing or unknown project returns a self-correcting error rather than
writing to a zone nobody chose:

```json
{ "error": "no_project",
  "message": "project 'ghost' does not exist. Create one with create_project(name), or pick one: [...]." }
```

The global default environment (`~/.anchor`) keeps the smooth single-corpus
flow: omit `project` and it uses `default`. A named environment requires an
explicit project.

## Multiple environments

A second environment is a second named MCP server.

```json
{ "mcpServers": {
    "anchor":      { "command": "anchor-mcp", "args": ["--env", "~/.anchor"] },
    "anchor-work": { "command": "anchor-mcp", "args": ["--env", "~/work/anchor-azure"] }
}}
```

`anchor install claude-desktop` writes one named pointer entry. It is
additive (other servers are preserved), collision-safe (an existing name
pointing at a different environment is refused, use `--name` to add a
second or `--force` to repoint), and it echoes the egress zone before
wiring.

```bash
anchor install claude-desktop                                   # name 'anchor' -> ~/.anchor
anchor install claude-desktop --env ~/work/anchor-azure --name anchor-work
```

## Claude Desktop walkthrough

1. One time: `anchor install claude-desktop`, restart Desktop. The only
   terminal step.
2. First ask: "Ingest this pump datasheet and pull specs onto a canvas."
   The agent runs `create_environment` (asks: on your machine, or via an
   API?), then `create_project("pumps")`, then ingests and builds the
   canvas. Two plain questions, no config file touched.
3. Second corpus: "New project for my paper." The agent runs
   `create_project("paper")` in the same environment. Same privacy,
   separate documents and canvases.

## Back-compat

A pre-#120 install keeps working. A folder with an `anchor.toml` is read
as an environment with one `default` project at the data dir it names. The
global default falls back to today's `~/anchor-data` as its `default`
project until `anchor migrate` relocates it.

See the canonical design in
[Novia-RDI-Seafaring/anchor#120](https://github.com/Novia-RDI-Seafaring/anchor/issues/120).
