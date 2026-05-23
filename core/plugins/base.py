"""Base plugin metadata shared by plugin categories."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PluginDescriptor:
    """Stable metadata for a plugin known by HEXA Structures."""

    plugin_id: str
    name: str
    version: str = "builtin"
    api_version: str = "1"
    source: str = "builtin"

    def __post_init__(self) -> None:
        if not self.plugin_id or not self.plugin_id.strip():
            raise ValueError("plugin_id must not be empty.")
        if not self.name or not self.name.strip():
            raise ValueError("name must not be empty.")
