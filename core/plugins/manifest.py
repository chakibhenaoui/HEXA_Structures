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
    extension_points: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    path: Path | None = None

    @property
    def plugin_id(self) -> str:
        """Stable plugin id used by registries."""
        return self.descriptor.plugin_id

    @property
    def name(self) -> str:
        """Human-readable plugin name."""
        return self.descriptor.name

    def has_capability(self, capability: str) -> bool:
        """Return whether this manifest declares a capability."""
        return _normalize_token(capability) in self.capabilities

    def provides_extension(self, extension_point: str) -> bool:
        """Return whether this manifest contributes to an extension point."""
        return _normalize_token(extension_point) in self.extension_points

    def has_tag(self, tag: str) -> bool:
        """Return whether this manifest declares a tag."""
        return _normalize_token(tag) in self.tags

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
            capabilities=_optional_token_tuple(data, "capabilities"),
            extension_points=_optional_token_tuple(data, "extension_points"),
            tags=_optional_token_tuple(data, "tags"),
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


def _optional_token_tuple(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    values = data.get(key, ())
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"Plugin manifest {key} must be a list.")
    tokens = tuple(
        token
        for token in (_normalize_token(item) for item in values)
        if token
    )
    return tokens


def _normalize_token(value: object) -> str:
    return str(value).strip().lower()
