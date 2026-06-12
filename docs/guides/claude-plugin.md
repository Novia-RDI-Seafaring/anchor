# Claude Code plugin

ANCHOR ships as a Claude Code plugin. The plugin bundles two things:

- the `anchor` MCP server, run via `uvx` so the published wheel is
  fetched on first use
- the `anchor` skill, so Claude knows when to drive ANCHOR instead of
  writing its own PDF parsing code

It works in the Claude Code CLI and in the desktop app. You do not need
to install the `anchor` CLI first.

## Requirements

- Claude Code with plugin support (run `/plugin` to check; update if
  the command is missing)
- [uv](https://docs.astral.sh/uv/) on your PATH. The plugin starts the
  MCP server with `uvx --from anchor-kb anchor-mcp`, so uv resolves and
  caches the `anchor-kb` wheel from PyPI on first run.

## Install

Inside Claude Code:

```text
/plugin marketplace add Novia-RDI-Seafaring/anchor
/plugin install anchor@anchor
```

Restart Claude Code or run `/reload-plugins`. Then run `/mcp` and check
that `anchor` is listed with its tools. The skill is available as
`/anchor:anchor`, and Claude invokes it automatically when you work
with engineering documents.

The first MCP call can take a while: uvx downloads the wheel and its
dependencies once, then reuses the cache.

## Update

```text
/plugin marketplace update anchor
```

The plugin version follows ANCHOR releases. A new release on PyPI is
picked up by uvx; the plugin manifest version is bumped in the same
release commit.

## Project resolution and the data dir

The plugin registers the MCP server without a baked data dir. The
server resolves the active project from its working directory, so the
normal flow is:

```bash
cd ~/my-project
anchor init        # optional: writes anchor.toml, picks the data dir
claude
```

Without a project, the server falls back to `ANCHOR_DATA_DIR`, then
`~/anchor-data`.

Some harness setups spawn the MCP server outside your project folder.
The desktop app is the known case (see
[issue #95](https://github.com/Novia-RDI-Seafaring/anchor/issues/95)).
The workaround is to pin the project explicitly with a user-level MCP
entry instead of the plugin's default one:

```bash
claude mcp add anchor -- uvx --from anchor-kb anchor-mcp --project /path/to/project
```

A user-level server named `anchor` coexists with the plugin's server;
disable the plugin's copy under `/plugin` if you pin one project this
way.

## The other install path: anchor install

If you already installed the CLI with `uv tool install anchor-kb`, the
older path still works:

```bash
anchor install claude-code
```

It writes the same MCP entry and skill into your user config
(`~/.claude.json` and `~/.claude/skills/anchor/`). Pick one path. If
you use both, Claude Code sees two `anchor` MCP servers and two copies
of the skill, which wastes context and can confuse tool selection.

| | Plugin marketplace | `anchor install claude-code` |
| --- | --- | --- |
| Needs the CLI installed first | No (uvx fetches the wheel) | Yes |
| Updates | `/plugin marketplace update` | Re-run after upgrading |
| Works in the desktop app | Yes | Yes |
| Skill location | Plugin-managed | `~/.claude/skills/anchor/` |

For Cursor, Codex, and other harnesses, see the
[agent configuration guide](agent-configuration.md).

## For maintainers

The plugin lives in `plugins/anchor/`; the marketplace catalog is
`.claude-plugin/marketplace.json` at the repo root. The skill file
`plugins/anchor/skills/anchor/SKILL.md` is generated from
`src/anchor/skills/`. After editing those sources or bumping the
version in `pyproject.toml`, regenerate and commit:

```bash
uv run python scripts/build_claude_plugin.py
```

Validate before merging:

```bash
claude plugin validate .
claude plugin validate ./plugins/anchor
```
