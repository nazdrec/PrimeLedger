"""The ways of reading a screenshot.  The user picks one in the settings.

By subscription (the user's own sign-in in a command-line program on this computer):
    claude_cli     Claude Code
    codex_cli      Codex
By API key (the user's own key, kept encrypted on this computer):
    anthropic_api  Claude
    openai_api     ChatGPT models
    deepseek_api   DeepSeek
    gemini_api     Gemini
"""
from __future__ import annotations

from typing import Dict, List

from .. import settings
from .anthropic_api import AnthropicApi
from .base import FATAL, Provider, ProviderError, Task
from .claude_cli import ClaudeCli
from .codex_cli import CodexCli
from .deepseek_api import DeepSeekApi
from .gemini_api import GeminiApi
from .openai_api import OpenAiApi

__all__ = ["FATAL", "Provider", "ProviderError", "Task", "get", "current", "everyone"]

_ALL: Dict[str, Provider] = {p.id: p for p in (ClaudeCli(), CodexCli(), AnthropicApi(), OpenAiApi(), DeepSeekApi(),
                                               GeminiApi())}
assert tuple(_ALL) == settings.PROVIDERS


def get(pid: str) -> Provider:
    return _ALL[pid]


def current() -> Provider:
    return _ALL[settings.provider()]


def everyone() -> List[Provider]:
    return list(_ALL.values())
