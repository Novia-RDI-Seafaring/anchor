from __future__ import annotations

import os
import re
from dataclasses import replace
from typing import Any

from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import ModelRequestParameters
from evals.trace_logger import log_event


def _last_user_prompt_index(messages: list[ModelMessage]) -> int | None:
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]
        if getattr(msg, "kind", None) != "request":
            continue
        parts = getattr(msg, "parts", None) or []
        for part in parts:
            if getattr(part, "part_kind", None) == "user-prompt":
                return idx
    return None


def _tool_seen_since(messages: list[ModelMessage], *, since_idx: int, tool_name: str) -> bool:
    for msg in messages[since_idx + 1 :]:
        for part in getattr(msg, "parts", None) or []:
            kind = getattr(part, "part_kind", None)
            if kind in {"tool-call", "builtin-tool-call", "tool-return", "builtin-tool-return"}:
                if getattr(part, "tool_name", None) == tool_name:
                    return True
    return False


def _tool_call_count_since(messages: list[ModelMessage], *, since_idx: int) -> int:
    count = 0
    for msg in messages[since_idx + 1 :]:
        for part in getattr(msg, "parts", None) or []:
            kind = getattr(part, "part_kind", None)
            if kind in {"tool-call", "builtin-tool-call"}:
                count += 1
    return count


def _get_tool_calls_since(messages: list[ModelMessage], *, since_idx: int) -> list[tuple[str, Any]]:
    """
    Extract all tool calls (name + args) made since a given message index.
    Returns list of (tool_name, tool_args) tuples.
    """
    tool_calls = []
    for msg in messages[since_idx + 1 :]:
        for part in getattr(msg, "parts", None) or []:
            kind = getattr(part, "part_kind", None)
            if kind in {"tool-call", "builtin-tool-call"}:
                tool_name = getattr(part, "tool_name", None)
                # Extract args - different providers may store this differently
                tool_args = getattr(part, "args", None) or getattr(part, "arguments", None) or {}
                if tool_name:
                    tool_calls.append((tool_name, tool_args))
    return tool_calls


def _has_redundant_tool_call(tool_calls: list[tuple[str, Any]]) -> bool:
    """
    Check if there are redundant tool calls (same tool with same/similar parameters).
    Returns True if redundancy detected.
    """
    import json
    
    # Group by tool name
    calls_by_tool = {}
    for tool_name, tool_args in tool_calls:
        if tool_name not in calls_by_tool:
            calls_by_tool[tool_name] = []
        calls_by_tool[tool_name].append(tool_args)
    
    # Check for duplicates within each tool
    for tool_name, args_list in calls_by_tool.items():
        if len(args_list) > 1:
            # Compare arguments for similarity
            # Use JSON serialization for deep comparison
            seen_args = set()
            for args in args_list:
                try:
                    # Normalize args to JSON string for comparison
                    args_str = json.dumps(args, sort_keys=True) if isinstance(args, dict) else str(args)
                    if args_str in seen_args:
                        # Found duplicate!
                        return True
                    seen_args.add(args_str)
                except (TypeError, ValueError):
                    # If args can't be serialized, compare as strings
                    args_str = str(args)
                    if args_str in seen_args:
                        return True
                    seen_args.add(args_str)
    
    return False


def _last_user_prompt_text(messages: list[ModelMessage]) -> str | None:
    idx = _last_user_prompt_index(messages)
    if idx is None:
        return None
    msg = messages[idx]
    parts = getattr(msg, "parts", None) or []
    for part in parts:
        if getattr(part, "part_kind", None) == "user-prompt":
            return getattr(part, "content", None)
    return None


_GREETING_RE = re.compile(r"^[a-zA-Z][a-zA-Z\s\.\!\?]{0,24}$")
_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "yo",
    "sup",
    "hiya",
    "good morning",
    "good afternoon",
    "good evening",
}


def _is_greeting(text: str) -> bool:
    s = text.strip().lower()
    if not s:
        return False
    if s in _GREETINGS:
        return True
    # Very short greetings like "hi", "hey", "yo", "hola"
    if len(s) <= 4 and s.isalpha():
        return True
    # "hi!" / "hello." etc (avoid matching real queries)
    if len(s) <= 25 and _GREETING_RE.match(text.strip()) and any(g in s for g in ("hi", "hello", "hey")):
        return True
    return False


def enforce_tools_for_turn(messages: list[ModelMessage], model_request_parameters: ModelRequestParameters) -> ModelRequestParameters:
    """
    Enforce that each user turn triggers KB retrieval before the model can answer with plain text.

    This addresses cases where models ignore the system prompt and answer generically without calling tools.
    """
    if os.getenv("ENFORCE_RAG_TOOLING", "1").strip().lower() in {"0", "false", "no", "n"}:
        return model_request_parameters

    user_idx = _last_user_prompt_index(messages)
    if user_idx is None:
        return model_request_parameters

    user_text = _last_user_prompt_text(messages)
    if user_text and _is_greeting(user_text):
        return model_request_parameters

    retrieval_tools = {"search_knowledge_base", "list_documents", "list_document_toc", "get_section_content", "get_database_status"}
    has_retrieval = any(_tool_seen_since(messages, since_idx=user_idx, tool_name=tn) for tn in retrieval_tools)
    has_render = _tool_seen_since(messages, since_idx=user_idx, tool_name="render_component")
    require_render = os.getenv("ENFORCE_UI_RENDER", "0").strip().lower() in {"1", "true", "yes", "y"}

    # Guard against infinite tool-call loops: if the model has already made several tool calls
    # for this user message but still hasn't called retrieval, stop enforcing and let it answer.
    max_tool_calls = int(os.getenv("ENFORCE_RAG_MAX_TOOL_CALLS", "4"))
    if not has_retrieval and _tool_call_count_since(messages, since_idx=user_idx) >= max_tool_calls:
        try:
            log_event(
                {
                    "type": "rag_enforcement_bailed_out",
                    "reason": "max_tool_calls_exceeded",
                    "max_tool_calls": max_tool_calls,
                }
            )
        except Exception:
            pass
        return model_request_parameters

    # Check for redundant tool calls if prevention is enabled
    if os.getenv("PREVENT_REDUNDANT_TOOLS", "1").strip().lower() not in {"0", "false", "no", "n"}:
        tool_calls = _get_tool_calls_since(messages, since_idx=user_idx)
        if _has_redundant_tool_call(tool_calls):
            # Log the redundancy detection
            try:
                log_event(
                    {
                        "type": "redundant_tool_calls_detected",
                        "tool_call_count": len(tool_calls),
                        "unique_tools": list(set(tc[0] for tc in tool_calls)),
                    }
                )
            except Exception:
                pass
            
            # Force text output to stop the redundant calling
            # The model should provide an answer based on what it already has
            return model_request_parameters

    # Force tool calling until retrieval (or rendering) has happened for this user prompt.
    # If the model has already rendered a component (e.g. for a follow-up), allow text response.
    if not has_retrieval and not has_render:
        return replace(model_request_parameters, allow_text_output=False)
    
    # If require_render is on, and we have neither retrieval nor render, block text.
    if require_render and not has_retrieval and not has_render:
        return replace(model_request_parameters, allow_text_output=False)
        
    return model_request_parameters
