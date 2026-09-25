"""Examiner UI (build spec Section 17) — minimum set, built only after Moat 1,
sampling, and Moat 2 are validated (all five gates pass — see docs/validation_plan.md).

Runs entirely offline: Streamlit's own usage-telemetry ping is disabled via
.streamlit/config.toml (Section 18 — no external network calls, ever). No CDN assets,
no external API calls anywhere in this file.

Run with: streamlit run src/satsa/ui/app.py
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import streamlit as st

from satsa.evidence.verdict import (
    TRUE_FINDING_SUB_TYPES,
    VERDICTS,
    InvalidVerdictError,
    Verdict,
    apply_verdict,
)
from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_DEV, MATURE_CSE_SCALED, SMALL_CSE_SCALED
from satsa.moat1.fusion import fuse
from satsa.ocel import sqlite_io
from satsa.okf import compiler
from satsa.sampling.allocation_explanation import explain_allocation
from satsa.sampling.submodular import budgeted_submodular_selection

AUTHORITY_LABELS = {
    "MANDATORY": "MANDATORY — NCIIPC criteria / regulation",
    "EXPECTED": "EXPECTED — approved SOP / playbook",
    "PEER_NORMAL": "PEER_NORMAL — statistical baseline, not a compliance rule",
    "OPTIONAL": "OPTIONAL — best practice, informational",
    "UNKNOWN": "UNKNOWN — no defensible basis, descriptive only",
}

PROFILES = {
    "CSE_ALPHA_MATURE_DEV (dev-scale)": MATURE_CSE_DEV,
    "CSE_ALPHA_MATURE_SCALED": MATURE_CSE_SCALED,
    "CSE_BETA_SMALL_SCALED": SMALL_CSE_SCALED,
}


@st.cache_resource(show_spinner="Generating dataset and running Moat 1 pipeline...")
def load_pipeline(profile_name: str):
    profile = PROFILES[profile_name]
    ocel, ground_truth = generate(profile)
    sqlite_path = f"/tmp/satsa_ui_{profile_name.split()[0]}.sqlite"
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)
    result = fuse(ocel, conn)
    return ocel, ground_truth, result.concerns, result.suppressed


def case_trace(ocel, case_id: str) -> list[dict]:
    """The 'object/process graph' for one case, as an ordered event trace — a
    lightweight, dependency-free representation (no system Graphviz binary required,
    which keeps the offline/air-gapped deployment footprint smaller) rather than a
    rendered graph diagram. Includes every event that touches the case via ANY
    relationship qualifier, plus which other objects (analyst, queue, ...) that same
    event also links to."""
    rows = []
    for e in sorted(ocel.events, key=lambda ev: ev.time):
        targets = {r.target_id: r.qualifier for r in e.relationships}
        if case_id in targets:
            other_targets = [f"{r.qualifier}->{r.target_id}" for r in e.relationships if r.target_id != case_id]
            rows.append({"time": e.time.isoformat(), "event_type": e.type, "other_relationships": ", ".join(other_targets)})
    return rows


def main() -> None:
    st.set_page_config(page_title="SAT-SA Examiner Console", layout="wide")
    st.title("SAT-SA — Examiner Console")
    st.caption(
        "Supervisory Analytics Tool for SOC Assessment. Every number on this page is "
        "computed live from the loaded dataset — nothing here is a placeholder."
    )

    if "audit_log" not in st.session_state:
        st.session_state.audit_log = []
    if "cost_overrides" not in st.session_state:
        st.session_state.cost_overrides = {}
    if "timers" not in st.session_state:
        st.session_state.timers = {}

    with st.sidebar:
        st.header("Dataset")
        profile_name = st.selectbox("CSE profile", list(PROFILES.keys()))
        ocel, ground_truth, concerns, suppressed = load_pipeline(profile_name)
        st.write(f"{len(ocel.objects)} objects, {len(ocel.events)} events, {len(concerns)} concerns")

        st.header("Budget")
        total_cost = sum(c.estimated_review_cost_minutes for c in concerns)
        budget_fraction = st.slider("Risk-selected budget (fraction of total review cost)", 0.05, 1.0, 0.3, 0.05)
        budget = total_cost * budget_fraction
        st.write(f"B_risk = {budget:.0f} minutes ({budget / 60:.1f} hours) of {total_cost:.0f} total")

    candidates = [c.finding_id for c in concerns]
    costs = {c.finding_id: st.session_state.cost_overrides.get(c.finding_id, c.estimated_review_cost_minutes) for c in concerns}
    bucket_of = {c.finding_id: f"{c.capability}|{c.finding_type}" for c in concerns}
    by_id = {c.finding_id: c for c in concerns}

    selected, _ = budgeted_submodular_selection(candidates, costs, budget, bucket_of)
    explanation = explain_allocation(selected, concerns, budget, increment_minutes=total_cost * 0.1)

    tab_allocation, tab_findings, tab_audit = st.tabs(["Allocation", "Findings", "Audit Trail"])

    with tab_allocation:
        st.subheader("Why this allocation")
        col1, col2, col3 = st.columns(3)
        col1.metric("Concerns selected", explanation.num_concerns_selected)
        col2.metric("Coverage score", f"{explanation.coverage_score:.2f}")
        col3.metric("Suppressed (audit trail below)", len(suppressed))
        st.write("Per-capability breakdown:")
        st.table(
            [
                {"capability": cap, "count": explanation.per_capability_counts[cap], "concern_score_sum": round(explanation.per_capability_concern_score_sum[cap], 2)}
                for cap in explanation.per_capability_counts
            ]
        )
        for note in explanation.notes:
            st.info(note)
        with st.expander(f"Detector suppression notes ({len(suppressed)}) — a coarser rule correctly overridden by a finer detector"):
            for s in suppressed:
                st.text(s)

    with tab_findings:
        st.subheader(f"Selected for review this cycle ({len(selected)} of {len(concerns)} concerns)")
        rows = [
            {
                "finding_id": fid,
                "finding_type": by_id[fid].finding_type,
                "capability": by_id[fid].capability,
                "authority": by_id[fid].authority,
                "confidence": by_id[fid].confidence,
                "evidence_quality": by_id[fid].evidence_quality,
                "concern_score": round(by_id[fid].concern_score, 3),
                "cost_minutes": round(costs[fid], 1),
                "case_id": by_id[fid].affected_objects[0],
            }
            for fid in sorted(selected, key=lambda f: -by_id[f].concern_score)
        ]
        st.dataframe(rows, width="stretch")

        st.subheader("Finding detail")
        chosen = st.selectbox("Select a finding_id to review", [r["finding_id"] for r in rows] or ["(none selected)"])
        if chosen and chosen in by_id:
            pkg = by_id[chosen]
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Finding type:** {pkg.finding_type}")
                st.write(f"**Capability:** {pkg.capability}")
                st.write(f"**Authority:** {AUTHORITY_LABELS.get(pkg.authority, pkg.authority)}")
                st.write(f"**Rule:** {pkg.rule_id or '(structural detector, no OKF rule)'}")
                st.write(f"**Confidence:** {pkg.confidence:.2f}  |  **Evidence quality:** {pkg.evidence_quality} (kept separate, never blended)")
                st.write(f"**Assumptions logged:** {pkg.assumptions}")
            with col2:
                new_cost = st.number_input(
                    "Estimated review cost (minutes) — examiner override",
                    value=float(costs[chosen]), min_value=0.0, step=5.0, key=f"cost_{chosen}",
                )
                if new_cost != costs[chosen]:
                    st.session_state.cost_overrides[chosen] = new_cost
                    st.session_state.audit_log.append(
                        {"time": datetime.now(timezone.utc).isoformat(), "event": "COST_OVERRIDE",
                         "finding_id": chosen, "detail": f"{costs[chosen]:.1f} -> {new_cost:.1f} minutes"}
                    )
                    st.rerun()

                timer_key = f"timer_{chosen}"
                if timer_key not in st.session_state.timers:
                    if st.button("Start review timer", key=f"start_{chosen}"):
                        st.session_state.timers[timer_key] = time.time()
                        st.rerun()
                else:
                    elapsed = time.time() - st.session_state.timers[timer_key]
                    st.write(f"Timer running: {elapsed:.0f}s")
                    if st.button("Stop review timer", key=f"stop_{chosen}"):
                        actual_minutes = elapsed / 60.0
                        st.session_state.audit_log.append(
                            {"time": datetime.now(timezone.utc).isoformat(), "event": "REVIEW_TIMER_STOPPED",
                             "finding_id": chosen, "detail": f"actual_review_minutes={actual_minutes:.2f} (estimate was {costs[chosen]:.1f})"}
                        )
                        del st.session_state.timers[timer_key]
                        st.rerun()
                st.caption(
                    "Mechanism only — a single demo session can't show real calibration "
                    "of estimated vs. actual review time across cycles (Section 17)."
                )

            st.write("**Object/process trace for the affected case:**")
            st.dataframe(case_trace(ocel, pkg.affected_objects[0]), width="stretch")

            st.write("**Examiner verdict**")
            verdict_type = st.selectbox("Verdict", sorted(VERDICTS), key=f"verdict_type_{chosen}")
            capability_link = sub_type = authority_violated = duplicate_of = None
            if verdict_type == "TRUE_SUPERVISORY_FINDING":
                capability_link = st.text_input("Capability link", value=pkg.capability, key=f"caplink_{chosen}")
                sub_type = st.selectbox("Sub-type", sorted(TRUE_FINDING_SUB_TYPES), key=f"subtype_{chosen}")
                authority_violated = st.text_input("Authority violated", value=pkg.authority, key=f"authviol_{chosen}")
            if verdict_type == "DUPLICATE_OF_EXISTING_FINDING":
                duplicate_of = st.text_input("Duplicate of finding_id", key=f"dupof_{chosen}")

            if st.button("Submit verdict", key=f"submit_{chosen}"):
                v = Verdict(chosen, verdict_type, capability_link, sub_type, authority_violated, duplicate_of)
                try:
                    apply_verdict(pkg, v)
                    st.session_state.audit_log.append(
                        {"time": datetime.now(timezone.utc).isoformat(), "event": "VERDICT_RECORDED",
                         "finding_id": chosen, "detail": verdict_type}
                    )
                    st.success(f"Verdict recorded: {verdict_type}")
                except InvalidVerdictError as e:
                    st.error(f"Rejected — invalid verdict: {e}")

    with tab_audit:
        st.subheader("Audit trail — every override is itself an audited event")
        if st.session_state.audit_log:
            st.dataframe(list(reversed(st.session_state.audit_log)), width="stretch")
        else:
            st.write("No overrides or verdicts recorded yet this session.")


if __name__ == "__main__":
    main()
