# OIP vNext invocation contract

!!! warning "Draft contract"
    This page is an ANCHOR proposal for upstream OIP review. It is not part of
    canonical OIP 0.2 and is not implemented by ANCHOR. Current releases
    continue to reject these fields.

The proposal defines portable invocation contracts for local and remote MCP
producers. It makes transport, working-directory resolution, environment
inheritance, and authentication explicit so independent OIP consumers can
behave consistently.

The upstream OIP repository must own the final schema and version. ANCHOR will
adopt the contract only after the canonical schema, validator, examples, and
conformance tests are released.

## Proposed invocation union

`invocation` becomes a closed union selected by `kind`. Unknown fields and
unknown kinds remain errors.

### Local MCP over stdio

```json
{
  "invocation": {
    "kind": "mcp-stdio",
    "command": "producer-mcp",
    "args": ["--stdio"],
    "tools_namespace": "producer",
    "cwd": {
      "base": "manifest",
      "path": "workers/pdf"
    },
    "environment": {
      "inherit": ["PATH", "PRODUCER_API_KEY"],
      "set": {
        "PRODUCER_MODE": "batch"
      }
    }
  }
}
```

Required fields are `kind`, `command`, and `tools_namespace`. `args` defaults
to an empty array. Consumers launch `command` directly with the argument
array. Shell parsing, interpolation, command substitution, and response files
are outside the contract.

### Remote MCP over Streamable HTTP

```json
{
  "invocation": {
    "kind": "mcp-http",
    "url": "https://producer.example/mcp",
    "tools_namespace": "producer",
    "authorization": {
      "kind": "oauth"
    }
  }
}
```

`authorization.kind` is `none` or `oauth`, defaulting to `none`. Manifests
never contain bearer tokens, cookies, client secrets, or arbitrary request
headers. Credentials belong to the consumer's secure credential store.

Non-loopback endpoints require HTTPS. A consumer may use MCP's documented
backwards-compatible negotiation for an older server, but the manifest still
declares `mcp-http`.

## Working directory

`cwd` is an object with a base and a relative path:

```json
{ "base": "manifest", "path": "workers/pdf" }
```

Allowed bases are:

- `manifest`: directory containing the registered manifest.
- `project`: root of the active OIP consumer project.

The path defaults to `.`. Absolute paths and parent traversal are invalid.
Consumers resolve symlinks and reject a result outside the selected base. A
consumer without a project concept reports `project` as unsupported instead
of choosing a different directory.

## Environment

The environment object is closed:

```json
{
  "inherit": ["PATH", "PRODUCER_API_KEY"],
  "set": { "PRODUCER_MODE": "batch" }
}
```

- `inherit` explicitly names parent variables and defaults to `[]`.
- `set` contains non-secret literal strings and defaults to `{}`.
- A name cannot occur in both fields.
- Names use `[A-Za-z_][A-Za-z0-9_]*`.
- Consumers start from a documented minimal platform environment, not the
  complete parent environment.
- A requested inherited variable that is absent is a startup error.

The manifest declares secret names, never secret values.

## Remote security

An `mcp-http` consumer must:

1. Require the normal human producer-enablement decision.
2. Display the normalized endpoint origin before the first connection.
3. Apply network-egress and private-address policy before and after DNS
   resolution and after redirects.
4. Refuse cross-origin redirects unless the user authorizes the new origin.
5. Keep OAuth tokens out of manifests, lockfiles, logs, and tool results.
6. Use a conforming MCP client for sessions and protocol negotiation.

These requirements build on the MCP
[transport](https://modelcontextprotocol.io/specification/draft/basic/transports)
and
[authorization](https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization)
contracts.

## Compatibility and rollout

Existing OIP 0.2 `mcp-stdio` manifests retain their current behavior. ANCHOR
will implement the proposal in this order:

1. Upstream the closed schema and conformance tests.
2. Release a canonical OIP version.
3. Extend ANCHOR's manifest validator and invocation model.
4. Add stdio and HTTP connectors behind the external producer gateway.
5. Add CLI diagnostics and installed-tool smoke tests.

Dynamic Python imports are not included. Third-party producers continue to
run out of process through MCP.
