# Connect an agent

ANCHOR supplies tools to an external MCP-capable agent. The agent's client and
model run separately from the canvas server. Browser requests wait until that
agent retrieves and handles them.

## Create an environment and project first

Follow the [Quickstart](../getting-started/quickstart.md), or use an existing
environment and project. These examples use environment `study`, project
`pump-study`, and canvas `pump-selection`.

The provider controls ANCHOR's model clients. Your harness controls its own
model calls. With `harness`, page work items reach the agent. With `local`,
ANCHOR skips model-assisted gold extraction, but MCP tools can still return
document content to a connected agent.

## Register your client

Run one installer for your client:

| Client | Command | What it installs |
| --- | --- | --- |
| Codex | `anchor install codex --env study` | Named MCP entry, normally `anchor-study`. No separate skill file. |
| Claude Desktop | `anchor install claude-desktop --env study` | Named MCP entry, normally `anchor-study`. |
| Claude Code | `anchor install claude-code --env study` | MCP entry named `anchor` and a composed ANCHOR skill. |
| Cursor | `anchor install cursor --env study` | MCP entry named `anchor`; optional project rules with `--rules`. |

Restart or reconnect the client after registration. Each entry launches
`anchor-mcp --env study` over stdio. The MCP server provides tool descriptions,
connection instructions, and an `anchor://help` resource. It does not start the
browser server.

Codex and Claude Desktop support `--name` for multiple named entries. Claude
Code and Cursor use a single `anchor` entry; rerunning their installer selects
the requested environment for that entry. `--dry-run` previews an installer.
Codex's installer preserves settings but rewrites TOML formatting and comments;
it makes a one-time `config.toml.anchorbak` backup.

Cursor's optional `--rules` writes a project-scoped pointer to `AGENTS.md` and
the CLI/MCP surfaces. Use it when those instructions exist in your workspace;
the rules file does not create the project conventions itself.

See [Agent configuration](agent-configuration.md) for manual configuration and
other clients. No hosted MCP HTTP endpoint is provided by `anchor serve`.

## Confirm the environment and project

Ask the agent:

> List ANCHOR projects in `study`. Open `pump-study` and report its status.
> Check pending intents for that project before starting work.

The agent uses `list_projects`, `open_project`, `anchor_status`, and
`list_pending_intents`. It can instead pass `project="pump-study"` on each
project-scoped tool. `anchor use study pump-study` selects only the CLI project;
it does not retarget the MCP server or agent session.

The initial MCP tool list is intentionally small. The agent can call
`anchor_list_capabilities` to discover advanced canvas, ingestion, CAD, SysML,
and FMU tools. A tool omitted from the initial advertised list is not necessarily
unavailable.

## Start the canvas server

```bash
anchor serve --env study --project pump-study
```

Open the printed URL and the `pump-selection` canvas. A browser server serves
one project; the named MCP server can address multiple projects in its environment.
Choose the same project on both sides.

Browser changes arrive through SSE. MCP uses its own local stdio process and
the persisted project stores. Do not assume the client is continuously listening
or polling. Tell it to check pending intents at the start of an ANCHOR task.

## Give a concrete request

> In project `pump-study`, process the pending PDF ingestion intent on
> `pump-selection`, then propose one spec table with row-level source references.
> Ask me in the intent thread if the desired product variant is unclear.

For submitted canvas asks, the agent should reply in the thread and stage
suggestions for your review. It should wait for clarification or approval rather
than approving its own suggestion. Direct extraction requests made in the agent
chat can also create canvas objects through the normal canvas tools.

## Troubleshooting

- **No documents:** verify the MCP environment, call `list_projects`, and use
  the right project. Check the browser server with `anchor serve-info`.
- **Awaiting agent:** have the agent pull the ingestion intent and complete the
  harness session. A PDF upload does not automatically run your harness.
- **Executable missing:** locate `anchor-mcp` with `Get-Command anchor-mcp`
  on PowerShell or `command -v anchor-mcp` on Bash, then reconnect the client
  with the correct executable path.
- **Tool missing:** ask for `anchor_list_capabilities`. FMU simulation also
  requires the optional runtime.
- **Windows reinstall blocked:** close clients using the installed MCP server
  before upgrading. See [Install](../getting-started/installation.md#reinstall-or-upgrade).

## Optional canvas snapshots

Snapshots need a running server and Playwright Chromium. For a uv tool install:

```bash
uv tool run --from anchor-kb playwright install chromium
anchor canvas snapshot pump-selection --out canvas.png
```

The agent can request `canvas_snapshot` with `format="inline"` for image-capable
clients. If the server uses another port, set the MCP entry's `--base-url` to
the printed server URL. A snapshot request must target the project served by
that browser server.
