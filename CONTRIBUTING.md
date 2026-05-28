# Contributing to Anchor

Thanks for your interest. This file describes how to contribute code,
docs, or bug reports. The repo-level conventions for coding agents
live in [`AGENTS.md`](./AGENTS.md); both files agree.

## Reporting bugs and security issues

- **Regular bug or feature request:** open a GitHub issue using one
  of the templates (bug, feature, docs, task). Each template is a
  short form; filling it in takes a minute and gives the next person
  (human or agent) what they need to pick the work up.
- **Security vulnerability:** do NOT open a public issue. Use the
  GitHub private advisory flow described in
  [`SECURITY.md`](./SECURITY.md). Encrypted, audit-trailed,
  coordinated disclosure.

## Filing and claiming issues

The authoritative task list is **GitHub Issues** in this repo, with
the **Anchor roadmap** Project as the shared board across humans
and coding agents.

### Filing

1. <https://github.com/Novia-RDI-Seafaring/anchor/issues/new/choose>
2. Pick the template that matches: bug, feature, docs, or task.
3. Add an `area:*` label (`canvas`, `ingest`, `cli`, `mcp`) so it
   shows up in the right board view.
4. If the scope is crisp and you'd be happy for a coding agent to
   pick it up unattended, add `agent-ready`. If architectural
   decisions are still open, add `needs-design` instead.

### Claiming

Self-assign before you start so two people don't pick up the same
thing:

```bash
gh issue edit <n> --add-assignee @me
```

Move the Project card to **In progress** at the same time. When the
PR is up, write `Closes #<n>` in the body — GitHub closes the issue
and moves the card to **Done** on merge.

### Proposals vs issues

Default to an issue. Open a `docs/proposals/*.md` PR only when the
work is cross-cutting, spans multiple PRs, and is the kind of thing
you'd want to re-read in a year. Everything else is an issue.

## Development setup

```bash
git clone https://github.com/Novia-RDI-Seafaring/anchor
cd anchor
uv sync --extra dev          # Python deps + pytest, ruff, import-linter
pnpm --dir web install       # Frontend deps
```

Run the tests:

```bash
uv run --extra dev pytest
uv run --extra dev lint-imports
pnpm --dir web test
pnpm --dir web exec tsc --noEmit
```

Run the app in dev mode:

```bash
uv run anchor serve            # backend on http://127.0.0.1:8002
pnpm --dir web dev             # Vite HMR on http://localhost:5173
```

Default data dir is `~/anchor-data`. Override by passing `--data-dir`
consistently to commands and agent installers.

## Workflow

The repo is **trunk-based**: one long-lived branch (`main`), short-lived
feature branches off it, every change through a pull request. There is
no `develop` / `dev` branch.

### 1. Branch

Name the branch by what the change is:

| Prefix | For |
| --- | --- |
| `feat/<topic>` | new functionality |
| `fix/<topic>` | bug fixes |
| `docs/<topic>` | docs, README, CHANGELOG, asset prose |
| `chore/<topic>` | tooling, CI, dependencies, plumbing |
| `refactor/<topic>` | internal restructuring without behaviour change |
| `test/<topic>` | tests only |

### 2. Make the change

Keep PRs focused. One coherent change per PR is easier to review and
easier to revert if needed.

For backend changes, run `uv run --extra dev pytest` locally.
For frontend changes, run `pnpm --dir web test` and
`pnpm --dir web exec tsc --noEmit`.
For changes that touch the import boundaries, run
`uv run --extra dev lint-imports`.

### 3. Commits and PR title

Use [Conventional Commits](https://www.conventionalcommits.org/) for
both commit messages and the PR title:

- `feat: short description`
- `fix(scope): short description`
- `docs(readme): short description`
- `chore(deps): bump X from Y to Z`
- `refactor: short description`

The release pipeline groups changelog entries by these prefixes.

### 4. Open the PR

Target `main`. Fill in the template. CI must pass before the PR can
merge:

- `python` — pytest + import-linter
- `web` — vitest + tsc
- `supply-chain audit` — Dependency Review + pnpm audit
- `analyze (python)`, `analyze (javascript-typescript)` — CodeQL

If your PR ends up behind `main` while it's waiting for review, use
**`gh pr update-branch <pr-number>`** (or click "Update branch" in
the GitHub UI). This merges main into the PR via the GitHub API and
re-runs CI on the merge commit. **Do not rebase and force-push** —
the discipline is to keep the PR's commit history stable so review
comments stay attached to the right commits.

### 5. Merge

Squash-merge is the default. The squash collapses the PR's commits
into one Conventional-Commit entry on `main`, which is what the
changelog and release notes ingestion expects.

```bash
gh pr merge <number> --squash --delete-branch
```

## What never goes on a pushed branch

- `git push --force` or `--force-with-lease`
- `git reset --hard` followed by push
- `git rebase main && git push --force-with-lease` to update a PR

Branch protection blocks the worst cases on `main`. The rules above
also apply to feature branches that have an open PR — the CI runs,
review comments, and audit trail depend on commit hashes staying
stable. If a rewrite is genuinely needed, get explicit OK from a
maintainer first.

## Releasing

Maintainers only. See [`PUBLISHING.md`](./PUBLISHING.md). Short
version: bump `pyproject.toml` and `CHANGELOG.md`, commit on a
release PR, merge, then tag `vX.Y.Z` and push the tag. The release
workflow handles the PyPI publish (OIDC trusted publishing, no token
in the repo) and the GitHub Release.

## Architectural guardrails

- **Hexagonal layering.** `core/` is pure domain (no `httpx`,
  `fastapi`, `openai`, `pymupdf`, ...). `infra/` implements ports.
  `adapters/` (HTTP, MCP, CLI) wires them together. `import-linter`
  enforces the contract in CI.
- **Adapter parity.** Every new user-visible operation must reach
  HTTP, MCP, and CLI in the same PR. Agents and shell users get
  parity with the UI by construction.
- **Row-level provenance.** Every spec-table row, every gold region,
  carries `page` + `bbox` back to its source. Never strip this.

## Style notes

- **Prose.** Match the voice of the existing README and posters.
  Short sentences. Active second-person. One claim per sentence.
  Periods over em-dashes. Skip marketing intensifiers and bolded
  summary claims.
- **Code comments.** Don't narrate what the code does — well-named
  identifiers handle that. Comments earn their place when they
  capture non-obvious *why*: a hidden constraint, a workaround for
  a specific bug, behaviour that would surprise a reader.

## Questions

Open a discussion at <https://github.com/Novia-RDI-Seafaring/anchor/discussions>
if you have a workflow question or want to propose something that
doesn't fit an issue.
