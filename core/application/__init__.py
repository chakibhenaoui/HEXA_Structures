"""Application layer for HEXA Structures."""

__all__ = [
    "ApplicationServices",
    "CONNECTION_DESIGN_EXTENSION_POINT",
    "ConnectionDesignRequest",
    "ConnectionDesignResult",
]


def __getattr__(name: str):
    """Lazy-load the application facade to keep use case imports lightweight."""
    if name == "ApplicationServices":
        from core.application.services import ApplicationServices

        return ApplicationServices
    if name in {
        "CONNECTION_DESIGN_EXTENSION_POINT",
        "ConnectionDesignRequest",
        "ConnectionDesignResult",
    }:
        from core.application import connection_design

        return getattr(connection_design, name)
    raise AttributeError(f"module 'core.application' has no attribute {name!r}")
