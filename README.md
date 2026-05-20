# Anchor — knowledge-grounded engineering canvas

A canvas your AI agent can drive. Drop a PDF datasheet onto a workspace,
ask the agent for the operating limits, get a grounded spec table where
every value points back to its source page+bbox. Wire those values into
a simulation. **No managed cloud, no vendor lock-in, your data stays on
your laptop.**

> Active development lives in [`v2/`](./v2/). The v2 codebase is a
> hexagonal modular monolith: pure Python core, swappable infra,
> per-protocol adapters (HTTP, MCP, CLI), and a React + Vite frontend.
> It is the supported entry point.
>
> The older code at the repo root (`src/`, `backend/`, `packages/`)
> is the v1 Next.js + Postgres+pgvector stack. It still runs but is
> being retired and should not be the starting point for new work.

## Get started

```bash
cd v2
uv sync
pnpm --filter @anchor/web install
pnpm --filter @anchor/web build

# in two terminals:
uv run anchor serve
pnpm --filter @anchor/web dev
```

Open `http://localhost:5173` (Vite, with HMR) or `http://localhost:8002`
(FastAPI serving the built bundle). Full install + adoption recipes:

- [v2/README.md](./v2/README.md) — install, quick start, CLI reference
- [v2/docs/README.md](./v2/docs/README.md) — six short documents covering architecture, on-disk substrate, OIP, canvas, and the multi-interface story
- [v2/docs/ADOPTION.md](./v2/docs/ADOPTION.md) — harness recipes (Claude Code, Cursor, opencode), Azure / Ollama / vLLM, air-gap notes

## License

Research code. Pending an open-source license commit (Apache-2.0 or MIT).
Ask before redistributing.
