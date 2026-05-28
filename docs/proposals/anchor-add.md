# Proposal: `anchor add` — install third-party extensions

**Status:** draft, not yet implemented
**Target:** v0.3
**Owners:** Christoffer Björkskog, Lamin Jatta
**Depends on:** [`anchor-projects.md`](./anchor-projects.md) (the `.anchor/` directory
convention), [`agent-skill-spec.md`](./agent-skill-spec.md) (the OIP 0.2
`agent` block), OIP PR #1 (the protocol-side schema for that block)

## Motivation

Today an OIP producer that someone built — Lamin's transcription tool,
a colleague's CAD parser, the audio-segmenter on PyPI — has no quick
install path into Anchor. `anchor extensions add <path/to/manifest.json>`
exists but assumes you already have the manifest sitting on disk. There's
no fetch, no version pinning, no project scope, and no path that says
"give me the thing on PyPI by name."

`anchor add <ref>` closes that gap. It mirrors the install verbs people
already know (`pip install`, `uv add`, `npm install`) and lands the
extension in a project-local directory by default.

## Default shape

```bash
$ cd ~/work/vessel-a
$ anchor add anchor-transcribe

✓ Installed anchor-transcribe from PyPI (v0.3.1)
  Registered at .anchor/extensions/anchor-transcribe/
  MCP entry written to ~/.claude/mcp.json (server: anchor-transcribe)
```

The project layout afterward:

```
~/work/vessel-a/
├── .anchor/
│   ├── config.toml
│   ├── data/
│   └── extensions/
│       ├── anchor-transcribe/        # installed extension, project-scoped
│       │   ├── manifest.json
│       │   ├── skills/skill.md
│       │   └── _env/                 # per-extension venv (for PyPI installs)
│       └── lockfile.json             # source + ref + installed-at per ext
```

Defaults that match modern tooling:

- **Project-local first.** Same as uv's `.venv`, npm's `./node_modules`,
  pip's editable installs in a venv. Extensions belong to a project.
- **`--global` for system-wide.** Falls back to
  `~/.config/anchor/extensions/`. Use when you want a personal
  extension available across every project.
- **`anchor init` required first** if no `.anchor/` is found in cwd or
  any ancestor. A friendly error directs the user:

  ```
  $ anchor add anchor-transcribe
  error: no .anchor/ project found in /Users/me/somewhere.

  To install for this project:        anchor init && anchor add anchor-transcribe
  To install for the whole machine:   anchor add --global anchor-transcribe
  ```

## Ref forms

The single `<ref>` argument disambiguates by prefix — same parsing
model as `pip install`. Bare names default to PyPI because that's where
most OIP producers will ship.

| Ref form | Source | Example |
|---|---|---|
| Bare name | **PyPI** (default) | `anchor add anchor-transcribe` |
| `pypi:<name>` | Explicit PyPI (equivalent to bare) | `anchor add pypi:anchor-transcribe` |
| `github:<owner>/<repo>[@<ref>][/<subpath>]` | Git clone the repo, optionally pinned to a tag/commit, manifest at `<subpath>` (default: repo root) | `anchor add github:Novia-RDI-Seafaring/anchor-transcribe@v0.3` |
| `git+<url>` | Generic git URL (GitLab, Bitbucket, self-hosted) | `anchor add git+ssh://git@gitlab.example.com/team/foo.git` |
| `https://...` | HTTP fetch of a single `manifest.json` | `anchor add https://example.com/manifests/foo.json` |
| `./path` or `/abs/path` | Local manifest file or directory | `anchor add ./manifest.json` |
| `npm:<name>` | **Deferred** until v0.4 | (error with a helpful workaround message) |

The bare-name → PyPI default keeps the common case short while letting
disambiguation be one prefix away.

## What "install" actually does

The install pipeline per source type:

### `pypi:` (or bare name)

1. Create a per-extension target dir: `.anchor/extensions/<name>/`.
2. Provision a per-extension venv: `.anchor/extensions/<name>/_env/`
   using `uv pip install --target` so the host Anchor's environment
   stays clean.
3. Install the package into the venv.
4. Resolve the package's manifest via the `oip.producers` entry point
   convention:

   ```toml
   # the third-party producer's pyproject.toml
   [project.entry-points."oip.producers"]
   anchor-transcribe = "anchor_transcribe:manifest_path"
   ```

   The entry point yields a callable returning the manifest path inside
   the installed package.
5. Symlink (or copy, on filesystems without symlinks) the resolved
   manifest into the target dir as `manifest.json`.
6. Write a `lockfile.json` entry recording the source, the requested
   ref, the resolved package version, and the install timestamp.
7. Update the MCP harness config (see "MCP wiring" below).

### `github:` / `git+`

1. Create the target dir.
2. `git clone --depth 1` to the target dir. Honour the `@<ref>` (tag,
   branch, or commit) if specified.
