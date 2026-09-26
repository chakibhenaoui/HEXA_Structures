"""Sampling of OpenSees triangular shell resultants at mesh vertices."""

from __future__ import annotations


def extrapolate_t3_mid_edge_to_nodes(values: tuple[float, float, float] | list[float]) -> tuple[float, float, float]:
    """Map ASDShellT3 full-integration values to nodes 1, 2, 3.

    OpenSees orders its three points at edges 2-3, 3-1 and 1-2.
    Linear extrapolation preserves a constant field exactly.
    """
    edge_23, edge_31, edge_12 = (float(value) for value in values)
    return (
        edge_31 + edge_12 - edge_23,
        edge_23 + edge_12 - edge_31,
        edge_23 + edge_31 - edge_12,
    )
