# Proposal: Agent skill contract for OIP extensions

**Status:** draft, not yet implemented
**Target:** v0.3
**Owners:** Christoffer Björkskog, Lamin Jatta
**Depends on:** PR #25 (skill composer foundation)

## Relationship to OIP

The `agent` block extends the OIP manifest schema. The OIP repo at
<https://github.com/Novia-RDI-Seafaring/OIP> currently specifies
`producer`, `produces`, `invocation`, and `ui_hints`. Agent skills
are a natural fourth dimension of how an extension is consumed —
visual via `ui_hints`, programmatic via `invocation`, semantic via
`produces`, and narrative via `agent`.

**ANCHOR's Python code does not currently depend on an `oip`
package.** We treat manifests as plain JSON dicts and do minimal
validation (`oip_version` + `producer` keys must exist). That is
intentional for v0.3:

- It keeps ANCHOR's release cycle decoupled from OIP's while both
  projects are pre-1.0.
- It tolerates slightly-malformed third-party manifests.
- It adds no Python dependency.

The cost is silent drift between our reading of the schema and the
canonical OIP one. The sequenced fix:

1. **Now** (this proposal): document the `agent` block as a JSON
   shape. No Python type coupling.
2. **Next**: introduce a small internal Pydantic model under
   `src/anchor/core/oip.py` that mirrors the OIP spec plus this
   `agent` extension. Replaces inline validation with
   `OipManifest.model_validate(data)`. Catches typos at
   `extensions add` time with clear error messages. No external
   dep yet — just our tracking of the spec, kept manually in sync.
3. **Later**, once the OIP repo ships a stable Python package
   (`oip>=1.0`): replace our internal model with `from oip import
   Manifest`, and upstream the `agent` block schema to OIP itself
   so it's part of the standard, not an ANCHOR convention. Other
   OIP consumers benefit.

This proposal targets step 1.

## Why this exists

ANCHOR's bundled extensions can contribute a `skill.md` snippet that
gets composed into the agent-facing SKILL.md. A third-party OIP
producer should be able to do the same so that an agent operating
against `anchor + transcribe-tool + your-custom-thing` sees one
coherent set of instructions, not three disconnected systems.

The composition is mechanical. What this spec defines is the
**contract** every contributing extension follows: where the skill
text lives, what it must contain, what it must not contain, and what
agents reading the composed result can rely on.

## The `agent` block in the OIP manifest

Existing OIP manifests carry `producer`, `produces`, `invocation`,
`ui_hints`. This proposal adds an optional `agent` block:

```json
{
  "oip_version": "0.1",
  "producer": { "name": "anchor-transcribe", "...": "..." },
  "produces": { "...": "..." },
  "invocation": { "...": "..." },

  "agent": {
    "spec_version": "1",
    "skill_path": "skills/skill.md",
    "tool_skills_dir": "skills/tools/"
  }
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `agent.spec_version` | yes | `"1"` for this spec. Lets ANCHOR refuse to compose skills that follow a future spec it doesn't understand yet. |
| `agent.skill_path` | one-of | Filesystem path to a markdown file, relative to the manifest's directory. |
| `agent.skill` | one-of | Inline markdown string. Mutually exclusive with `skill_path`. |
| `agent.tool_skills_dir` | no | Filesystem directory containing one `.md` per MCP tool. Relative to the manifest. |

Either `skill_path` or `skill` must be present for the extension to
contribute. An extension may omit the `agent` block entirely; it then
shows up in `anchor extensions list` but contributes nothing to the
composed SKILL.md.

## The contract for the skill content

This is the AX-specific part — the rules a skill file follows so the
composed SKILL.md stays coherent and the receiving agent's judgment
isn't replaced by a flowchart.

### Required structure

```markdown
## `<extension-name>` — short one-line summary

Two-sentence paragraph: what the extension does, when an agent
would invoke it.

### Tools

- `tool_one(args)` — one-line description.
- `tool_two(args)` — one-line description.

### Typical situation

A short paragraph (not a numbered procedure) describing the shape of
the situation the agent will find itself in, and naming the tools to
reach for. Trust the agent to compose them.

### Common errors

- `<code> / <name>` → what to try next.
```

The top heading is `##` (the composed SKILL.md uses `#` for the
overall title). Subsections use `###`.

### Hard constraints

Enforced by a linter (CI failure if violated):

