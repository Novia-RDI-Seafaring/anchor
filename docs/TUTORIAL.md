# Anchor tutorial — first day

Five minutes from zero to "agent fills in my engineering specs while I watch".

This walkthrough assumes you have a working AI harness on your machine
(Claude Code, Cursor, opencode). If not, do that first; the agent is the
half of Anchor that makes the canvas pay off.

## 1. Install

You need Python 3.12+ on macOS or Linux.

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

This does four things, in order:

1. Creates `~/anchor-data/` if it's missing.
2. Stages the bundled Alfa-Laval LKH-5 pump datasheet into
   `~/anchor-data/bronze/`.
3. Runs the bronze → silver → gold ingest pipeline so the doc is
   queryable. Silver always builds; gold + embeddings build if you have
   `ANCHOR_OPENAI_API_KEY` (or `OPENAI_API_KEY`) set, otherwise the demo
   logs a friendly note and the agent will fall back to page-text reads.
4. Creates a workspace called `demo` and drops one document node + six
   **placeholder spec nodes** with hints like "Max inlet pressure",
   "Temperature range", "Motor power range".

Then it starts the server on `localhost:8002`. Leave it running.

If the server's already running on that port, pass `--port 8003` (and
later pass the same to `anchor install` so MCP points at the right
place).

## 3. Open the canvas

```text
http://localhost:8002/c/demo
```

You'll see:

- One **document node** (Alfa-Laval LKH-5) on the left.
- Six **placeholder spec nodes** in a grid on the right. Each carries a
  dashed sky-blue outline and a small `✶ empty · <hint>` chip in the
  top-right corner. That's the "agent please fill this" signal.

Try it: right-click a plain shape, pick `Mark as placeholder`. It
flips to the dashed-sky look. Pick `Clear placeholder` to revert.

## 4. Register Anchor with your AI harness

In a second terminal:

```bash
anchor install claude-code        # or: anchor install cursor
```

This writes:

- `~/.claude/mcp.json` — an MCP server entry pointing at `anchor-mcp`.
- `~/.claude/skills/anchor/SKILL.md` — a skill so Claude Code knows
  when to invoke Anchor's tools.

Restart your harness (`Cmd+Q`, reopen). In any conversation, `/mcp`
should now show `anchor` with a handful of tools.

Anchor's MCP server also returns a short system-prompt block on connect
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
   to find the relevant region of the LKH-5 PDF.
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
- Read `docs/06-many-interfaces.md` to understand why CLI / MCP / HTTP
  are peers, not one wrapping another.

## Troubleshooting

`anchor demo` errored on ingest. Look for `ANCHOR_OPENAI_API_KEY` in
the output. Without it the gold layer (and embeddings) is skipped — the
demo still works, the agent just has fewer tools. Set the key and
re-run.

`/mcp` doesn't list `anchor`. Restart your harness fully (`Cmd+Q`,
reopen — not just close the window). MCP server lists load on startup.

Port 8002 is taken. Pass `--port` to both `anchor demo` and to your
agent's MCP config, then re-run `anchor install`.

The canvas didn't update live. The browser is fine; SSE always
reconciles on next state read. Force a refresh — but first check
`anchor canvas state demo` from the shell; if the state's there, the
SSE reconnect just hasn't fired yet.
