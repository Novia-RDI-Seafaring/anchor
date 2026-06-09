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
    #: One-line caveat shown when this provider is chosen.
    note: str = ""


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        key="local",
        label="Local only",
        zone="on-host · nothing leaves the network",
        does_vision=False,
        base_url_required=False,
        note="Bronze/silver + local-embedding search. No gold regions (those need a vision model).",
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
        available=False,
        note="Config is recorded now; the Azure endpoint client lands in #48.",
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
