"""Host use case for connection design plugins."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from core.application.connection_design import (
    CONNECTION_DESIGN_EXTENSION_POINT,
    ConnectionDesignRequest,
    ConnectionDesignResult,
)
from core.application.ports import PluginLoaderPort
from core.plugins import PluginManifest


@dataclass(frozen=True)
class RunConnectionDesign:
    """Load and call plugins contributing to ``connections.design``."""

    plugin_loader: PluginLoaderPort
    manifests: Sequence[PluginManifest]
    extension_point: str = CONNECTION_DESIGN_EXTENSION_POINT

    def execute(
        self,
        request: ConnectionDesignRequest,
        *,
        plugin_id: str | None = None,
    ) -> tuple[ConnectionDesignResult, ...]:
        """Run connection design with matching plugins."""
        selected = self._select_manifests(plugin_id=plugin_id)
        if plugin_id is not None and not selected:
            return (
                ConnectionDesignResult.failed(
                    plugin_id,
                    f"No plugin declares {self.extension_point}.",
                    status="not_found",
                ),
            )

        results: list[ConnectionDesignResult] = []
        for manifest in selected:
            results.append(self._run_manifest(manifest, request))
        return tuple(results)

    def _select_manifests(
        self,
        *,
        plugin_id: str | None = None,
    ) -> tuple[PluginManifest, ...]:
        return tuple(
            manifest
            for manifest in self.manifests
            if manifest.provides_extension(self.extension_point)
            and (plugin_id is None or manifest.plugin_id == plugin_id)
        )

    def _run_manifest(
        self,
        manifest: PluginManifest,
        request: ConnectionDesignRequest,
    ) -> ConnectionDesignResult:
        load_result = self.plugin_loader.load(manifest)
        if not load_result.loaded or load_result.plugin is None:
            return ConnectionDesignResult.failed(
                manifest.plugin_id,
                load_result.error or "Plugin could not be loaded.",
                status=load_result.load_state,
            )

        plugin = load_result.plugin
        if not callable(getattr(plugin, "design_connection", None)):
            return ConnectionDesignResult.failed(
                manifest.plugin_id,
                "Loaded plugin does not expose design_connection(request).",
                status="incompatible",
            )

        try:
            if not _plugin_accepts_request(plugin, request):
                return ConnectionDesignResult.skipped(
                    manifest.plugin_id,
                    "Plugin reported that the request is not applicable.",
                )
            response = plugin.design_connection(request)
        except Exception as exc:
            return ConnectionDesignResult.failed(
                manifest.plugin_id,
                f"{type(exc).__name__}: {exc}",
                status="error",
            )

        return ConnectionDesignResult.from_plugin_response(
            manifest.plugin_id,
            response,
        )


def _plugin_accepts_request(plugin: Any, request: ConnectionDesignRequest) -> bool:
    can_design = getattr(plugin, "can_design_connection", None)
    if not callable(can_design):
        return True
    return bool(can_design(request))
