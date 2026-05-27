# ANCHOR tutorial - first day

Five minutes from zero to "agent fills in my engineering specs while I watch".

This walkthrough assumes you have a working AI harness on your machine
(Claude Code, Cursor, opencode). If not, do that first; the agent is the
half of ANCHOR that makes the canvas pay off.

## 1. Install

You need Python 3.12+. CI runs on Linux and performs CLI smoke checks on
macOS and Windows.

```bash
uv tool install anchor-kb
```

After the install completes, `anchor` and `anchor-mcp` are on your `$PATH`.

```bash
anchor version
```

If you prefer plain pip / pipx, both work too:

```bash
pipx install anchor-kb           # isolated CLI install
# or
pip install anchor-kb            # in your active virtualenv
```

## 2. Run `anchor demo`

```bash
anchor demo
```

This does three things in every installation:

1. Creates `~/anchor-data/` if it's missing.
2. Creates a workspace called `demo` and drops six
   **placeholder spec nodes** with hints like "Max inlet pressure",
   "Temperature range", "Motor power range".
3. Starts the server on `localhost:8002`.

If an optional local demo PDF is already present, `anchor demo` also ingests
it and adds a document node. The public repository and package do not ship a
vendor PDF. For a normal first run, ingest your own PDF in another terminal:

```bash
anchor ingest /path/to/datasheet.pdf
```

Silver extraction is local. Gold regions build only when you configure
`ANCHOR_OPENAI_API_KEY` (or `OPENAI_API_KEY`) and a suitable vision endpoint.
Leave the server running.

If the server's already running on that port, pass `--port 8003`. MCP tools
still work through stdio; for canvas snapshots, add
`"--base-url", "http://localhost:8003"` to the installed `anchor-mcp`
arguments in your harness configuration.

## 3. Open the canvas

```text
http://localhost:8002/c/demo
```

You'll see:

- Six **placeholder spec nodes** in a grid on the right. Each carries a
  dashed sky-blue outline and a small `✶ empty · <hint>` chip in the
  top-right corner. That's the "agent please fill this" signal.
- A **document node** after you ingest your PDF.

Try it: right-click a plain shape, pick `Mark as placeholder`. It
flips to the dashed-sky look. Pick `Clear placeholder` to revert.

## 4. Register ANCHOR with your AI harness

In a second terminal:

```bash
anchor install claude-code        # or: anchor install cursor
```

This writes:

- `~/.claude/mcp.json` — an MCP server entry pointing at `anchor-mcp`.
- `~/.claude/skills/anchor/SKILL.md` — a skill so Claude Code knows
  when to invoke ANCHOR's tools.

Restart your harness (`Cmd+Q`, reopen). In any conversation, `/mcp`
should now show `anchor` with a handful of tools.

ANCHOR's MCP server also returns a short system-prompt block on connect
that tells the agent how to think about the canvas — the substrates,
the source-grounding rule, and the placeholder protocol. You don't
need to brief it yourself.

## 5. Ask the agent to fill the placeholders

In your harness, paste:

> Please fill in the placeholder spec nodes on the `demo` canvas using
> `canvas_list_placeholders` + `search_documents`.

The agent will:

1. Call `canvas_list_placeholders(workspace_slug="demo")` to see what's
   empty.
2. For each placeholder, call `search_documents` (or `get_gold_regions`)
   to find the relevant region of your ingested PDF.
3. Call `canvas_update_node` with the resolved rows + a `source_ref`
   carrying the doc slug, page, and bbox. The `placeholder: false` flag
   clears the dashed outline and chip.

## 6. Watch it happen live

Your browser tab on `/c/demo` is subscribed to a Server-Sent Events feed.
As the agent writes each node, you'll see:

- The chip disappears.
- The dashed sky outline flips to solid neutral.
- The spec rows fade in.
- A `p2` badge (or wherever the source lives) appears on the spec
  header — click it to open the source page in the viewer.

No reload needed. The same SSE stream is how a second browser tab, a
second agent, or a headless viewer would see the same updates.

## 7. Inspect a value's source

Click any `p2` badge on a spec table to open the PDF viewer at that
page, with the relevant region's bbox highlighted in sky-blue. This is
the trust mechanism: every value the agent writes points back to a
specific page+bbox. If you don't see a source ref, treat the value as
ungrounded.

## What's next

- Drop another PDF onto the canvas and the same flow works on a fresh
  doc. `anchor ingest /path/to/file.pdf` runs the pipeline from the CLI.
- Make your own placeholders: right-click any shape → `Mark as
  placeholder`. Set `data.placeholder_hint` via the Properties panel to
  give the agent a steer.
- Run `anchor canvas placeholders demo` in a shell to see the agent-
  visible list any time.
- Read [Many interfaces](../concepts/interfaces.md) to understand why CLI / MCP / HTTP
  are peers, not one wrapping another.

## Troubleshooting

`anchor ingest` produced no gold regions. Check `ANCHOR_OPENAI_API_KEY`
and the configured vision model. Without a configured LLM endpoint, silver
still builds but region-driven placeholder filling is unavailable.

`/mcp` doesn't list `anchor`. Restart your harness fully (`Cmd+Q`,
reopen — not just close the window). MCP server lists load on startup.

Port 8002 is taken. Pass `--port` to `anchor demo`. For MCP snapshots,
add a matching `--base-url http://localhost:<port>` argument to the
installed `anchor-mcp` entry in your harness configuration.

The canvas didn't update live. The browser is fine; SSE always
reconciles on next state read. Force a refresh — but first check
`anchor canvas state demo` from the shell; if the state's there, the
SSE reconnect just hasn't fired yet.
