"""Seismic spectral analysis helpers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResponseSpectrumRequest:
    """Response spectrum request."""

    damping_ratio: float = 0.05
    directions: tuple[str, ...] = ("X", "Y")
    combine_modes: str = "CQC"
    combine_directions: str = "SRSS"
    periods_s: list[float] = field(default_factory=list)
    spectral_accel: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class ResponseSpectrumResult:
    """Result data for response spectrum result."""

    base_shear: dict[str, float] = field(default_factory=dict)
    modal_periods_s: list[float] = field(default_factory=list)
    participation_factors: dict[str, list[float]] = field(default_factory=dict)
    envelopes: dict = field(default_factory=dict)


def compute_response_spectrum(
    request: ResponseSpectrumRequest,
    modal_results: dict,
) -> ResponseSpectrumResult:
    """Compute response spectrum."""
    del request, modal_results
    raise NotImplementedError(
        "Le calcul sismique modal spectral interne n'est pas encore implemente."
    )
