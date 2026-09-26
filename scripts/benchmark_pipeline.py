"""Measures real wall-clock and peak-memory numbers for the full pipeline
(generate/ingest -> OCEL -> fuse -> submodular selection), across the existing
profiles plus a 4-CSE portfolio run. Feeds docs/deployment_requirements.md with
measured numbers, not invented ones (PS deliverables vi/viii, req 7).

Uses stdlib `tracemalloc` (cross-platform) rather than the POSIX-only `resource`
module — this project's deployment target is unspecified beyond "offline,
NCIIPC-controlled," which could be Windows Server, so a benchmark tool that
silently misreports there would be worse than not measuring at all.
"""
from __future__ import annotations

import time
import tracemalloc
from dataclasses import dataclass

from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_DEV, MATURE_CSE_SCALED, SMALL_CSE_SCALED
from satsa.ingestion.adapters.csv_adapter import CSVAdapter
from satsa.ingestion.pipeline import run_ingestion
from satsa.ingestion.schema import ALL_TABLES, suggest_mapping
from satsa.moat1.fusion import fuse
from satsa.ocel import sqlite_io
from satsa.okf import compiler
from satsa.portfolio.entity_risk import compute_entity_risk_indicators
from satsa.sampling.submodular import budgeted_submodular_selection


@dataclass
class BenchmarkResult:
    label: str
    num_events: int
    num_objects: int
    wall_seconds: float
    peak_memory_mb: float


def _run_and_measure(label: str, ocel, cse_id: str | None = None) -> tuple[BenchmarkResult, object]:
    tracemalloc.start()
    t0 = time.perf_counter()

    sqlite_path = f"/tmp/satsa_bench_{label}.sqlite"
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)
    result = fuse(ocel, conn, cse_id=cse_id)

    candidates = [c.finding_id for c in result.concerns]
    costs = {c.finding_id: c.estimated_review_cost_minutes for c in result.concerns}
    bucket_of = {c.finding_id: f"{c.capability}|{c.finding_type}" for c in result.concerns}
    total_cost = sum(costs.values()) or 1.0
    budgeted_submodular_selection(candidates, costs, total_cost * 0.3, bucket_of)

    wall = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return BenchmarkResult(label, len(ocel.events), len(ocel.objects), wall, peak / (1024 * 1024)), result


def _auto_mapping(adapter):
    schema = adapter.discover_schema()
    return {table: suggest_mapping(table, schema.get(table, [])) for table in ALL_TABLES}


def main() -> None:
    results: list[BenchmarkResult] = []

    for profile, label in [(MATURE_CSE_DEV, "dev"), (MATURE_CSE_SCALED, "mature_scaled"), (SMALL_CSE_SCALED, "small_scaled")]:
        ocel, _ = generate(profile)
        r, _ = _run_and_measure(label, ocel)
        results.append(r)

    # 4-CSE portfolio scenario: the 3 real sample fixtures + one synthetic profile,
    # each tagged with its own cse_id, run through entity risk indicators.
    t0 = time.perf_counter()
    tracemalloc.start()
    datasets = {}
    adapter = CSVAdapter.from_directory("data/samples/cse_a_csv")
    ocel, report = run_ingestion(adapter, _auto_mapping(adapter), cse_id="CSE_A")
    sqlite_io.write_sqlite(ocel, "/tmp/satsa_bench_portfolio_a.sqlite")
    conn = compiler.connect("/tmp/satsa_bench_portfolio_a.sqlite")
    datasets["CSE_A"] = (ocel, fuse(ocel, conn, cse_id="CSE_A"))

    dev_ocel, _ = generate(MATURE_CSE_DEV)
    sqlite_io.write_sqlite(dev_ocel, "/tmp/satsa_bench_portfolio_dev.sqlite")
    conn2 = compiler.connect("/tmp/satsa_bench_portfolio_dev.sqlite")
    datasets["CSE_DEV"] = (dev_ocel, fuse(dev_ocel, conn2, cse_id="CSE_DEV"))

    compute_entity_risk_indicators(datasets)
    wall = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    results.append(BenchmarkResult("portfolio_2cse", sum(len(o.events) for o, _ in datasets.values()), sum(len(o.objects) for o, _ in datasets.values()), wall, peak / (1024 * 1024)))

    print(f"{'label':<18}{'events':>10}{'objects':>10}{'seconds':>12}{'peak_MB':>12}")
    for r in results:
        print(f"{r.label:<18}{r.num_events:>10}{r.num_objects:>10}{r.wall_seconds:>12.3f}{r.peak_memory_mb:>12.2f}")


if __name__ == "__main__":
    main()