| Constraint | Limit |
| --- | --- |
| Total length of a single extension's skill (incl. tool snippets) | 500 words |
| Examples per tool | 3 |
| "Don't call this when..." entries per tool | 3 |
| Numbered procedural lists (`1. do X; 2. do Y; 3. then Z`) | **0** in skill bodies |
| Required frontmatter at the top of the composed file | YAML with `name`, `description` |

### Soft guidance

These are the rules that catch over-specification in code review:

- **Active voice.** "Use this when..." not "This skill should be
  activated when...".
- **Situations, not procedures.** Describe the shape of when an
  agent would invoke the tool. Don't enumerate the order of steps.
- **Concrete examples, not exhaustive ones.** Two examples that span
  variation beat eight that cover every case.
- **Negative space is small.** One or two "don't call this when"
  entries; if there are five, the tool is doing too much.
- **No "the agent will..." or "the system will..."**. You're
  writing *to* the agent. Address it directly: "you".

### Anti-patterns the linter rejects

Real examples from drafts that have failed review:

- **Step-list of imperatives:**
  > 1. First, call `list_documents()`.
  > 2. Then, check if the slug exists.
  > 3. Next, call `ingest_pdf()` if it doesn't.
  > 4. After that, call `get_gold_regions()`.

  Rewrite: *"Check `list_documents()` first; if the slug isn't there,
  `ingest_pdf()`; then `get_gold_regions()` returns the structured
  output."*

- **Enumerated edge cases:**
  > Don't call this when the user has already ingested the PDF, or
  > when the slug is empty, or when the file path is relative, or
  > when the file is over 200MB, or when the user is offline...

  Rewrite: *"Don't re-ingest existing slugs. The tool validates the
  rest; let it."*

- **"The agent will..." voice:**
  > The agent will then take the result and pass it to the next tool,
  > after which the agent will...

  Rewrite: *"Pass the result to `<next-tool>`."*

## How ANCHOR composes the third-party skill

At install / serve / `anchor doctor` time:

1. Read core.md (always present).
2. Read canvas.md (always present).
3. For each bundled extension (declared in `_BUNDLED_EXTENSIONS`),
   read its `skill.md` via package data.
4. For each registered OIP manifest (in the system or project
   producer directories), check for an `agent` block:
   - If `agent.skill` is inline, append it.
   - If `agent.skill_path` is set, resolve relative to the manifest
     file's directory and append.
   - If neither, skip silently — the extension contributes no
     agent-facing text.
5. Concatenate in order: core → canvas → bundled extensions →
   third-party extensions.
6. The composed result is written to `~/.claude/skills/anchor/SKILL.md`
   on install, and served from `anchor://help` at runtime.

Third-party extensions thus extend the agent's view of the system
the same way they extend the user's view via the canvas — through a
declarative manifest, without anyone modifying ANCHOR's code.

## Linter behaviour

A future CI workflow (`anchor lint-skills` or similar):

- Walks every contributing skill file in the wheel + the producers.d
  manifests it can discover at lint time.
- Checks each against the constraints above.
- Reports per-file findings; fails the run if any file violates a
  hard constraint.
- Soft-guidance violations report as warnings without failing.

The linter is a separate PR; this proposal just defines what it
should check.

## Open questions

- **Cross-version compatibility.** What happens when a third-party
  extension declares `spec_version: 2` and ANCHOR only supports `1`?
  Suggested: skip the extension's skill, log a warning visible via
  `anchor doctor`, continue.
- **Tool-level skill files.** The `tool_skills_dir` field is in the
  spec but the composer doesn't read tool-level files yet. Defer to
  the per-tool-skill PR.
- **Skill discovery for extensions installed as Python packages.**
  Some OIP producers will ship as Python wheels with their own
  package data. Should the manifest's `skill_path` resolve via
  `importlib.resources` against the package name, in addition to
  filesystem-relative? Defer to the bundled-as-pip-package PR.
- **Internationalisation.** Multi-language skills aren't in v0.3.
  English is the only target. The frontmatter could add `lang: en`
  if we ever need to compose per-locale SKILL.md.

## What this proposal does *not* yet implement

- The composer extension that walks third-party manifests
  (separate PR; this one defines the data shape only).
- The linter (separate PR).
- The `agent` block on the bundled extensions' Python manifests
  (separate PR; the bundled extensions still ship skill files via
  package data today, and that's fine).
- The `tool_skills_dir` reading.

This is the contract. The wiring follows.

---

*Last updated: 2026-05-28. Counter-proposals welcome.*
