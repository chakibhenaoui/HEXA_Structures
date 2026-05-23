"""Application layer for HEXA Structures."""

__all__ = ["ApplicationServices"]


def __getattr__(name: str):
    """Lazy-load the application facade to keep use case imports lightweight."""
    if name == "ApplicationServices":
        from core.application.services import ApplicationServices

        return ApplicationServices
    raise AttributeError(f"module 'core.application' has no attribute {name!r}")
