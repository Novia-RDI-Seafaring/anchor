# Publishing Anchor releases

This file documents how to ship a new `anchor-kb` release to PyPI.
After the first manual publish, every subsequent release is automated:
push a `v*` tag, GitHub Actions does the rest.

## One-time setup

### 1. Reserve the name on PyPI (manual, ~5 minutes)

You need a PyPI account with **two-factor authentication enabled** (a
hard requirement for new uploads since 2024). Sign in at
<https://pypi.org/account/login/>.

From this repo root, with the working tree clean and on the tag you
want to release (start with `v0.2.0`):

```bash
# Build the frontend bundle (the wheel force-includes it)
pnpm --dir web install --frozen-lockfile
pnpm --dir web build

# Build wheel + sdist
uv build
# → dist/anchor_kb-0.2.0-py3-none-any.whl
# → dist/anchor_kb-0.2.0.tar.gz

# Publish. uv will prompt for a PyPI API token.
# Create one at: https://pypi.org/manage/account/token/
# Scope: "Entire account" for the first publish, then narrow to
# "Project: anchor-kb" for subsequent ones.
uv publish
```

After the first publish, `pip install anchor-kb` and `uv tool install
anchor-kb` both work globally.

### 2. Configure PyPI trusted publishing (no token needed afterwards)

This is the modern PyPA-recommended pattern: GitHub Actions
authenticates to PyPI using OIDC, no API token sits in the repo or in
secrets storage.

On PyPI:

1. Go to <https://pypi.org/manage/project/anchor-kb/settings/publishing/>
2. Add a trusted publisher with:
   - **Owner:** `Novia-RDI-Seafaring`
   - **Repository name:** `anchor`
   - **Workflow filename:** `release.yml`
   - **Environment name:** `pypi`
3. On GitHub: repo → Settings → Environments → New environment → name
   it `pypi`. Optionally add required reviewers so a release pause for
   approval before publishing.

After this, the `release.yml` workflow can publish without any
PyPI credentials in the repo.

## Releasing a new version

Once the setup above is done, releases are tag-driven:

```bash
# 1. Update version in pyproject.toml + CHANGELOG.md
# 2. Commit those changes
git add pyproject.toml CHANGELOG.md
git commit -m "release: v0.2.1"

# 3. Tag the commit
git tag v0.2.1 -m "v0.2.1"

# 4. Push the commit + tag
git push origin main
git push origin v0.2.1
```

The `release.yml` workflow picks up the tag push, runs the full test
suite (Python + web), builds the frontend bundle into the wheel,
publishes to PyPI via OIDC, and creates a GitHub Release with the wheel
attached.

## Verifying a release

After the workflow finishes (~5 minutes), confirm:

```bash
# PyPI page is live
open https://pypi.org/project/anchor-kb/

# Fresh install from a throwaway venv works
uv run --isolated --with anchor-kb anchor version
# → 0.2.1

# GitHub Release shows up
gh release view v0.2.1
```

## Rolling back

PyPI **does not allow re-uploading a version**. If a release is broken,
**yank** it (still discoverable in the API but not installed by default)
and ship a patch:

```bash
# Yank the bad version
twine yank anchor-kb 0.2.1 --reason "broken frontend bundle"

# Ship a patch
# Bump pyproject.toml to 0.2.2, update CHANGELOG, tag v0.2.2, push.
```

Hard-deletion is only available within 72 hours of upload via the PyPI
web UI, and only for projects with a single release.

## Version policy

Anchor follows [SemVer](https://semver.org/spec/v2.0.0.html):

- **MAJOR** (`1.0.0`): public API breaking changes. The Python import
  surface `import anchor.*`, the on-disk state.json / events.jsonl
  schema, the HTTP endpoint shapes, and the MCP tool contracts are all
  part of the public API.
- **MINOR** (`0.X.0`): backwards-compatible features.
- **PATCH** (`0.0.X`): backwards-compatible bug fixes.

Pre-1.0, MINOR bumps may include breaking changes if they're clearly
called out in CHANGELOG. Once we hit 1.0, MAJOR bumps are the only path
for breaks.

## Frontend on npm — deferred

The `web/` React app is **not** published to npm. The canvas isn't
designed as an embeddable library; it talks directly to specific
backend event shapes, and exposing it without a stabilised public
contract would be a backwards-compat trap. Revisit once the MCP event
protocol carries a version field and we've defined the canvas's
embedding API.
