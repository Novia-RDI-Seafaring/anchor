"""Shared types and imports for agent framework."""
from __future__ import annotations

# Standard library
import base64
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from enum import Enum
from functools import wraps
from inspect import Parameter, Signature, signature
from logging import getLogger
from pathlib import Path
from typing import (
    Any, AsyncIterator, Callable, Dict, Generic, Iterator, List, Literal,
    Optional, Sequence, Tuple, Type, TypeVar, Union, get_args, get_origin,
    get_type_hints
)

# Third party
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from rich.console import Console

# pydantic_ai
from pydantic_ai import (
    Agent, AgentRunResult, BinaryContent, ModelRequest, ModelResponse,
    TextPart, ToolCallPart, ToolReturnPart, UserPromptPart
)
from pydantic_ai._run_context import AgentDepsT, RunContext
from pydantic_ai.ag_ui import StateDeps
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import KnownModelName, Model, ModelRequestParameters
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.output import OutputDataT
from pydantic_ai.providers import Provider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import Tool  # type: ignore

# ag_ui
from ag_ui.core import EventType, StateSnapshotEvent  # type: ignore

# Local application
from evals.token_utils import estimate_tokens
from evals.trace_logger import log_event
from .context import get_current_model_id

# =====
# UI Component Types
# =====
class UIComponentType(str, Enum):
  """Types of UI components the agent can request to render."""
  LIST = "list"
  TABLE = "table"
  IMAGE = "image"
  PAGE_PREVIEW = "page_preview"
  MARKDOWN_TABLE = "markdown_table"

class UIComponentData(BaseModel):
  """Data for a UI component to be rendered by the frontend."""
  component_type: UIComponentType = Field(
    description='Type of UI component to render'
  )
  data: Dict[str, Any] = Field(
    description='Component-specific data payload'
  )
  metadata: Optional[Dict[str, Any]] = Field(
    default=None,
    description='Optional metadata about the component'
  )

# =====
# State
# =====
class RAGState(BaseModel):
  """State for RAG-powered conversation."""
  conversation_history: list[dict[str, str]] = Field(
    default_factory=list,
    description='The conversation history',
  )
  current_sources: list[str] = Field(
    default_factory=list,
    description='Sources from the most recent knowledge base query',
  )
  vector_db_status: str = Field(
    default='disconnected',
    description='Status of the vector database connection',
  )
  # UI rendering state
  active_ui_components: list[UIComponentData] = Field(
    default_factory=list,
    description='Active UI components to render with their data'
  )
  render_mode: str = Field(
    default='auto',
    description='How the agent decided to render: auto, list, table, etc.'
  )
  # RAG context storage for tools
  last_chunks: list[dict[str, Any]] = Field(
    default_factory=list,
    description='Chunks from the most recent knowledge base query, used for context injection'
  )

__all__ = [
    # modules and global variables
    'os', 'uuid', 'base64', 'Enum',
    # typing
    'List', 'Optional', 'Dict', 'Literal', 'Any', 'Type', 'TypeVar', 'Union', 'Callable', 'Generic', 'Tuple', 
    'get_type_hints', 'get_origin', 'get_args',
    'wraps', 'signature', 'Parameter', 'Signature',
    # dotenv/logging/pathlib
    'load_dotenv', 'getLogger', 'Path',
    # pydantic
    'BaseModel', 'Field', 'Console',
    # ag_ui
    'EventType', 'StateSnapshotEvent', 'StateDeps',
    # AI agent infrastructure
    'Agent', 'Tool', 'AgentRunResult', 'StateDeps', 'RunContext', 'OpenAIChatModel', 'AgentDepsT', 'OutputDataT', 
    'Model', 'KnownModelName', 'Provider', 'BinaryContent',
    'UserPromptPart', 'ModelRequest', 'ModelResponse', 'TextPart', 'ToolCallPart', 'ToolReturnPart',
    # control_toolbox core and tunings
    # control_toolbox functions/tools (internal names)
    
    # openai
    'AsyncOpenAI',
    
    # UI Components
    'UIComponentType', 'UIComponentData',
    
    # State
    'RAGState',
    
    # Moved from model.py
    'timedelta', 'AsyncIterator', 'Iterator', 'Sequence', 'asynccontextmanager', 'time', 'replace',
    'ModelMessage', 'ModelRequestParameters', 'ModelSettings', 'get_current_model_id',
    'OpenAIResponsesModel', 'log_event', 'estimate_tokens',
]
