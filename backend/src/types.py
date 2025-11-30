"""Shared types and imports for agent framework."""
from __future__ import annotations
import os
import uuid
import base64
from typing import List, Optional, Dict, Literal, Any, Type, TypeVar, Union, Callable, Generic, Tuple, get_type_hints, get_origin, get_args
from functools import wraps
from inspect import signature, Parameter, Signature
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from logging import getLogger
from pathlib import Path
from rich.console import Console

from ag_ui.core import EventType, StateSnapshotEvent # type: ignore
from pydantic_ai import Agent, BinaryContent, AgentRunResult, UserPromptPart, ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.tools import Tool # type: ignore
from pydantic_ai.ag_ui import StateDeps
from pydantic_ai._run_context import RunContext, AgentDepsT
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.output import OutputDataT
from pydantic_ai.models import Model, KnownModelName
from pydantic_ai.providers import Provider

from openai import AsyncOpenAI

__all__ = [
    # modules and global variables
    'os', 'uuid', 'base64',
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
]

