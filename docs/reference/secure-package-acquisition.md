# Secure extension package acquisition

!!! warning "Design only"
    Package acquisition is not implemented. Today, a human registers a
    reviewed OIP manifest with `anchor extensions add` and separately enables
    it. This design records the security contract for a future installer.

The future installer lets a human acquire, inspect, install, register, remove,
and reproduce an external OIP producer without allowing an agent or the
unauthenticated HTTP server to fetch and execute packages.

Acquisition and execution authorization remain separate:

1. `install` acquires immutable artifacts, validates a static manifest,
   creates an isolated runtime, writes a lock record, and registers it.
2. `enable` remains the explicit authorization to execute the producer.

An installed producer is inert until a human enables it.

## Security boundary

- Acquisition is available through the local CLI only.
- MCP, HTTP, canvas actions, intents, and manifests cannot install, upgrade,
  remove, or enable packages.
- Initial Python support accepts wheels only. Source distributions and build
  backends are rejected because they can execute package-controlled code.
- Every package and dependency has an exact version and SHA-256 digest before
  installation starts.
- Installation uses a local wheelhouse with network access disabled.
- Manifest discovery reads packaged JSON without importing package code.
- Registration never enables execution.
- Deletion targets are revalidated under the selected installation root.
- ANCHOR never imports installed producer code. Execution remains isolated
  behind the external MCP gateway.

## Proposed CLI

```text
anchor extensions install <spec> [--scope project|system]
                              [--sha256 <digest>] [--dry-run] [--yes]
anchor extensions uninstall <name> [--scope project|system] [--yes]
anchor extensions installed [--scope project|system|all]
anchor extensions verify <name> [--scope project|system]
anchor extensions sync [--scope project|system] [--dry-run] [--yes]
```

Project scope is the default only when a project resolves. There is no silent
fallback to system scope. The CLI prints the complete plan and asks for human
confirmation before persistent writes. `--yes` is local CLI automation, not a
capability exposed to agents.

## Initial sources

Phase 1 supports immutable local and PyPI wheel references:

```text
./producer-1.2.3-py3-none-any.whl
pypi:producer==1.2.3
```

Bare names, ranges, `latest`, source distributions, editable installs, Git
branches, direct HTTP manifests, npm packages, and private registries are
deferred. Each requires a separate provenance, authentication, and mutability
policy.

Dependency resolution downloads wheels into quarantine. The operator confirms
the exact names, versions, origins, sizes, and hashes. A later `sync` accepts
only artifacts matching the lock hashes.

## Static package contract

A producer wheel contains one declared `oip-manifest.json`. Acquisition reads
the wheel archive and distribution metadata without importing Python code.
The exact metadata key must be standardized upstream before ANCHOR implements
it.

Validation checks that:

- Wheel filename, metadata name, version, and request agree.
- Exactly one declared OIP manifest exists.
- The manifest validates against the released canonical OIP schema.
- The producer name is portable and does not collide at the selected scope.
- The ANCHOR version supports every invocation field.
- Archive paths are relative, unique after normalization, and within size and
  entry-count limits.

## Storage

Project scope keeps a portable lock at the project root and runtime files
under `.anchor_data`:

```text
<project>/
|-- anchor.extensions.lock
`-- .anchor_data/
    `-- oip/
        |-- packages/<producer>/<lock-id>/
        |   |-- env/
        |   `-- wheelhouse/
        `-- .oip/producers.d/<producer>.json
```

Registration continues to use the existing project discovery path
`.anchor_data/.oip/producers.d/`. System scope uses the documented XDG config
and data roots.

The lock contains source identifiers, exact versions, artifact filenames,
SHA-256 hashes, the manifest hash, and invocation kind. It contains no
credentials, tokens, timestamps, temporary paths, or host-specific values.

## Install transaction

1. Resolve scope and containment roots.
2. Acquire wheels into a new quarantine directory without executing them.
3. Validate archive safety, metadata, static manifest, and hashes.
4. Resolve wheel-only dependencies and freeze the complete plan.
5. Print the plan and stop here for `--dry-run`.
6. Obtain confirmation unless local CLI automation supplied `--yes`.
7. Create a fresh per-producer virtual environment in staging.
8. Install from the wheelhouse with indexes and network disabled.
9. Verify installed files and executable containment without launching it.
10. Write a normalized registration manifest.
11. Atomically replace package storage, registration, and lockfile.
12. Leave execution disabled and print the separate enable command.

Failures remove staging and preserve the previous registration and lock.

## Uninstall and verification

Uninstall disables execution first, closes the live gateway client, validates
every target, removes only locked package and registration paths, and updates
the lock atomically. It never removes bronze, silver, gold, canvases, events,
or producer output data.

Offline verification checks lock syntax, retained artifact hashes,
distribution metadata, registered manifest equality, executable containment,
and enablement state.

Dynamic third-party Python loading remains deliberately out of scope. Package
acquisition supplies isolated MCP processes; it does not create an in-process
plugin system.