3. Locate `manifest.json` — default at the repo root, override via the
   `/<subpath>` suffix.
4. Record `source: github:owner/repo`, the resolved commit SHA, and
   timestamp in the lockfile.
5. Update MCP harness config.

### `https://...`

1. Fetch the manifest JSON via `httpx.get`.
2. Validate it against the OIP schema (via the bundled `oip.validator`
   helper). Refuse to register if invalid; print the schema error.
3. Write it to the target dir as `manifest.json`.
4. Record the source URL and the SHA-256 of the body for
   reproducibility.
5. Update MCP harness config.

### `./path` or absolute path

1. Resolve to a real path.
2. If it's a manifest file → copy or symlink it.
3. If it's a directory → look for `manifest.json` at the root.
4. Record source as `path:<absolute-path>`. No version metadata.

## Lockfile

```json
{
  "extensions": {
    "anchor-transcribe": {
      "source": "pypi:anchor-transcribe",
      "ref": "0.3.1",
      "resolved_version": "0.3.1",
      "manifest_path": "/Users/me/work/vessel-a/.anchor/extensions/anchor-transcribe/manifest.json",
      "installed_at": "2026-05-28T11:20:14Z"
    },
    "anchor-coderag": {
      "source": "github:Novia-RDI-Seafaring/anchor-coderag",
      "ref": "v0.1.2",
      "resolved_commit": "abc123def...",
      "manifest_path": "/Users/me/work/vessel-a/.anchor/extensions/anchor-coderag/manifest.json",
      "installed_at": "2026-05-28T11:21:02Z"
    }
  }
}
```

Two lockfiles in practice — one project-scoped at
`.anchor/extensions/lockfile.json`, one global at
`~/.config/anchor/extensions/lockfile.json`. Same schema in both.

The lockfile is committed by default (it's small, deterministic, and
answers "what version is this teammate running?"). Lockable: future
`anchor sync` will read the lockfile and reinstall.

## CLI surface

```bash
anchor add <ref>                 # install + register (default: project-local)
anchor add <ref> --global        # install to ~/.config/anchor/extensions/
anchor add <ref> --as <name>     # override the registered name (useful for forks)
anchor add <ref> --dry-run       # download + validate + print plan, no write

anchor remove <name>             # uninstall + deregister
anchor remove --global <name>    # remove from the global slot

anchor upgrade [<name>]          # refresh one extension or all of them
anchor upgrade --check           # report what would change, no write

anchor list                      # what's installed; show scope + source
anchor show <name>               # everything we know: manifest, lockfile entry,
                                 # which MCP server registers it
```

`anchor extensions add <path>` stays as a low-level escape hatch — third
parties without a packaged manifest source can still drop a JSON.

## Discovery + resolution order

Resolution chain when a consumer asks "is producer X available":

1. **Project** — `<cwd>/.anchor/extensions/*/manifest.json`
2. **Global** — `~/.config/anchor/extensions/*/manifest.json`
3. **System** — `~/.config/oip/producers.d/*.json` (existing OIP
   convention; an installer may drop a manifest here without going
   through Anchor)
4. **Bundled** — in-tree, compiled into the wheel

First-match wins on name collision. `anchor list` shows which scope
each registered extension came from.

## MCP wiring

The MCP server today (`anchor-mcp`) only loads bundled extensions.
Third-party extensions need either:

- **Anchor proxies their MCP tools.** `anchor-mcp` reads the
  `invocation` block from each registered manifest, spawns the
  extension's MCP subprocess at startup, multiplexes tool calls.
  Single MCP entry in `~/.claude/mcp.json` for the user.
- **Each extension is its own MCP entry.** `anchor add` writes a
  separate MCP entry per extension (`anchor-transcribe` alongside
  `anchor`). The agent sees them as peer servers.

For v0.3 we ship **independent MCP entries**. It's simpler, debuggable,
and matches how MCP harnesses already think about servers. Proxying is
strictly more complex (lifecycle, error attribution, tool naming
collisions) and can land later if a real need emerges.

What `anchor add` writes when registering an MCP-speaking extension:

```json
{
  "mcpServers": {
    "anchor": { "...": "..." },
    "anchor-transcribe": {
      "command": "/path/to/.anchor/extensions/anchor-transcribe/_env/bin/anchor-transcribe-mcp",
      "args": ["--data-dir", "/path/to/.anchor/data"]
    }
  }
}
```

`anchor remove` cleans up the matching entry.

## Relationship to OIP (the layer split)

The work splits cleanly between repos:

