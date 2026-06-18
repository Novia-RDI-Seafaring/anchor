# ANCHOR

**A**gent-**N**ative **C**anvas to **H**elp **O**rganize **R**esources<br>
*Source-Grounded Knowledge Canvas for Traceable Engineering Document Extraction*

ANCHOR is a tool that lets you and your agent work with engineering documents.

Drop a PDF onto a canvas. The agent reads it and pulls the values you need into a spec table. Every value links back to the page and bounding box it came from, so you can click and see the source.

Drop FMU simulation models onto the same canvas and wire the extracted values into their parameters.

It runs on your laptop. Run `anchor init` to create an environment — a named profile where you choose the AI provider (and therefore where your documents may go). Projects (corpuses) live inside it. Agents talk to it over MCP, so it works with Claude Code, Cursor, Claude Desktop, or any MCP client. There's an HTTP API and a CLI too.

---

## Get started

=== "uv (recommended)"

    ```bash
    uv tool install anchor-kb
    anchor serve
    ```

=== "pipx"

    ```bash
    pipx install anchor-kb
    anchor serve
    ```

=== "pip"

    ```bash
    pip install anchor-kb
    anchor serve
    ```

Then open <http://127.0.0.1:8002> in your browser.

For your own work, create an environment first: `anchor init` picks the AI
provider / data zone. See
[Environments and projects](concepts/projects.md).

Requires Python 3.12+. CI tests Linux and runs CLI smoke checks on macOS and
Windows; verify browser and PDF workflows on your target platform.

[Five-minute tutorial](getting-started/tutorial.md){.md-button .md-button--primary }
[Architecture overview](concepts/architecture.md){.md-button }

---

## What's in this documentation

- **[Tutorial](getting-started/tutorial.md)** - first day, from install to "agent fills in my engineering specs"
- **[Install](getting-started/installation.md)** - paths for end users and contributors, plus optional extras
- **[Usage](guides/documents-and-canvases.md)** - ingest documents, create canvases, and connect an agent
- **[Projects](concepts/projects.md)** - a folder is a project; providers, data zones, and how every adapter finds it
- **[Architecture](concepts/architecture.md)** - the hexagonal monolith, ports + adapters
- **[Data and events](concepts/data-and-events.md)** - workspace state model, event log, real-time sync
- **[On-disk substrate](concepts/on-disk-substrate.md)** - what every folder under a project means
- **[Canvas](concepts/canvas.md)** - node types, edges, sub-canvases
- **[Many interfaces](concepts/interfaces.md)** - HTTP, MCP, CLI, and the parity rule
- **[Extensions and OIP](concepts/extensions-and-oip.md)** - how third-party producers plug in
- **[Agent setup](guides/agent-setup.md)** - connect MCP clients and optional local models
- **[Agent configuration](guides/agent-configuration.md)** - configure Claude Code, Codex, Cursor, OpenCode, and generic stdio clients
- **[Reference](reference/cli.md)** - CLI, MCP tool families, and configuration
- **[Citation and acknowledgments](reference/citation.md)** - citing ANCHOR and project funding

---

## Designed for both humans and agents

ANCHOR is **agent-native**: every operation reaches HTTP, MCP, and CLI in parity. An agent driving the canvas through MCP and a human clicking in a browser end up at the same workspace, see each other's edits in real time, and share the same source-grounded view of the data.

The point is to kill the manual loop: open a datasheet, find a number, paste it into a spreadsheet or simulation, hope you got the right one. The agent does the lookup; the source link makes every answer checkable.
