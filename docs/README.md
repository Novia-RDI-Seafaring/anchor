# Anchor Documentation

This directory is the public documentation index for the repository.

## Public Docs

- [Project README](../README.md) - setup, usage, runtime commands, and limits.
- [Backend README](../backend/README.md) - API service, storage layout, and backend setup.
- [Agent README](../backend/src/agent/README.md) - current agent tools and canvas behavior.
- [Ingestion README](../backend/src/ingestion/README.md) - document ingestion modules.
- [Ingestion pipeline](../backend/src/ingestion/PIPELINE.md) - bronze, silver, and gold data flow.
- [Evaluation notes](../backend/evals/README.md) - local evaluation scripts and fixtures.
- [Contributing](../CONTRIBUTING.md) - contribution workflow and local checks.
- [Security](../SECURITY.md) - reporting process and local deployment assumptions.

## Documentation Rules

Keep public documentation tied to code that is wired into the runtime.

Before adding a new doc link here, make sure the target file is tracked in Git
and useful to a new local user. Mark dormant or experimental modules as dormant
until they are registered in the live runtime.