| `oip add <ref>` | `anchor add <ref>` |
|---|---|
| Lives in the OIP package (deferred for now per a separate decision) | Lives in this repo |
| Vendor-neutral installer for any OIP-aware consumer | Anchor-specific wrapper |
| Always installs **globally** to `~/.config/oip/producers.d/` | Defaults to **project-local** in `.anchor/extensions/` |
| Owns the **fetch + validate + register** machinery | Owns Anchor's **MCP wiring, lockfile, project scope** |
| Doesn't know about MCP harness configs | Updates `~/.claude/mcp.json` etc. on register |

When `oip add` ships, `anchor add` becomes a thin wrapper that calls
`oip.installer.install(ref, destination=<project-scoped-path>)` for the
fetch + validate + write, then adds Anchor's MCP wiring on top. Until
then, `anchor add` does the fetch itself.

## Compatibility with skills.sh

[skills.sh](https://www.skills.sh) is an emerging distribution + leaderboard
platform for cross-harness agent skills. Their install verb is
`npx skills add owner/repo` and they support multiple harnesses
(Claude Code, Cursor, Copilot).

This proposal is **not** in conflict with skills.sh — they sit at
different layers:

- **skills.sh:** distribution and registry. Resolves
  `owner/repo` to a fetchable artefact and ships it into the
  harness's expected location.
- **`anchor add`:** installer for OIP-shaped extensions specifically,
  with Anchor-specific MCP wiring and project scope.
- **OIP `agent` block:** the wire format describing what an extension
  contributes to an agent's briefing.

Two real integration opportunities (a spike-then-decide):

1. **Format compatibility.** If skills.sh standardises on a markdown
   file shape (frontmatter + body), the OIP `agent.skill_path` content
   should follow it so a single skill file is publishable to both. If
   they diverge, a future `oip.convert --to=skills-sh` could bridge.

2. **`anchor add skills.sh:<owner>/<repo>`.** Parse a `skills.sh:` ref
   prefix to fetch from their registry. Trivial once their CLI / API
   is documented.

Neither is in v0.3. Track them as follow-ups after we ship `anchor add`
and have a stable surface to integrate against.

## Open questions

- **Per-extension venv vs shared.** Per-extension is cleaner for
  conflict isolation but uses more disk. Shared is leaner but couples
  extensions to a single dependency resolution. Suggest start
  per-extension; revisit if real-world install volumes hurt.
- **Entry-point convention name.** `oip.producers` is the proposed
  Python entry-point group. Coordinate with the OIP repo before
  shipping so third parties know what to declare.
- **GitHub Releases vs git clone.** For `github:` refs, do we clone or
  download the release tarball? Releases are smaller and version-
  pinned; cloning gives full git provenance. Suggest tarball for
  tagged refs, clone for `@HEAD` or commit-pinned.
- **`anchor upgrade` policy.** Always check vs only on user request?
  Default to "report but don't auto-upgrade" matches the OSS Renovate
  pattern.
- **Authentication.** Private PyPI packages, private GitHub repos,
  authenticated HTTP. Out of scope for v0.3; users with private deps
  pre-install via their own toolchain and `anchor add ./path`.
- **Telemetry.** None. The lockfile is enough.

## Phasing

| Phase | What |
|---|---|
| **v0.3** | `anchor add <ref>` for `pypi:`, `github:`, `https://`, and local paths. Project-local default. `--global` opt-in. Lockfile per scope. MCP wiring via independent entries. `anchor remove` + `anchor list` + `anchor show`. |
| **v0.3.1** | `anchor upgrade [name]` + `anchor sync` from lockfile. The "share a project, every collaborator gets the same extensions" flow. |
| **v0.4** | npm source if there's demand. Possibly per-extension MCP proxying if independent entries start fighting. `anchor add skills.sh:...` once their format is verified. |
| **v0.5+** | Curated discovery index ("known good" community extensions). Eventually `oip add` ships and `anchor add` becomes a thin wrapper over it. |

## What this proposal does *not* yet implement

- Any code. This is the contract; the implementation follows in
  separate PRs that each tackle one ref form.
- npm source (deferred to v0.4).
- `oip add` (separate OIP-side proposal, deferred).
- Per-extension MCP proxying (independent entries first; proxy is a
  fallback if collisions become real).
- A registry-style discovery layer.

## Test plan (when implemented)

- `anchor add` for each ref form against a fixture producer that
  ships an OIP-compliant manifest with a known `agent` block.
- `anchor add` failure paths: malformed manifest, missing
  `manifest.json`, network failure, name already registered.
- `anchor remove` cleans up the venv + the MCP entry + the lockfile
  entry.
- `anchor list` reports scope + source correctly across project,
  global, and bundled.
- Cold project: `anchor add` without `.anchor/` prints the friendly
  error and exits 0 without writing.
- Idempotent re-install: `anchor add foo` then `anchor add foo` is a
  no-op with a clear "already at this version" message.

---

*Last updated: 2026-05-28. Counter-proposals welcome.*
