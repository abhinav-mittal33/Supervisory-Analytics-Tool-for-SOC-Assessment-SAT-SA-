"""Build Order Step 14 — offline deployment (Section 18): "no internet, cloud, SaaS,
or external API dependency anywhere, at any point."

Verified by blocking every socket connection attempt at the Python level for the
duration of a full pipeline run (generate -> OCEL -> OKF -> Moat 1 -> sampling ->
Moat 2), rather than by physically disconnecting the host machine's network
interface. Chosen deliberately over a manual real-disconnect test: this session has
no safe, reversible way to toggle a shared machine's network interface, and a
programmatic block is strictly MORE rigorous anyway — it raises immediately and
loudly on the first attempted connection, where a real disconnect could let a slow
DNS timeout or a silently-caught exception pass unnoticed. This is also the test that
would have caught huggingface_hub (a pgmpy dependency, Build Order Step 11 — see
docs/assumptions.md entry 010) trying to phone home, had it done so.
"""
import socket

import pytest

from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_DEV
from satsa.moat1.fusion import fuse
from satsa.moat2.causal_model import estimate_effect
from satsa.moat2.decision import decide
from satsa.moat2.sensitivity import robustness_value
from satsa.moat2.synthetic_causal_data import generate_intervention_scenario
from satsa.ocel import sqlite_io
from satsa.okf import compiler
from satsa.sampling.allocation_explanation import explain_allocation
from satsa.sampling.submodular import budgeted_submodular_selection


class NetworkAccessAttempted(RuntimeError):
    pass


@pytest.fixture
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise NetworkAccessAttempted(f"socket.connect attempted with args={args}")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    yield


def test_full_pipeline_runs_with_zero_network_access(no_network, tmp_path):
    ocel, ground_truth = generate(MATURE_CSE_DEV)

    sqlite_path = str(tmp_path / "offline_test.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)

    result = fuse(ocel, conn)
    assert result.concerns

    candidates = [c.finding_id for c in result.concerns]
    costs = {c.finding_id: c.estimated_review_cost_minutes for c in result.concerns}
    bucket_of = {c.finding_id: f"{c.capability}|{c.finding_type}" for c in result.concerns}
    budget = sum(costs.values()) * 0.3
    selected, _ = budgeted_submodular_selection(candidates, costs, budget, bucket_of)
    explain_allocation(selected, result.concerns, budget)

    causal_df = generate_intervention_scenario(
        n=500, seed=1, true_effect=2.0, confounder_strength_on_treatment=0.0, confounder_strength_on_outcome=0.0
    )
    est = estimate_effect(causal_df, treatment="T", outcome="Y", confounders=())
    rv = robustness_value(est.t_statistic, est.df_resid)
    decide(est.effect, est.ci_low, est.ci_high, rv)
