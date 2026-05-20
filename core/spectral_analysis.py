"""
Base de la future surcouche sismique modale spectrale interne.

Cette couche a vocation a fonctionner au-dessus d'un moteur modal
comme PyNite ou OpenSeesPy, afin de produire un calcul spectral
réglementaire sans dépendre nécessairement d'une commande native du moteur.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResponseSpectrumRequest:
    """Données d'entree d'une analyse spectrale modale."""

    damping_ratio: float = 0.05
    directions: tuple[str, ...] = ("X", "Y")
    combine_modes: str = "CQC"
    combine_directions: str = "SRSS"
    periods_s: list[float] = field(default_factory=list)
    spectral_accel: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class ResponseSpectrumResult:
    """Conteneur de sortie de la future analyse spectrale."""

    base_shear: dict[str, float] = field(default_factory=dict)
    modal_periods_s: list[float] = field(default_factory=list)
    participation_factors: dict[str, list[float]] = field(default_factory=dict)
    envelopes: dict = field(default_factory=dict)


def compute_response_spectrum(
    request: ResponseSpectrumRequest,
    modal_results: dict,
) -> ResponseSpectrumResult:
    """Point d'entree futur du calcul sismique modal spectral."""
    del request, modal_results
    raise NotImplementedError(
        "Le calcul sismique modal spectral interne n'est pas encore implemente."
    )
