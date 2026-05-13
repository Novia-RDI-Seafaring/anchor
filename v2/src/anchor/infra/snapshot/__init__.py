"""Headless-browser snapshotters — the only infra files allowed to import
playwright. Import lazily where possible so unit tests that don't exercise
the snapshot path don't pay the playwright import tax."""
