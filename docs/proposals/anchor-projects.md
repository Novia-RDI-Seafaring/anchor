# Proposal: ANCHOR projects (`anchor init` + `anchor link`)

**Status:** draft, not yet implemented
**Target:** v0.3

## Motivation

A user running `anchor serve` today gets one global data directory at
`~/anchor-data`. Everything they ever ingest piles into it. That works
for one engineer with one focus area; it breaks the moment they want:

- Two unrelated projects with separate knowledge bases (Vessel A's
  datasheets shouldn't bleed into Vessel B's agent queries)
- A teammate's research project they'd like to *consume* but not
  *clutter* their own data dir with
- A self-contained project folder they can hand to a colleague (or
  zip + email) and have it Just Work
- A way to live alongside other tools (`.git/`, `.claude/`,
  `.vscode/`) in a project directory without taking the whole space

This proposal adds a project model: each project is a directory you
can `anchor init` and optionally `anchor link` other projects into.
It mirrors conventions people already know from `npm`, `pip`, `git`,
and Claude Code's own `.claude/`.

## Default shape

```
my-project/
├── .git/
├── .claude/                       # optional, Claude Code project
├── .anchor/
│   ├── config.toml                # small, commit-friendly
│   └── data/                      # default data location
│       ├── bronze/  silver/  gold/
│       └── canvases/
└── (everything else the project has)
```

`anchor init` in any directory creates `.anchor/config.toml` and
`.anchor/data/`. The data dir lives next to the project by default,
so the project is self-contained.

### Discovery

When any `anchor` command runs, walk up from `cwd` looking for the
first ancestor containing `.anchor/config.toml`. Found → use it.
Not found → fall back to the legacy global default
(`~/anchor-data`, env vars).

### Override

```toml
# .anchor/config.toml
data_dir = ".anchor/data"          # default (relative to config file)
# data_dir = "~/anchor-data/vessel-a"           # outside the project
# data_dir = "/Volumes/SSD/anchor/vessel-a"     # on a faster disk
```

The `data_dir` value is the only thing required for a project to be
valid. Everything else (`openai_base_url`, `region_model`, …) inherits
from env vars / global defaults if absent.

## `anchor init`

```bash
$ cd my-project
$ anchor init

Created .anchor/config.toml
Data directory: .anchor/data/        (project-local; override in config)

Next:
  anchor serve              # use this project's config
  anchor demo               # seed with the sample PDF
```

Flags:

| Flag | Effect |
|---|---|
| `--data-dir <path>` | Set a different data dir at init time. |
| `--global` | Use `~/anchor-data/<cwd-name>` instead of `.anchor/data/`. |
| `--name <slug>` | Set the project's display name (defaults to cwd basename). |

`anchor init` is idempotent: re-running on an already-initialised
project prints a warning and exits 0 without overwriting.

## `anchor link`

Compose multiple anchor projects together: include another project's
documents into the current project, read-only by default, read-write
on opt-in. Modelled on `npm link` and `pip install -e`.

```bash
$ anchor link ~/work/company-catalogue
Linked: ~/work/company-catalogue (read-only)
  contains 47 documents, 12 canvases

$ anchor link ~/work/lamins-research --writable
Linked: ~/work/lamins-research (read-write)

$ anchor link --list
Linked sources in this project:
  ~/work/company-catalogue   (read-only,  47 docs,  12 canvases)
  ~/work/lamins-research     (read-write,  3 docs,   1 canvas)

$ anchor unlink ~/work/lamins-research
Unlinked: ~/work/lamins-research
```

Each link writes a block to `.anchor/config.toml`:

```toml
[[link]]
path = "~/work/company-catalogue/.anchor/data"
mode = "read-only"
include = ["pump-*", "motor-*"]   # optional glob filter on slugs
```

### Read-merged document store

Extend the existing `FsDocStore` (and the equivalent canvas store)
to read from an **ordered chain** of directories:

1. Local `.anchor/data/` (highest priority, writable)
2. Each `[[link]]` entry in declaration order

When the agent or UI asks for `gold/alfa-laval-lkh-5/`:

- First look in the local data dir
- Then walk the link chain
- First match wins
- Metadata on the response carries `source` so the UI can show a
  "linked" badge and the agent can reason about provenance

Writes go to the local data dir unless the slug came from a
`read-write` link. Writes to a `read-only` link return a clear
error: *"Document `alfa-laval-lkh-5` lives in linked source
`company-catalogue` (read-only). Run `anchor copy alfa-laval-lkh-5`
to import it locally before editing."*

### Permissions

