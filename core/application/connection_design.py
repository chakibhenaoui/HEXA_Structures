"""Application DTOs for connection design plugins."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


CONNECTION_DESIGN_EXTENSION_POINT = "connections.design"


@dataclass(frozen=True)
class ConnectionDesignRequest:
    """Input passed by HEXA Structures to a connection design plugin."""

    connection_id: str
    connection_type: str = ""
    node_tag: int | None = None
    member_tags: tuple[int, ...] = field(default_factory=tuple)
    design_code: str | None = None
    inputs: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        connection_id = str(self.connection_id).strip()
        if not connection_id:
            raise ValueError("connection_id must not be empty.")
        object.__setattr__(self, "connection_id", connection_id)
        object.__setattr__(self, "connection_type", str(self.connection_type).strip())
        object.__setattr__(
            self,
            "member_tags",
            tuple(int(tag) for tag in self.member_tags),
        )
        if self.design_code is not None:
            design_code = str(self.design_code).strip() or None
            object.__setattr__(self, "design_code", design_code)


@dataclass(frozen=True)
class ConnectionDesignResult:
    """Normalized result returned by a connection design plugin."""

    plugin_id: str
    success: bool
    status: str = "success"
    payload: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def ok(
        cls,
        plugin_id: str,
        payload: Mapping[str, Any] | None = None,
        *,
        warnings: tuple[str, ...] | list[str] = (),
    ) -> "ConnectionDesignResult":
        """Build a successful result."""
        return cls(
            plugin_id=plugin_id,
            success=True,
            status="success",
            payload=dict(payload or {}),
            warnings=tuple(str(warning) for warning in warnings),
        )

    @classmethod
    def failed(
        cls,
        plugin_id: str,
        error: str,
        *,
        status: str = "failed",
        payload: Mapping[str, Any] | None = None,
    ) -> "ConnectionDesignResult":
        """Build a failed result."""
        return cls(
            plugin_id=plugin_id,
            success=False,
            status=status,
            payload=dict(payload or {}),
            errors=(str(error),),
        )

    @classmethod
    def skipped(
        cls,
        plugin_id: str,
        reason: str,
    ) -> "ConnectionDesignResult":
        """Build a skipped result for a plugin that is not applicable."""
        return cls(
            plugin_id=plugin_id,
            success=False,
            status="skipped",
            errors=(str(reason),),
        )

    @classmethod
    def from_plugin_response(
        cls,
        plugin_id: str,
        response: object,
    ) -> "ConnectionDesignResult":
        """Normalize common plugin return shapes."""
        if isinstance(response, cls):
            return response
        if isinstance(response, tuple) and len(response) == 2:
            success, payload = response
            payload_dict = dict(payload or {}) if isinstance(payload, Mapping) else {}
            if bool(success):
                return cls.ok(plugin_id, payload_dict)
            return cls.failed(
                plugin_id,
                str(payload_dict.get("error") or "Connection design failed."),
                payload=payload_dict,
            )
        if isinstance(response, Mapping):
            return _from_mapping_response(plugin_id, response)
        return cls.ok(plugin_id, {"value": response})


def _from_mapping_response(
    plugin_id: str,
    response: Mapping[str, Any],
) -> ConnectionDesignResult:
    success = bool(response.get("success", True))
    status = str(response.get("status") or ("success" if success else "failed"))
    payload = response.get("payload")
    if isinstance(payload, Mapping):
        payload_dict = dict(payload)
    else:
        payload_dict = {
            str(key): value
            for key, value in response.items()
            if key not in {"success", "status", "warnings", "errors", "error"}
        }
    warnings = _message_tuple(response.get("warnings", ()))
    errors = _message_tuple(response.get("errors", ()))
    if response.get("error"):
        errors = errors + (str(response["error"]),)
    return ConnectionDesignResult(
        plugin_id=plugin_id,
        success=success,
        status=status,
        payload=payload_dict,
        warnings=warnings,
        errors=errors,
    )


def _message_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return (str(value),)
