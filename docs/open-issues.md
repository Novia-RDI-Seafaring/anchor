# Current open GitHub issues

Snapshot: 2026-10-16 (UTC), queried directly from [Anchor's open issues](https://github.com/Novia-RDI-Seafaring/anchor/issues?q=is%3Aissue%20is%3Aopen). There were **21 open issues** and **0 open PRs**. Main was `3088a28fc5330f2fdadf87448b1062a66296d105`.

This is a dated inventory, not a live board or an assertion that every request still needs code. Categories are coordinator triage based on current issue bodies, labels, ownership and the recorded audits; they do not represent GitHub Project columns. Each issue appears once. Existing assignments take precedence, including #147's design label.

| Category | Open issues |
| --- | ---: |
| Design proposals | 14 |
| Research | 1 |
| Work owned by others / existing assignments | 2 |
| Unresolved defects and technical follow-ups | 4 |
| Total | 21 |

The five explicitly deferred issues are **#222, #223, #380, #375 and #279**. They remain open. Classification alone does not authorize implementation: confirm current need, concrete benefit and scope, then prefer the smallest tested change. Close obsolete, duplicate or unnecessary work only with evidence and the appropriate reason.

## Design proposals (14)

| Issue | Current GitHub assignee | Triage / next step |
| --- | --- | --- |
| [#509: Agents should hear canvas remarks between turns, not only when the user nudges them](https://github.com/Novia-RDI-Seafaring/anchor/issues/509) | Unassigned | Harness wake-up, listening and claim lifecycle need decisions. Browser refresh in PR #533 does not wake an idle agent. |
| [#498: Dragged sections should land as the element they are; infer real tables from table regions](https://github.com/Novia-RDI-Seafaring/anchor/issues/498) | Unassigned | Table/section drop semantics and inference. Recheck what PR #526 already delivers before planning additional work. |
| [#490: Scoped-ask threads: what the mark-up pen does not cover yet](https://github.com/Novia-RDI-Seafaring/anchor/issues/490) | Unassigned | Selection Ask, stale feedback, batch-parent validation and server refresh have landed. Since-ask comparison, result-only presentation and cross-process delivery remain design work. |
| [#403: Mark-up mode as a standalone annotator: own package, MCP server, injectable into any page](https://github.com/Novia-RDI-Seafaring/anchor/issues/403) | Unassigned | Reusable layers and examples largely ship. Separate publishing, injection and extension delivery need a supported consumer and boundary decision. |
| [#401: Ingest Markdown files and URLs, with anchors that point into them](https://github.com/Novia-RDI-Seafaring/anchor/issues/401) | Unassigned | Decide stable Markdown/URL locators, source viewing, drift and trust behavior before implementation. |
| [#380: CLI and MCP resolve different projects from the same directory](https://github.com/Novia-RDI-Seafaring/anchor/issues/380) | Unassigned | Explicitly deferred by the user. Agree project-resolution behavior across CLI and MCP. |
| [#375: feat(canvas): visual primitives for conveying an answer, not just storing one](https://github.com/Novia-RDI-Seafaring/anchor/issues/375) | Unassigned | Explicitly deferred by the user. Choose visual primitives and semantic presentation rules. |
| [#364: Canvas composition: frames, text blocks, layout inside containers, so explaining is not always a tree of cards and arrows](https://github.com/Novia-RDI-Seafaring/anchor/issues/364) | Unassigned | Direction, not a specification. Define frame ownership, container layout and composition behavior. |
| [#353: Canvas editor: primitives (box, text, connector) where Miro/Excalidraw users expect them; drop fixed connector handles on plain shapes](https://github.com/Novia-RDI-Seafaring/anchor/issues/353) | Unassigned | Core editor improvements ship. Remaining primitive/tool organization is design work; PR #529 also changed navigation. |
| [#352: Canvas as the working record of iterative engineering design: delegated work, outcomes and references on the canvas (direction, not spec)](https://github.com/Novia-RDI-Seafaring/anchor/issues/352) | Unassigned | Direction, not a specification. Define how delegated work and outcomes belong on the canvas. |
| [#279: feat(ingest): Unlimited-OCR extractor behind the PdfExtractor port (not locked to Docling)](https://github.com/Novia-RDI-Seafaring/anchor/issues/279) | Unassigned | Explicitly deferred by the user. Decide the alternative OCR engine, runtime and integration contract. |
| [#228: AX: make an env's trust-zone / locality legible so a harness policy reviewer can approve ingest](https://github.com/Novia-RDI-Seafaring/anchor/issues/228) | Unassigned | Agree the machine-readable locality/egress contract; check existing status and policy surfaces before adding another. |
| [#223: Find / embedding-search from the file browser (find-in-folder over docs)](https://github.com/Novia-RDI-Seafaring/anchor/issues/223) | Unassigned | Explicitly deferred by the user. Folder-scoped search depends on the organization design in #222. |
| [#222: File browser: project folders + drag-to-ingest + organize (move without re-ingest) + add/context-menu](https://github.com/Novia-RDI-Seafaring/anchor/issues/222) | Unassigned | Explicitly deferred by the user. Decide folder metadata, organization operations and ingest/drop behavior. |

## Research (1)

| Issue | Current GitHub assignee | Triage / next step |
| --- | --- | --- |
| [#212: Spike: compare gold-extraction quality - harness-driven vs server OpenAI vision](https://github.com/Novia-RDI-Seafaring/anchor/issues/212) | Unassigned | Useful quality measurement, not a default change. Pin corpus, six-dimension rubric, model/prompt versions and comparable cost/latency; the paired study is not complete. |

## Work owned by others / existing assignments (2)

| Issue | Current GitHub assignee | Triage / next step |
| --- | --- | --- |
| [#256: chore(mcp): migrate Anchor MCP adapter to MCP Python SDK v2](https://github.com/Novia-RDI-Seafaring/anchor/issues/256) | Lamboyjat | Assigned to Lamboyjat. Pre-existing SDK v2 work belongs to another harness; coordinate before takeover. Its local worktree contains uncommitted changes. |
| [#147: References store + authoring: make a reference by selecting the source, keep a bibliography, attach to facts](https://github.com/Novia-RDI-Seafaring/anchor/issues/147) | melonkernel | Assigned to melonkernel. Store scope, inline attachment and locator capture also carry needs-design. Preserve existing ownership. |

## Unresolved defects and technical follow-ups (4)

| Issue | Current GitHub assignee | Triage / next step |
| --- | --- | --- |
| [#517: fix(ingest): gold fallback mislabels diagram letters and embeds a false OCR numeral](https://github.com/Novia-RDI-Seafaring/anchor/issues/517) | Unassigned | Unresolved OCR/diagram-context accuracy report. Structural completion does not establish semantic correctness. |
| [#516: fix(ingest): silver table captions inherit unrelated section headings in PX fixture](https://github.com/Novia-RDI-Seafaring/anchor/issues/516) | Unassigned | Unresolved table-caption accuracy report. Geometric heading selection and singleton title/data treatment need verified rules. |
| [#495: Dependabot regenerates web/pnpm-lock.yaml with a stale overrides block, so its PRs fail the frozen install](https://github.com/Novia-RDI-Seafaring/anchor/issues/495) | Unassigned | Hosted Dependabot lockfile/override behavior needs controlled verification. A successful main install does not establish that the bot issue is fixed. |
| [#459: bug: agent-ready guard reports conflicting author trust for a MEMBER issue](https://github.com/Novia-RDI-Seafaring/anchor/issues/459) | Unassigned | Author-trust guard inconsistency remains unproven in cause. A protected workflow change requires a maintainer-authored PR under repository rules. |

GitHub records account assignments, not individual agent sessions. #256 uses the same account as this coordinator but is treated as pre-existing work owned outside this task. An assignee does not prove that a worker is currently running. Useful research and unresolved design are not grounds for an unsupported completed closure.

## Refreshing this inventory

Use the live issue list as the authority. Refresh bodies, labels, assignees and linked PRs before changing a classification or claiming work. Reconcile every currently open issue exactly once and update the snapshot date and counts; do not assume an old issue body reflects features already merged.

```powershell
gh issue list --state open --limit 1000 --json number,title,body,url,labels,assignees,updatedAt
gh pr list --state open --json number,title,url,headRefName,author
```
