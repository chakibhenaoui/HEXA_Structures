"""Port for connection design plugins."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from core.application.connection_design import (
    ConnectionDesignRequest,
    ConnectionDesignResult,
)


class ConnectionDesignPort(Protocol):
    """Contract exposed by plugins contributing connection design features."""

    plugin_id: str

    def can_design_connection(self, request: ConnectionDesignRequest) -> bool:
        """Return whether this plugin can handle the request."""

    def design_connection(
        self,
        request: ConnectionDesignRequest,
    ) -> ConnectionDesignResult | tuple[bool, dict] | Mapping[str, Any]:
        """Run connection design and return a normalizable result."""
