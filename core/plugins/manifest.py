"""Plugin manifest model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.plugins.base import PluginDescriptor


@dataclass(frozen=True)
class PluginManifest:
    """Validated metadata loaded from an installed plugin manifest."""

    descriptor: PluginDescriptor
    kind: str
    entry_point: str | None = None
    description: str = ""
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    path: Path | None = None

    @property
    def plugin_id(self) -> str:
        """Stable plugin id used by registries."""
        return self.descriptor.plugin_id

    @property
    def name(self) -> str:
        """Human-readable plugin name."""
        return self.descriptor.name

    @classmethod
    def from_file(cls, path: str | Path) -> "PluginManifest":
        """Load a plugin manifest from a JSON file."""
        manifest_path = Path(path)
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid plugin manifest JSON: {manifest_path}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Plugin manifest must be a JSON object: {manifest_path}")
        return cls.from_mapping(data, path=manifest_path)

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        path: str | Path | None = None,
    ) -> "PluginManifest":
        """Create a validated manifest from a mapping."""
        plugin_id = _required_text(data, "id")
        name = _required_text(data, "name")
        kind = _required_text(data, "kind").strip().lower()
        if not kind:
            raise ValueError("Plugin manifest kind must not be empty.")

        capabilities = data.get("capabilities", ())
        if capabilities is None:
            capabilities = ()
        if not isinstance(capabilities, (list, tuple)):
            raise ValueError("Plugin manifest capabilities must be a list.")

        return cls(
            descriptor=PluginDescriptor(
                plugin_id=plugin_id,
                name=name,
                version=str(data.get("version", "0.0.0")),
                api_version=str(data.get("api_version", "1")),
                source=str(data.get("source", "local")),
            ),
            kind=kind,
            entry_point=_optional_text(data, "entry_point"),
            description=str(data.get("description", "")),
            capabilities=tuple(str(item) for item in capabilities),
            path=Path(path) if path is not None else None,
        )


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if value is None or not str(value).strip():
        raise ValueError(f"Plugin manifest field '{key}' is required.")
    return str(value).strip()


def _optional_text(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None
