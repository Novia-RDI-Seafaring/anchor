"""The AI providers ``anchor init`` can target.

Each entry pairs an operational config (endpoint defaults, which stages it
serves) with the *data zone* it implies — because choosing a provider is
choosing where document content is allowed to go. Local/Ollama keep content on
your network; Azure/custom send it only to the endpoint you name; OpenAI is
public. This registry is the single source of that mapping, shared by the CLI
``init`` and the status surface, so the boundary is described in exactly one
place.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    key: str
    #: Human label shown in the picker.
    label: str
    #: Where document content goes if this provider is chosen — shown to the
    #: user at init time and by the status surface.
    zone: str
    #: True when this provider runs the vision stages (polish + gold regions).
    does_vision: bool
    #: True when the user must supply the endpoint (no sensible default).
    base_url_required: bool
    #: Endpoint used when the user does not override it (Ollama's localhost).
    default_base_url: str | None = None
    #: Suggested vision model / deployment for the picker default.
    default_vision_model: str | None = None
    #: False when the config can be written but the runtime client is not yet
    #: implemented (Azure — see #48). init records the choice and flags it.
    available: bool = True
    #: True when this provider runs with no external egress at all: ingest +
    #: embed call no remote endpoint and model loading is pinned offline. Sets
    #: ``local_only = true`` in the env.toml so the runtime asserts it (see
    #: ``AnchorConfig.local_only`` and ``anchor.infra.models``). Only the pure
    #: ``local`` provider qualifies; ``ollama`` talks to a local *server*, which
    #: is on-host but still a network call.
    local_only: bool = False
    #: One-line caveat shown when this provider is chosen.
    note: str = ""


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        key="local",
        label="Local only",
        zone="on-host · nothing leaves the network",
        does_vision=False,
        base_url_required=False,
        local_only=True,
        note="Bronze/silver + local-embedding search, no egress (run `anchor models prefetch` "
        "once first to work offline). No gold regions (those need a vision model).",
    ),
    Provider(
        key="harness",
        label="Harness agent (no API key)",
        zone="on-host - pages are read by the agent harness you are already running",
        does_vision=False,
        base_url_required=False,
        note="Gold extraction runs through your agent (Claude Code, Codex, ...) via "
        "ingest sessions; where the harness sends page content is governed by the "
        "harness's own provider agreement. No key, no new egress paths.",
    ),
    Provider(
        key="ollama",
        label="Ollama (self-hosted)",
        zone="your machine / LAN · no internet egress",
        does_vision=True,
        base_url_required=False,
        default_base_url="http://localhost:11434/v1",
        default_vision_model="llava",
        note="Offline gold regions via a local vision model.",
    ),
    Provider(
        key="openai",
        label="OpenAI",
        zone="public cloud",
        does_vision=True,
        base_url_required=False,
        default_vision_model="gpt-5.4",
    ),
    Provider(
        key="azure",
        label="Azure OpenAI",
        zone="your Azure tenant / region",
        does_vision=True,
        base_url_required=True,
        note="Use your Azure OpenAI v1 endpoint (https://<resource>.openai.azure.com/openai/v1/) "
        "and the deployment name as the model.",
    ),
    Provider(
        key="custom",
        label="Other OpenAI-compatible endpoint",
        zone="depends on the endpoint — you label the zone",
        does_vision=True,
        base_url_required=True,
        note="vLLM, LM Studio, LiteLLM, Together, Groq, OpenRouter, on-prem gateway, …",
    ),
)

PROVIDERS_BY_KEY: dict[str, Provider] = {p.key: p for p in PROVIDERS}


def get_provider(key: str) -> Provider | None:
    """Look up a provider by key, case-insensitively. None when unknown."""
    return PROVIDERS_BY_KEY.get(key.strip().lower())


#: The one env var that actually carries the endpoint key. A plain
#: OPENAI_API_KEY in the env's .env is ignored (only ANCHOR_* keys propagate),
#: so onboarding messaging must name this exact variable (issue #226).
ANCHOR_KEY_VAR = "ANCHOR_OPENAI_API_KEY"


def no_key_remedy_lines(env_dotenv_path: str | None) -> list[str]:
    """Actionable remedy when gold needs a key but none is configured.

    Names the exact fix: (a) the env's ``.env`` path, (b) that the key MUST be
    ``ANCHOR_OPENAI_API_KEY`` (a plain ``OPENAI_API_KEY`` there is ignored), and
    (c) the offline no-key alternative — switch to the ``harness`` (or ``local``)
    provider and drive the harness ingest tools. Shared by ``anchor check``,
    ``anchor install``, and the MCP ``ingest_pdf`` gold-skip note so the guidance
    reads the same on every surface (issue #226).
    """
    target = env_dotenv_path or "the environment's .env"
    return [
        f"Set the endpoint key named {ANCHOR_KEY_VAR} in {target}",
        "  (a plain OPENAI_API_KEY in that .env is ignored; only ANCHOR_* keys load).",
        "Or run key-free: switch to --provider harness (or local) and drive the",
        "  harness ingest tools (ingest_begin -> ingest_get_page ->",
        "  ingest_submit_page -> ingest_finalize; the agent reads pages, embed is local).",
    ]


def normalize_base_url(provider_key: str | None, url: str) -> str:
    """Repair a pasted endpoint so it points at the right API surface.

    Azure's OpenAI-compatible API lives under ``/openai/v1/``; users routinely
    paste the bare resource URL from the portal, which would 404 every call.
    Append the missing suffix instead of expecting the user to know it. Other
    providers pass through untouched. Shared by ``anchor init`` (at write time)
    and ``anchor check`` (as a repair), so the rule lives in one place.
    """
    url = (url or "").strip()
    if not url or (provider_key or "").lower() != "azure":
        return url
    trimmed = url.rstrip("/")
    if trimmed.endswith("/openai/v1"):
        return trimmed + "/"
    if trimmed.endswith("/openai"):
        return trimmed + "/v1/"
    if trimmed.endswith("/v1"):
        # Bare ``/v1`` is OpenAI muscle memory; Azure serves it under /openai/v1.
        return trimmed[: -len("/v1")] + "/openai/v1/"
    return trimmed + "/openai/v1/"


@dataclass(frozen=True)
class EmbedOption:
    model: str
    label: str
    #: True when embedding *text* is sent to the provider endpoint (egress).
    remote: bool


# Local stays a single bge model on purpose: the in-browser query embedder is
# fixed to bge-small, so a different local model would silently break browser
# search (vector-space mismatch — see #41). The meaningful choice is local-vs-
# remote, surfaced only when an endpoint exists.
LOCAL_EMBED_OPTIONS: tuple[EmbedOption, ...] = (
    EmbedOption("BAAI/bge-small-en-v1.5", "bge-small · 384d · local, no egress", remote=False),
)

REMOTE_EMBED_OPTIONS: tuple[EmbedOption, ...] = (
    EmbedOption("text-embedding-3-small", "text-embedding-3-small · 1536d · sent to your endpoint", remote=True),
    EmbedOption("text-embedding-3-large", "text-embedding-3-large · 3072d · sent to your endpoint", remote=True),
)


def embed_options_for(provider: Provider) -> tuple[EmbedOption, ...]:
    """Embedding choices for a provider.

    The local sentence-transformer model always applies (no egress). Remote
    embeddings are offered only when there is an OpenAI-compatible endpoint to
    send vectors to; ``local``/``ollama`` keep embeddings on the host.
    """
    if provider.key in ("openai", "azure", "custom"):
        return LOCAL_EMBED_OPTIONS + REMOTE_EMBED_OPTIONS
    return LOCAL_EMBED_OPTIONS
