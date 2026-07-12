# ADR 0001: Execute external OIP producers through an isolated gateway

- Status: accepted
- Date: 2026-07-13

## Context

ANCHOR discovers bundled, system, and project OIP manifests. Bundled producers
run in the ANCHOR process because they ship in the same reviewed wheel.
Registered third-party manifests name executable MCP stdio commands. Importing
third-party code into ANCHOR would collapse the trust seam, while asking every
harness to configure each producer would fragment the tool surface and weaken
CLI, HTTP, and MCP parity.

## Decision

ANCHOR uses a process-isolated External Producer Gateway with a small
`catalog / call / close` interface.

1. Registration and execution authorization are separate human actions.
   `anchor extensions add` stores a discoverable manifest. `anchor extensions
   enable` creates an adjacent `<producer>.enabled` marker.
2. Enable and disable are CLI-only. MCP and the unauthenticated HTTP server
   cannot authorize executable code.
3. Only `invocation.kind = "mcp-stdio"` is executable. ANCHOR passes the
   manifest command and argument array directly to the MCP SDK without a shell.
4. Each enabled producer runs in its own child process. ANCHOR never imports
   its Python, JavaScript, or native package code.
5. Processes start lazily when a catalog or call needs them. One worker task
   owns each MCP session from startup through shutdown.
6. External tools are exposed as `<tools_namespace>.<remote_tool_name>`.
   Namespace collisions, malformed invocation fields, and ANCHOR-owned tool
   name collisions fail closed.
7. Project manifests override system manifests with the same producer name.
   A registration fingerprint rebuilds a cached gateway when a manifest or
   `.enabled` marker changes, so no server restart is required.
8. Catalog and call operations have CLI, HTTP, and MCP surfaces. Runtime
   diagnostics join the shared extension-status payload.

## Consequences

- Third-party failures do not stop bundled extensions or other producers.
- Producer stderr and process lifetime remain outside the ANCHOR core.
- A user must review and enable a registered producer before ANCHOR executes
  it, including manifests installed before this feature existed.
- Dynamic MCP tool discovery may start enabled producer processes.
- HTTP callers can invoke enabled tools because the server is loopback-only by
  default and registration was authorized locally. Exposing the HTTP server to
  a network still requires an authenticated reverse proxy.
- Remote MCP transports, producer-supplied environment variables, working
  directories, and in-process plugin imports remain unsupported.

## Rejected alternatives

- Harness-owned composition duplicates configuration across Codex, Claude
  Code, and OpenCode and removes a consistent CLI/HTTP call surface.
- HTTP-only producers narrow OIP around one transport and require every local
  producer to run a network server.
- In-process package loading gives a manifest authority to execute inside the
  ANCHOR process and is not accepted.