For local links, filesystem permissions are the permission model. If
you can read the path, you can link to it. If you can't write it, the
link is read-only by force regardless of the configured mode.
Anchor does not invent its own permission model.

Cross-machine linking is out of scope for v0.3. When it lands, identity
will come from whatever transport carries it (HTTP auth, SSH, S3
credentials, etc.).

## What's *not* in v0.3

- **Linking canvases.** Canvases have live state and an event log;
  linking them requires deciding whether linked-canvas edits stay
  local (a fork) or push through to the source. Defer to v0.4 once
  doc linking is proven.
- **Content-addressed deduplication.** If two linked sources both
  contain `alfa-laval-lkh-5`, the first one wins and `anchor doctor`
  shows the duplicate. Real dedup (content-hash addressing) is v1.0.
- **Cross-machine links.** Local filesystem links only.
- **Anchor link registry** (`anchor link install @novia/maritime-catalogue`).
  Far-future, not before v1.0.

## Interaction with `anchor install`

The MCP server today is registered once globally with a fixed
`--data-dir` baked into the entry. With projects, each project gets
its own MCP server entry, so the agent can talk to multiple projects
without ambiguity:

```bash
$ cd ~/work/vessel-a
$ anchor install claude-code --project
Wrote MCP entry 'anchor-vessel-a' → ~/.claude/mcp.json
  --data-dir ~/work/vessel-a/.anchor/data
```

`~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "anchor-vessel-a": {
      "command": "anchor-mcp",
      "args": ["--data-dir", "/Users/you/work/vessel-a/.anchor/data"]
    }
  }
}
```

The agent sees `anchor-vessel-a.list_documents` as a tool, namespaced
distinctly from any other Anchor instance. Three vessels open in
three Claude Code windows = three distinct MCP entries, three
namespaces, no overlap.

Without `--project`, `anchor install claude-code` keeps the legacy
behaviour: a single global MCP entry named `anchor` pointing at
`~/anchor-data`.

## Implementation sequencing

| Step | What | Effort |
|---|---|---|
| 1 | `anchor doctor` (no config changes; pure diagnostics) | ½ day |
| 2 | `.anchor/config.toml` discovery + load in `infra/config.py` | ½ day |
| 3 | `anchor init` (creates `.anchor/data/` by default) | ½ day |
| 4 | `anchor link` (read-only documents only) | 1 day |
| 5 | `anchor unlink` + `anchor link --list` | ½ day |
| 6 | `anchor link --writable` | ½ day |
| 7 | `anchor install claude-code --project` | ½ day |
| 8 | UI: "linked" badge on document tiles | ½ day |
| 9 | Migration helper for users on the old `~/anchor-data` flat layout | ½ day |

Each step is a self-contained PR. Items 1-7 are the v0.3 release;
items 8-9 land in v0.3.1 or v0.4 as time allows.

## Open questions

- **`.anchor/data/` vs `data/`**: should the data dir name be a magic
  hidden one or just `data/`? Hidden matches `.git/`'s convention but
  isn't visible in Finder/Explorer by default. Probably keep hidden
  for consistency with the rest of the `.anchor/` tree.
- **What goes into `.anchor/config.toml`?** Minimum: `data_dir` + the
  `[[link]]` blocks. Maximum: everything pydantic-settings exposes
  (so a project can override the OpenAI base URL, region model,
  embed model, etc.). Suggest start minimum and grow.
- **Should `.anchor/config.toml` be committable?** Yes by default —
  it's how a project communicates its setup to a clone-and-go user.
  Secrets stay in env vars / `.env` (which is gitignored).
- **What if two projects' data dirs collide?** Two projects both
  declaring `data_dir = "~/anchor-data/shared"` is technically fine
  — they share the workspace. `anchor doctor` should flag it as
  "data dir shared with project X" so the user knows.
- **Should `anchor link` accept a URL (Git, HTTP)?** Not in v0.3.
  Local paths only. Remote sources are a v0.4+ conversation.

## Test plan (when implemented)

- `anchor init` in a fresh directory creates the expected files
- Re-running `anchor init` is idempotent
- `anchor serve` from inside a project picks up the project's
  `data_dir`, falls back to global if no `.anchor/` is found
- `anchor link <path>` adds the expected `[[link]]` block; the
  document store reads merged + flagged from the local + linked dirs
- Writes to read-only linked docs return the error envelope
- `anchor doctor` reports the active config source + every linked
  source's status
- The MCP install path supports multiple named entries

---

*Last updated: 2026-05-28. This is a living draft; comments and
counter-proposals welcome.*
