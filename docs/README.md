# Anchor Documentation

This directory contains developer and system documentation for Anchor UI.

## Structure

- **[agent-guide.md](agent-guide.md)** - Custom nodes, canvas edges, agent capabilities, and CopilotKit integration.
- **[architecture.md](architecture.md)** - Runtime architecture and dormant capability-router notes.
- **[anchor-current-architecture.mmd](anchor-current-architecture.mmd)** - Mermaid diagrams for the runtime flow.
- **[paper/](paper/)** - Academic drafts, templates, figures, and poster material.

---

## Documentation Rules

Keep public documentation tied to the code that is actually wired into the
runtime. A reader should be able to answer:

- what the agent does
- how retrieval works
- how evidence becomes canvas output
- how a fact/spec is grounded to source

Mark dormant or experimental modules as such. Do not describe them as active
behavior until they are registered in the live runtime.
