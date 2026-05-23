"""Small in-memory plugin registry."""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar


class PluginLike(Protocol):
    """Protocol required by the generic plugin registry."""

    plugin_id: str


PluginT = TypeVar("PluginT", bound=PluginLike)


class PluginRegistry(Generic[PluginT]):
    """Ordered registry keyed by stable plugin id."""

    def __init__(self, plugins: tuple[PluginT, ...] = ()) -> None:
        self._plugins: dict[str, PluginT] = {}
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: PluginT) -> None:
        """Register a plugin, rejecting duplicate ids."""
        if plugin.plugin_id in self._plugins:
            raise ValueError(f"Plugin already registered: {plugin.plugin_id}")
        self._plugins[plugin.plugin_id] = plugin

    def get(self, plugin_id: str) -> PluginT | None:
        """Return a plugin by id, if registered."""
        return self._plugins.get(plugin_id)

    def require(self, plugin_id: str) -> PluginT:
        """Return a plugin by id or raise a clear error."""
        plugin = self.get(plugin_id)
        if plugin is None:
            raise KeyError(f"Unknown plugin: {plugin_id}")
        return plugin

    def all(self) -> tuple[PluginT, ...]:
        """Return plugins in registration order."""
        return tuple(self._plugins.values())

    def ids(self) -> tuple[str, ...]:
        """Return registered plugin ids in registration order."""
        return tuple(self._plugins.keys())

    def as_mapping(self) -> dict[str, PluginT]:
        """Return a shallow copy of the plugin mapping."""
        return dict(self._plugins)
