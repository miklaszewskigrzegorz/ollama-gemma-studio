"""Base classes for the plugin system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PluginContext:
    """Runtime context passed to every plugin call."""
    project: str = "default"
    preset: str = "General"
    model: str = "gemma4:e2b"
    history: list = field(default_factory=list)
    # extra: pass-through dict for plugin-specific config (e.g. git_dir)
    extra: dict = field(default_factory=dict)


class BasePlugin(ABC):
    """
    Inherit from this class to create a plugin.

    Attributes:
        name          internal identifier (snake_case)
        trigger       chat command that activates this plugin, e.g. "/git"
        description   one-line description shown in /help
        usage         usage example shown in /help
        direct_result True  → return result to chat directly (no LLM call)
                      False → result is prepended as context before LLM call
    """

    name: str = ""
    trigger: str = ""
    description: str = ""
    usage: str = ""
    direct_result: bool = True

    @abstractmethod
    def run(self, args: str, ctx: PluginContext) -> str:
        """Execute the plugin. Return a markdown-formatted string."""
        ...
