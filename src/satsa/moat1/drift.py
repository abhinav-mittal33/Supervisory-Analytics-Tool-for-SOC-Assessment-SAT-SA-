"""CUSUM/EWMA drift detection for metric-gaming / displacement-within-a-cycle
(build spec Section 9.2): a reported KPI improves while a *linked* object-relationship
invariant degrades in the same period. Run in parallel on both series; output is
always `POTENTIAL_EXECUTION_GAP` / `POTENTIAL_DISPLACEMENT`, never an assertion of
intent (Section 9.2's own wording).

Interpretation logged per Section 1 (the spec doesn't itself distinguish when to emit
which label): a period where the KPI series alarms UP while the invariant alarms DOWN
is labeled POTENTIAL_DISPLACEMENT (the visible metric moved but the thing it's a proxy
for didn't — worth checking whether effort got redirected toward the number itself).
A period where the invariant alarms DOWN with no corresponding KPI alarm is labeled
POTENTIAL_EXECUTION_GAP (a capability drop with no gaming signal attached).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def ewma(series: list[float], lam: float = 0.3) -> list[float]:
    out = []
    prev = series[0]
    for x in series:
        prev = lam * x + (1 - lam) * prev
        out.append(prev)
    return out


def cusum_alarms(series: list[float], k: float = 0.5, h: float = 4.0) -> tuple[list[int], list[int]]:
    """Two-sided CUSUM against the series' own mean. k = allowed slack (in units of
    the series' std), h = alarm threshold. Returns (upper_alarm_indices, lower_alarm_indices)."""
    target = float(np.mean(series))
    std = float(np.std(series)) or 1.0
    k_val, h_val = k * std, h * std
    s_hi, s_lo = 0.0, 0.0
    upper, lower = [], []
    for i, x in enumerate(series):
        s_hi = max(0.0, s_hi + (x - target) - k_val)
        s_lo = min(0.0, s_lo + (x - target) + k_val)
        if s_hi > h_val:
            upper.append(i)
            s_hi = 0.0
        if s_lo < -h_val:
            lower.append(i)
            s_lo = 0.0
    return upper, lower


@dataclass(frozen=True)
class DisplacementFinding:
    period_index: int
    label: str  # "POTENTIAL_DISPLACEMENT" | "POTENTIAL_EXECUTION_GAP"


def detect_displacement(
    kpi_series: list[float],
    invariant_series: list[float],
    k: float = 0.5,
    h: float = 4.0,
    period_tolerance: int = 1,
) -> list[DisplacementFinding]:
    """period_tolerance allows a KPI alarm and an invariant alarm to be treated as
    "the same period" if they land within `period_tolerance` bins of each other —
    two independently-CUSUM'd series reacting to the same underlying window won't
    generally cross their own thresholds on the exact same bin, since each has its
    own noise and its own reset history."""
    if len(kpi_series) != len(invariant_series):
        raise ValueError("kpi_series and invariant_series must be the same length (same period bins)")

    kpi_up, _ = cusum_alarms(kpi_series, k, h)
    _, inv_down = cusum_alarms(invariant_series, k, h)

    findings = []
    for i in sorted(inv_down):
        nearby_kpi_up = any(abs(i - j) <= period_tolerance for j in kpi_up)
        label = "POTENTIAL_DISPLACEMENT" if nearby_kpi_up else "POTENTIAL_EXECUTION_GAP"
        findings.append(DisplacementFinding(i, label))
    return findings
