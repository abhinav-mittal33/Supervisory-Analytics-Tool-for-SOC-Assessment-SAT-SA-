"""Examiner UI (build spec Section 17) — minimum set, built only after Moat 1,
sampling, and Moat 2 are validated (all five gates pass — see docs/validation_plan.md).

Runs entirely offline: Streamlit's own usage-telemetry ping is disabled via
.streamlit/config.toml (Section 18 — no external network calls, ever). No CDN assets,
no external API calls anywhere in this file.

Run with: streamlit run src/satsa/ui/app.py
"""
from __future__ import annotations

from pathlib import Path

import tempfile
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
from satsa.ingestion.adapters.csv_adapter import CSVAdapter
from satsa.ingestion.adapters.db_adapter import DBAdapter
from satsa.ingestion.adapters.json_adapter import JSONAdapter
from satsa.ingestion.pipeline import run_ingestion
from satsa.ingestion.schema import ALL_TABLES, suggest_mapping
from satsa.moat1.fusion import fuse
from satsa.evidence.export import export_evidence_package, export_evidence_packages
from satsa.ocel import sqlite_io
from satsa.okf import compiler
from satsa.portfolio import history as portfolio_history
from satsa.portfolio.entity_risk import compute_entity_risk_indicators
from satsa.portfolio.peer_comparison import compare_all_entities
from satsa.reporting.intervention_report import build_intervention_report
from satsa.reporting.report_builder import build_report
from satsa.sampling.allocation_explanation import explain_allocation
from satsa.sampling.submodular import budgeted_submodular_selection
from satsa.temporal.cycles import TrendClassification, classify_trend
from satsa.ui import background
from satsa.validation.expert_agreement import compute_agreement

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


def _build_adapter_from_uploads(fmt: str):
    """Saves every upload to a temp file path immediately (main thread) and returns
    (adapter, source_paths, warning). `source_paths` (dict of table->path, or a
    single path for a DB export) is what the background ingestion job rebuilds its
    own fresh adapter from — never the live adapter/UploadedFile objects themselves,
    which aren't safe to hand to another thread. `warning` is set (adapter still
    None) when nothing usable was uploaded yet, never a silent no-op."""
    if fmt in ("CSV", "JSON"):
        ext = "csv" if fmt == "CSV" else "json"
        uploaded = st.file_uploader(
            f"Upload {ext} files — name each one after the table it holds "
            f"(cases.{ext}, case_events.{ext}, and optionally alerts/assets/analysts/queues.{ext})",
            type=[ext], accept_multiple_files=True, key=f"uploader_{fmt}",
        )
        if not uploaded:
            return None, None, None
        source_paths: dict[str, str] = {}
        skipped = []
        for f in uploaded:
            stem = f.name.rsplit(".", 1)[0]
            if stem in ALL_TABLES:
                tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
                tmp.write(f.read())
                tmp.close()
                source_paths[stem] = tmp.name
            else:
                skipped.append(f.name)
        if skipped:
            st.warning(f"Ignored (filename doesn't match a canonical table name): {', '.join(skipped)}")
        if not source_paths:
            return None, None, "No recognized table files uploaded yet."
        adapter = CSVAdapter(source_paths) if fmt == "CSV" else JSONAdapter(source_paths)
        return adapter, source_paths, None

    uploaded = st.file_uploader("Upload a SQLite database export (.sqlite/.db)", type=["sqlite", "db"], key="uploader_DB")
    if uploaded is None:
        return None, None, None
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.write(uploaded.read())
    tmp.close()
    return DBAdapter(tmp.name), tmp.name, None


@st.fragment(run_every=2)
def _render_pending_jobs() -> None:
    """Polls in-flight background ingestion jobs on its own timer — only this
    fragment re-renders every 2 seconds, not the whole page, so nothing else in the
    app is disrupted while a job runs."""
    pending = st.session_state.get("pending_jobs", [])
    if not pending:
        return
    still_pending = []
    for job_id in pending:
        status = background.get_job_status(job_id)
        if status.status == "running":
            st.info(f"⏳ Processing {status.cse_id} in the background...")
            still_pending.append(job_id)
        elif status.status == "done":
            st.success(f"{status.cse_id} — assessment complete. Open Companies to review it.")
            background.forget_job(job_id)
        else:
            st.error(f"{status.cse_id} — ingestion failed: {status.error}")
            background.forget_job(job_id)
    st.session_state.pending_jobs = still_pending


def _render_upload_ingestion() -> None:
    """Data-upload section (Section 17 extension): lets an examiner run the full
    pipeline against their own CSE export instead of only the three built-in
    synthetic profiles. Runs in the background (Phase F) — never blocks the app."""
    existing_ids = sorted(_all_portfolio_datasets().keys())
    mode = st.radio(
        "This submission is for...", ["An existing entity", "A brand-new entity"],
        key="import_entity_mode", horizontal=True,
    )
    if mode == "An existing entity" and existing_ids:
        cse_id = st.selectbox("Entity", existing_ids, key="import_existing_entity")
        st.caption(f"This adds a new dated batch to {cse_id} — its existing batches are kept as-is.")
    else:
        if mode == "An existing entity":
            st.caption("No entities exist yet — creating a new one.")
        cse_id = st.text_input("New entity ID", value="CSE_CUSTOM", key="import_new_entity")
        if cse_id in existing_ids:
            st.warning(f"{cse_id} already exists — this adds a new batch to it, not a separate entity.")
        else:
            st.caption(f"This creates a new entity called {cse_id}.")

    fmt = st.selectbox("File format", ["CSV", "JSON", "SQLite database export"])
    adapter, source_paths, warning = _build_adapter_from_uploads(fmt)
    if warning:
        st.warning(warning)
    if adapter is not None:
        schema = adapter.discover_schema()
        if not schema:
            st.warning("No canonical table names recognized in the upload.")
        else:
            st.write("Check the suggested column mappings below. Change any field that does not match your file.")
            mapping: dict[str, dict[str, str | None]] = {}
            for table, columns in schema.items():
                with st.expander(f"Check columns for {table} ({len(columns)} found)"):
                    guess = suggest_mapping(table, columns)
                    table_mapping = {}
                    for field in guess:
                        options = ["(none)"] + columns
                        default_col = guess[field] if guess[field] in columns else "(none)"
                        chosen = st.selectbox(
                            field, options, index=options.index(default_col), key=f"map_{fmt}_{table}_{field}"
                        )
                        table_mapping[field] = None if chosen == "(none)" else chosen
                    mapping[table] = table_mapping

            if st.button("Run assessment", type="primary", key=f"run_ingestion_{fmt}"):
                fmt_key = "DB" if fmt.startswith("SQLite") else fmt
                job_id = background.start_ingestion_job(cse_id, fmt_key, source_paths, mapping)
                st.session_state.setdefault("pending_jobs", []).append(job_id)
                st.info(
                    f"Started processing {cse_id} in the background. Keep using the rest "
                    "of the app — this will appear below once it's done."
                )
                st.rerun()

    _render_pending_jobs()


@st.cache_resource(show_spinner="Ingesting the 5 sample CSE exports for the portfolio view...")
def load_sample_portfolio():
    """The 5 deliberately heterogeneous demo CSE exports (data/samples/), ingested
    and fused once per session — the concrete proof of PS req 8/9 (cross-CSE peer
    comparison, entity-level risk indicator), not a synthetic-only claim. CSE_D is
    deliberately deviant (real elevated reassignment-loop rate, large enough sample
    to clear MIN_PEER_GROUP_SIZE) so the peer-comparison table has something real to
    flag — CSE_A/B/C/E are all quiet by design."""
    specs = [
        ("CSE_A", CSVAdapter.from_directory("data/samples/cse_a_csv"), {}),
        ("CSE_B", JSONAdapter.from_directory("data/samples/cse_b_json"), {}),
        ("CSE_C", DBAdapter("data/samples/cse_c_sqlite/cse_c.sqlite"),
         {"cases": {"analyst_id": "handler", "queue_id": "team"}}),
        ("CSE_D", CSVAdapter.from_directory("data/samples/cse_d_csv"), {}),
        ("CSE_E", JSONAdapter.from_directory("data/samples/cse_e_json"), {}),
    ]
    datasets = {}
    for cse_id, adapter, overrides in specs:
        schema = adapter.discover_schema()
        mapping = {t: suggest_mapping(t, schema.get(t, [])) for t in ALL_TABLES}
        for table, fields in overrides.items():
            mapping.setdefault(table, {}).update(fields)
        ocel, report = run_ingestion(adapter, mapping, cse_id)
        if ocel is None:
            continue
        sqlite_path = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False).name
        sqlite_io.write_sqlite(ocel, sqlite_path)
        conn = compiler.connect(sqlite_path)
        result = fuse(ocel, conn, cse_id=cse_id, low_confidence_cases=report.low_confidence_cases)
        datasets[cse_id] = (ocel, result)
        portfolio_history.seed_demo_history(cse_id, ocel, result)
    return datasets


def label(value: str | None) -> str:
    return (value or "Not recorded").replace("_", " ").capitalize()


def open_finding(finding_id: str, origin: str, entity: str | None = None) -> None:
    st.session_state.open_finding_id = finding_id
    st.session_state.open_finding_origin = origin
    st.session_state.open_finding_entity = entity
    st.rerun()


def close_finding() -> None:
    st.session_state.open_finding_id = None
    st.session_state.finding_table_version = st.session_state.get("finding_table_version", 0) + 1
    st.rerun()


def paged_table(rows: list[dict], key: str, *, selectable: bool = False, column_config=None):
    """Show a bounded page and optionally return the clicked record."""
    controls = st.columns([1, 1, 3])
    size = controls[0].selectbox("Rows per page", [25, 50, 100], key=f"{key}_size")
    pages = max(1, (len(rows) + size - 1) // size)
    page_key = f"{key}_page"
    if st.session_state.get(page_key, 1) > pages:
        st.session_state[page_key] = 1
    page = controls[1].number_input("Page", min_value=1, max_value=pages, step=1, key=page_key)
    start = (page - 1) * size
    visible = rows[start:start + size]
    controls[2].caption(f"{start + 1 if rows else 0:,} to {min(start + size, len(rows)):,} of {len(rows):,}")
    if not selectable or not visible:
        st.dataframe(visible, width="stretch", hide_index=True, column_config=column_config)
        return visible, None
    state = st.dataframe(
        visible, width="stretch", hide_index=True, column_config=column_config,
        key=f"{key}_select_{st.session_state.get('finding_table_version', 0)}",
        on_select="rerun", selection_mode="single-row",
    )
    chosen = state.selection.rows[0] if state.selection.rows else None
    return visible, visible[chosen] if chosen is not None and chosen < len(visible) else None


def detail_list(title: str, values: list[str]) -> None:
    st.markdown(f"**{title}**")
    if values:
        for value in values:
            st.write(value)
    else:
        st.caption("None recorded")


def finding_detail(pkg, ocel, *, origin: str, costs: dict[str, float] | None = None, concerns=None) -> None:
    if st.button("← Back to findings", key="back_to_findings"):
        close_finding()
    st.caption(f"{origin} / Finding {pkg.finding_id}")
    st.title(label(pkg.finding_type))
    st.write(f"**{pkg.finding_id}** · {pkg.capability} · {pkg.cse_id or 'Current assessment'}")
    if pkg.verdict:
        st.success(f"Examiner verdict: {label(pkg.verdict)}")
        if pkg.verdict_notes:
            st.write(f"**Investigator's notes:** {pkg.verdict_notes}")
    else:
        st.info("Not yet reviewed — the system flagged this automatically. An examiner still needs to look at it and decide if it's real.")
    dl1, dl2 = st.columns(2)
    dl1.download_button(
        "Download finding report (readable HTML)",
        data=build_report([], {pkg.cse_id or "This assessment": [pkg]}),
        file_name=f"satsa_finding_report_{pkg.finding_id}.html", mime="text/html",
        key=f"export_html_{origin}_{pkg.finding_id}",
    )
    dl2.download_button(
        "Download raw evidence package (JSON)",
        data=export_evidence_package(pkg), file_name=f"satsa_evidence_{pkg.finding_id}.json",
        mime="application/json", key=f"export_{origin}_{pkg.finding_id}",
    )

    st.subheader("Why this was flagged")
    if pkg.assumptions:
        for reason in pkg.assumptions:
            st.write(reason)
    else:
        st.write("The detector did not supply a narrative reason. Review the rule and evidence below.")

    st.subheader("Assessment at a glance")
    st.table([
        {"Item": "Capability", "Value": pkg.capability},
        {"Item": "Authority", "Value": AUTHORITY_LABELS.get(pkg.authority, pkg.authority)},
        {"Item": "Rule", "Value": pkg.rule_id or "Structural detector"},
        {"Item": "Rule version", "Value": pkg.rule_version or "Not recorded"},
        {"Item": "Concern score", "Value": f"{pkg.concern_score:.3f}"},
        {"Item": "Finding score", "Value": f"{pkg.finding_score:.3f}"},
        {"Item": "Anomaly score", "Value": f"{pkg.anomaly_score:.3f}"},
        {"Item": "Confidence", "Value": f"{pkg.confidence:.2f}"},
        {"Item": "Evidence quality", "Value": pkg.evidence_quality},
        {"Item": "Estimated review time", "Value": f"{pkg.estimated_review_cost_minutes:.1f} minutes"},
    ])
    st.caption("Confidence describes the signal. Evidence quality describes the supporting data. They are assessed separately.")

    st.subheader("Supporting evidence")
    cols = st.columns(2)
    with cols[0]:
        detail_list("Affected objects", pkg.affected_objects)
        detail_list("Supporting cases", pkg.supporting_cases)
    with cols[1]:
        detail_list("Supporting events", pkg.supporting_events)
        detail_list("Source records", pkg.source_records)
    if pkg.provenance:
        st.markdown("**Source provenance**")
        st.table([{"Item": label(k), "Value": v or "Not recorded"} for k, v in vars(pkg.provenance).items()])
    else:
        st.caption("Source provenance was not supplied with this finding.")

    st.subheader("Case timeline")
    case_id = pkg.affected_objects[0] if pkg.affected_objects else None
    if case_id:
        linked = [event for event in ocel.events
                  if any(rel.target_id == case_id for rel in event.relationships)]
        linked.sort(key=lambda event: event.time)
        if linked:
            st.dataframe([
                {"When": event.time.isoformat(), "Event": label(event.type),
                 "Event ID": event.id, "Related objects": ", ".join(
                     f"{rel.qualifier}: {rel.target_id}" for rel in event.relationships
                     if rel.target_id != case_id) or "—"}
                for event in linked
            ], width="stretch", hide_index=True)
            with st.expander("Complete event and object fields"):
                for event in linked:
                    st.markdown(f"**{event.id} · {label(event.type)} · {event.time.isoformat()}**")
                    st.table([{"Field": attr.name, "Value": str(attr.value)} for attr in event.attributes]
                             or [{"Field": "Attributes", "Value": "None recorded"}])
                    st.write("Linked objects: " + ", ".join(
                        f"{rel.qualifier}: {rel.target_id}" for rel in event.relationships))
                for obj in ocel.objects:
                    if obj.id in pkg.affected_objects or obj.id in pkg.supporting_cases:
                        st.markdown(f"**Object {obj.id} · {obj.type}**")
                        st.table([{"Field": attr.name, "Value": str(attr.value),
                                   "Recorded": attr.time.isoformat()} for attr in obj.attributes]
                                 or [{"Field": "Attributes", "Value": "None recorded", "Recorded": "—"}])
        else:
            st.caption("No linked case events found in this submission.")
    else:
        st.caption("No affected case is linked to this finding.")

    st.subheader("Examiner decision")
    new_cost = st.number_input(
        "Estimated review time (minutes)",
        value=float((costs or {}).get(pkg.finding_id, pkg.estimated_review_cost_minutes)),
        min_value=0.0, step=5.0, key=f"cost_{origin}_{pkg.finding_id}",
    )
    previous_cost = (costs or {}).get(pkg.finding_id, pkg.estimated_review_cost_minutes)
    if new_cost != previous_cost:
        st.session_state.cost_overrides[pkg.finding_id] = new_cost
        st.session_state.audit_log.append({
            "time": datetime.now(timezone.utc).isoformat(), "event": "COST_OVERRIDE",
            "finding_id": pkg.finding_id, "detail": f"{previous_cost:.1f} -> {new_cost:.1f} minutes",
        })
        st.rerun()
    timer_key = f"timer_{pkg.finding_id}"
    if timer_key not in st.session_state.timers:
        if st.button("Start review timer", key=f"start_{origin}_{pkg.finding_id}"):
            st.session_state.timers[timer_key] = time.time()
            st.rerun()
    else:
        elapsed = time.time() - st.session_state.timers[timer_key]
        st.write(f"Review timer: {elapsed / 60:.1f} minutes elapsed")
        if st.button("Stop review timer", key=f"stop_{origin}_{pkg.finding_id}"):
            st.session_state.audit_log.append({
                "time": datetime.now(timezone.utc).isoformat(), "event": "REVIEW_TIMER_STOPPED",
                "finding_id": pkg.finding_id,
                "detail": f"actual_review_minutes={elapsed / 60:.2f} (estimate was {previous_cost:.1f})",
            })
            del st.session_state.timers[timer_key]
            st.rerun()
    verdict_type = st.selectbox("Verdict", sorted(VERDICTS),
                                format_func=label, key=f"verdict_type_{origin}_{pkg.finding_id}")
    capability_link = sub_type = authority_violated = duplicate_of = None
    if verdict_type == "TRUE_SUPERVISORY_FINDING":
        capability_link = st.text_input("Capability link", value=pkg.capability, key=f"caplink_{origin}_{pkg.finding_id}")
        sub_type = st.selectbox("Finding category", sorted(TRUE_FINDING_SUB_TYPES),
                                format_func=label, key=f"subtype_{origin}_{pkg.finding_id}")
        authority_violated = st.text_input("Authority violated", value=pkg.authority,
                                            key=f"authviol_{origin}_{pkg.finding_id}")
    if verdict_type == "DUPLICATE_OF_EXISTING_FINDING":
        duplicate_of = st.text_input("Existing finding ID", key=f"dupof_{origin}_{pkg.finding_id}")
    notes = st.text_area(
        "Describe the real issue, in your own words (optional)",
        placeholder="e.g. spoke to the analyst — this was a genuine shift handover, just not logged correctly.",
        key=f"notes_{origin}_{pkg.finding_id}",
    )
    if st.button("Record verdict", type="primary", key=f"submit_{origin}_{pkg.finding_id}"):
        try:
            apply_verdict(pkg, Verdict(pkg.finding_id, verdict_type, capability_link,
                                       sub_type, authority_violated, duplicate_of, notes or None))
            audit_detail = label(verdict_type) + (f" — \"{notes}\"" if notes else "")
            st.session_state.audit_log.append({
                "time": datetime.now(timezone.utc).isoformat(), "event": "VERDICT_RECORDED",
                "finding_id": pkg.finding_id, "detail": audit_detail,
            })
            st.success(f"Verdict recorded: {label(verdict_type)}")
        except InvalidVerdictError as exc:
            st.error(f"Verdict could not be recorded: {exc}")

    st.subheader("Intervention analysis (Moat 2)")
    st.caption(
        "Preliminary = a real, computed entity-wide signal, shown regardless of verdict "
        "status. Confirmed = the same analysis, officially tied to this finding, only "
        "once you've recorded TRUE_SUPERVISORY_FINDING above."
    )
    concerns_for_report = concerns if concerns else [pkg]
    st.iframe(build_intervention_report(pkg.cse_id or origin, ocel, concerns_for_report), height=520)


def _all_portfolio_datasets() -> dict:
    """Sample entities + anything already in this session's memory + anything a
    background ingestion job has written to disk (Phase F) — discovered purely
    from `portfolio_history`, since the background thread never touches
    `st.session_state` directly."""
    datasets = {**load_sample_portfolio(), **st.session_state.get("custom_portfolio_entities", {})}
    for cse_id in portfolio_history.list_entity_ids():
        if cse_id in datasets:
            continue
        submissions = portfolio_history.list_submissions(cse_id)
        if not submissions:
            continue
        loaded = portfolio_history.load_batch(cse_id, submissions[-1].submitted_at)
        if loaded:
            datasets[cse_id] = loaded
    return datasets


def _pick_batch(entity_id: str, ocel, result, submissions: list, key_prefix: str):
    """Shared batch selector — used by Companies and the Audit & Reports console so
    both pages pick a specific dated batch the same, reliable way. Returns
    (batch_ocel, batch_result, batch_label) or None if the chosen batch has no
    stored raw data (the demo-seed cycle)."""
    if submissions:
        st.table([
            {"Submitted": s.submitted_at[:10], "Cases": s.case_count, "Findings": s.concern_count,
             "Raw data available": "Yes" if s.has_data else "No — illustrative only",
             "Note": s.note or "—"}
            for s in reversed(submissions)
        ])
        batch_options = [s.submitted_at for s in reversed(submissions)]
    else:
        st.caption("No batches recorded to history yet — showing the current in-memory data only.")
        batch_options = ["(current)"]
    chosen_batch = st.selectbox(
        "Open a batch", batch_options,
        format_func=lambda s: (s[:10] + (" (last submitted)" if submissions and s == submissions[-1].submitted_at else "")) if s != "(current)" else "Current",
        key=f"{key_prefix}_batch_{entity_id}",
    )
    if not submissions or chosen_batch == submissions[-1].submitted_at:
        return ocel, result, "latest"
    loaded = portfolio_history.load_batch(entity_id, chosen_batch)
    if loaded is None:
        st.warning(
            "No raw data stored for this batch — it's the illustrative demo-seed cycle "
            "(synthetic prior-month numbers only, not a real dataset), so there's "
            "nothing to drill into."
        )
        return None
    return loaded[0], loaded[1], chosen_batch[:10]


def render_companies() -> None:
    """The file-manager-style navigator: Companies -> one company's submission
    batches -> one batch's findings -> one finding's full evidence. Every level
    down is an explicit choice (selectbox, not just a grid click that might not
    register), per the "clicking the box does nothing" bug found earlier."""
    datasets = _all_portfolio_datasets()
    if not datasets:
        st.warning("No entities yet — import a CSE submission to get started.")
        return

    if st.session_state.get("open_finding_id") and st.session_state.get("open_finding_origin") == "Companies":
        batch_ocel, batch_result = st.session_state.get("companies_batch_data", (None, None))
        if batch_result:
            pkg = next((c for c in batch_result.concerns if c.finding_id == st.session_state.open_finding_id), None)
            if pkg:
                finding_detail(pkg, batch_ocel, origin=f"Companies / {st.session_state.get('open_finding_entity')}",
                              concerns=batch_result.concerns)
                return

    entity_id = st.session_state.get("companies_entity")

    if entity_id is None or entity_id not in datasets:
        st.title("Companies")
        st.write("Every entity that has ever submitted data. Pick one to see its submission history.")
        entity_query = st.text_input("Search companies", placeholder="Entity ID")
        rows = []
        for eid, (_, result) in datasets.items():
            if entity_query and entity_query.casefold() not in eid.casefold():
                continue
            subs = portfolio_history.list_submissions(eid)
            rows.append({
                "Company": eid, "Findings (latest)": len(result.concerns),
                "Batches on record": len(subs) or 1,
                "Last submitted": subs[-1].submitted_at[:10] if subs else "not recorded",
            })
        _, picked = paged_table(rows, "companies", selectable=True)
        options = ["(select a company)"] + [r["Company"] for r in rows]
        chosen = st.selectbox("Or pick a company directly", options)
        target = picked["Company"] if picked else (chosen if chosen != "(select a company)" else None)
        if target:
            st.session_state.companies_entity = target
            st.session_state.pop("companies_batch_choice", None)
            st.rerun()
        return

    ocel, result = datasets[entity_id]
    submissions = portfolio_history.list_submissions(entity_id)
    if st.button("← Back to companies"):
        st.session_state.companies_entity = None
        st.rerun()

    st.title(entity_id)
    st.caption("Everything an investigator needs to know before opening individual findings.")
    st.subheader("Briefing")
    entity_trend: dict[str, TrendClassification] = {}
    if len(submissions) >= 2:
        prior, current = submissions[-2], submissions[-1]
        cols = st.columns(4)
        cols[0].metric("Findings this batch", current.concern_count)
        cols[1].metric("Cases this batch", current.case_count)
        cols[2].metric("Batches on record", len(submissions))
        cols[3].metric("Last submitted", current.submitted_at[:10])
        st.caption(
            f"Comparing last month ({prior.submitted_at[:10]}"
            f"{' — demo seed, illustrative only' if 'DEMO SEED' in prior.note else ''}) "
            f"to this month ({current.submitted_at[:10]})."
        )
        trend_rows = []
        for ft in sorted(prior.per_finding_type):
            prior_obs, current_obs = portfolio_history.trend_observations(prior, current, ft)
            classification = classify_trend(prior_obs, current_obs)
            entity_trend[ft] = classification
            trend_rows.append({
                "Finding type": label(ft),
                "Last month": prior.per_finding_type[ft]["flagged_count"],
                "This month": current.per_finding_type[ft]["flagged_count"],
                "Trend": label(classification.value),
            })
        st.table(trend_rows)
    elif submissions:
        current = submissions[-1]
        cols = st.columns(3)
        cols[0].metric("Findings this batch", current.concern_count)
        cols[1].metric("Cases this batch", current.case_count)
        cols[2].metric("Batches on record", 1)
        st.caption("Only one batch on record so far — trend needs a second submission cycle.")
    else:
        st.caption("No batch history recorded yet for this entity.")

    st.subheader("Submission batches")
    picked_batch = _pick_batch(entity_id, ocel, result, submissions, key_prefix="companies")
    if picked_batch is None:
        return
    batch_ocel, batch_result, batch_label = picked_batch
    st.session_state.companies_batch_data = (batch_ocel, batch_result)

    st.subheader(f"Findings — {batch_label}")
    st.caption("Pick a finding below to see its complete evidence, case timeline, and record a verdict.")
    rows = [
        {"Finding ID": c.finding_id, "Finding": label(c.finding_type),
         "Capability": c.capability, "Concern score": round(c.concern_score, 3),
         "Evidence quality": c.evidence_quality,
         "Case": c.affected_objects[0] if c.affected_objects else "—"}
        for c in sorted(batch_result.concerns, key=lambda c: -c.concern_score)
    ]
    _, picked = paged_table(rows, f"companies_{entity_id}_{batch_label}", selectable=True)
    picker_options = ["(select a finding)"] + [r["Finding ID"] for r in rows]
    picked_dropdown = st.selectbox("Or open a finding directly", picker_options, key=f"finding_picker_{entity_id}_{batch_label}")
    target_finding = picked["Finding ID"] if picked else (picked_dropdown if picked_dropdown != "(select a finding)" else None)
    if target_finding:
        open_finding(target_finding, "Companies", entity_id)

    st.subheader("Downloads for this entity")
    col1, col2, col3 = st.columns(3)
    col1.download_button(
        "Supervisory report (HTML)",
        data=build_report([], {entity_id: sorted(batch_result.concerns, key=lambda c: -c.concern_score)[:5]}, trend=entity_trend or None),
        file_name=f"satsa_report_{entity_id}.html", mime="text/html", key=f"dl_report_{entity_id}",
    )
    col2.download_button(
        "Evidence package (JSON)",
        data=export_evidence_packages(batch_result.concerns, cse_id=entity_id),
        file_name=f"satsa_evidence_{entity_id}.json", mime="application/json", key=f"dl_evidence_{entity_id}",
    )
    col3.download_button(
        "Intervention suggestions (Moat 2)",
        data=build_intervention_report(entity_id, batch_ocel, batch_result.concerns),
        file_name=f"satsa_suggestions_{entity_id}.html", mime="text/html", key=f"dl_suggestions_{entity_id}",
    )


def render_peer_comparison() -> None:
    datasets = _all_portfolio_datasets()
    if len(datasets) < 2:
        st.warning("Peer comparison needs at least two entities on record.")
        return
    indicators = compute_entity_risk_indicators(datasets)
    st.title("Peer comparison")
    st.write("How each entity's supervisory signals compare to its peers, entity by entity.")
    stats = st.columns(3)
    stats[0].metric("Entities", len(indicators))
    stats[1].metric("Findings", sum(len(result.concerns) for _, result in datasets.values()))
    stats[2].metric("Entities needing attention", sum(i.entity_risk_tier in {"HIGH", "CRITICAL"} for i in indicators))

    st.subheader("Entity risk indicators")
    st.caption("An uncalibrated indicator, pending real portfolio history — review the evidence before concluding anything from the score alone.")
    st.table([
        {"Entity": i.cse_id, "Risk score": round(i.entity_risk_score, 2), "Tier": label(i.entity_risk_tier)}
        for i in indicators
    ])

    st.subheader("Per-finding-type detail")
    for finding_type, comparison in compare_all_entities(datasets).items():
        st.markdown(f"**{label(finding_type)}**")
        st.table([
            {"Entity": group_id, "Expected": round(f.expected, 1),
             "Observed": f.observed, "Deviation": round(f.z_score, 2) if f.z_score is not None else "—",
             "Flagged": "Yes" if f.flagged else "No", "Reason not assessed": f.abstain_reason or "—"}
            for group_id, f in comparison.items()
        ])

    top_concerns = {
        entity_id: sorted(result.concerns, key=lambda c: -c.concern_score)[:5]
        for entity_id, (_, result) in datasets.items()
    }
    st.download_button(
        "Download supervisory report (all entities)", data=build_report(indicators, top_concerns),
        file_name="satsa_supervisory_report.html", mime="text/html", key="dl_peer_comparison_report",
    )


def render_import() -> None:
    st.title("Import data")
    st.write("Add a periodic CSE submission, check its field mapping, then run the assessment locally.")
    st.info(
        "Ingestion runs in the background — you can keep using every other page while "
        "it processes. The new batch appears under Companies the moment it's fully done, "
        "never mid-write."
    )
    _render_upload_ingestion()


def get_assessment():
    with st.sidebar:
        source_options = ["Sample assessment"]
        if st.session_state.get("uploaded_pipeline", (None, None, None))[0] is not None:
            source_options.insert(0, "Imported CSE submission")
        source = st.selectbox("Assessment", source_options, key="assessment_source")
        if source == "Sample assessment":
            profile_name = st.selectbox("Sample dataset", list(PROFILES), format_func=lambda name: {
                "CSE_ALPHA_MATURE_DEV (dev-scale)": "Alpha · small sample",
                "CSE_ALPHA_MATURE_SCALED": "Alpha · large sample",
                "CSE_BETA_SMALL_SCALED": "Beta · large sample",
            }[name])
            ocel, _, concerns, suppressed = load_pipeline(profile_name)
            scope = profile_name
        else:
            ocel, concerns, suppressed = st.session_state.uploaded_pipeline
            scope = "Imported CSE submission"
        st.caption(f"{len(ocel.objects):,} objects · {len(ocel.events):,} events")
    return ocel, concerns, suppressed, scope


def main() -> None:
    st.set_page_config(page_title="SAT-SA | Supervisory assessment", layout="wide")
    st.html((Path(__file__).with_name("styles.css")).read_text())
    for key, default in {"audit_log": [], "cost_overrides": {}, "timers": {},
                         "open_finding_id": None, "finding_table_version": 0,
                         "custom_portfolio_entities": {}, "companies_entity": None,
                         "pending_jobs": []}.items():
        if key not in st.session_state:
            st.session_state[key] = default
    with st.sidebar:
        st.markdown('<div class="brand">SAT-SA</div><div class="brand-sub">Supervisory assessment</div>', unsafe_allow_html=True)
        page = st.radio(
            "Menu",
            ["Companies", "Peer comparison", "Findings", "Import data", "Review plan", "Audit & Reports"],
            key="workspace",
        )
        st.divider()
        st.caption("Local, offline examiner workspace")

    if page == "Import data":
        render_import()
        return
    if page == "Companies":
        render_companies()
        return
    if page == "Peer comparison":
        render_peer_comparison()
        return

    ocel, concerns, suppressed, scope = get_assessment()
    total_cost = sum(c.estimated_review_cost_minutes for c in concerns)
    with st.sidebar:
        fraction = st.slider("Review time budget", 0.05, 1.0, 0.3, 0.05)
        st.caption(f"{total_cost * fraction / 60:.1f} of {total_cost / 60:.1f} estimated hours")
    costs = {c.finding_id: st.session_state.cost_overrides.get(c.finding_id, c.estimated_review_cost_minutes)
             for c in concerns}
    by_id = {c.finding_id: c for c in concerns}
    selected, _ = budgeted_submodular_selection(
        list(by_id), costs, total_cost * fraction,
        {c.finding_id: f"{c.capability}|{c.finding_type}" for c in concerns},
    )
    if page == "Findings":
        if st.session_state.open_finding_id in by_id and st.session_state.get("open_finding_origin") == "Findings":
            finding_detail(by_id[st.session_state.open_finding_id], ocel, origin="Findings", costs=costs, concerns=concerns)
            return
        st.title("Findings")
        st.write(f"{scope} · {len(concerns):,} findings · {len(selected):,} selected within the current review budget")
        st.caption("Click a row to open the full finding, its source evidence and the examiner decision form.")
        filters = st.columns([2, 1, 1])
        query = filters[0].text_input("Search findings", placeholder="Finding, case or entity ID")
        capability = filters[1].selectbox("Capability", ["All"] + sorted({c.capability for c in concerns}))
        view = filters[2].selectbox("Show", ["Selected for review", "All findings"])
        source_ids = selected if view == "Selected for review" else list(by_id)
        rows = [
            {"Finding ID": fid, "Finding": label(by_id[fid].finding_type),
             "Capability": by_id[fid].capability,
             "Concern score": round(by_id[fid].concern_score, 3),
             "Evidence quality": by_id[fid].evidence_quality,
             "Case": by_id[fid].affected_objects[0] if by_id[fid].affected_objects else "—",
             "Entity": by_id[fid].cse_id or scope}
            for fid in sorted(source_ids, key=lambda fid: -by_id[fid].concern_score)
        ]
        rows = [r for r in rows if (capability == "All" or r["Capability"] == capability)
                and (not query or query.casefold() in " ".join(str(v) for v in r.values()).casefold())]
        if rows:
            _, picked = paged_table(rows, "findings", selectable=True)
            if picked:
                open_finding(picked["Finding ID"], "Findings")
        else:
            st.info("No findings match this view. Clear the search or change the filters.")
        return

    if page == "Review plan":
        st.title("Review plan")
        st.write(f"{scope} · how the current time budget covers the selected findings")
        explanation = explain_allocation(selected, concerns, total_cost * fraction,
                                         increment_minutes=total_cost * 0.1)
        cols = st.columns(3)
        cols[0].metric("Selected findings", explanation.num_concerns_selected)
        cols[1].metric("Coverage score", f"{explanation.coverage_score:.2f}")
        cols[2].metric("Overlapping signals removed", len(suppressed))
        st.subheader("Coverage by capability")
        st.table([{"Capability": cap, "Findings": explanation.per_capability_counts[cap],
                   "Concern score total": round(explanation.per_capability_concern_score_sum[cap], 2)}
                  for cap in explanation.per_capability_counts])
        for note in explanation.notes:
            st.info(note)
        with st.expander("Overlapping signal details"):
            for note in suppressed:
                st.write(note)
        return

    st.title("Audit & Reports")

    st.subheader("Audit trail")
    st.write("Examiner changes and review results recorded during this session.")
    if st.session_state.audit_log:
        paged_table(list(reversed(st.session_state.audit_log)), "audit")
    else:
        st.info("No decisions or review time changes recorded yet.")

    st.subheader("Agreement with examiner reviews")
    st.caption(
        "Includes verdicts recorded on this assessment AND on every Portfolio "
        "entity — a verdict recorded from anywhere counts here."
    )
    portfolio_concerns = [c for _, result in _all_portfolio_datasets().values() for c in result.concerns]
    agreement = compute_agreement(concerns + portfolio_concerns)
    if agreement.total_verdicted:
        cols = st.columns(2)
        cols[0].metric("Verdicts recorded", agreement.total_verdicted)
        cols[1].metric("Confirmation rate", f"{agreement.confirmation_rate:.0%}")
        st.table([{"Finding": label(ft), "Reviewed": v, "Confirmed": c}
                  for ft, (v, c) in agreement.by_finding_type.items()])
    else:
        st.caption("Record an examiner verdict on a finding to populate this view.")

    st.divider()
    st.subheader("Raw data browser")
    st.caption("Browse an entity's actual case and event records directly — independent of any finding, for direct manual inspection.")
    all_datasets = _all_portfolio_datasets()
    entity_ids = sorted(all_datasets)
    if not entity_ids:
        st.info("No entities on record yet.")
    else:
        raw_entity = st.selectbox("Entity", entity_ids, key="raw_data_entity")
        raw_ocel, raw_result = all_datasets[raw_entity]
        raw_submissions = portfolio_history.list_submissions(raw_entity)
        with st.expander("Pick a specific batch (defaults to the latest)"):
            picked = _pick_batch(raw_entity, raw_ocel, raw_result, raw_submissions, key_prefix="raw")
        if picked is not None:
            raw_ocel, _raw_result, raw_batch_label = picked
            st.caption(f"Showing batch: {raw_batch_label} · {len(raw_ocel.objects):,} objects · {len(raw_ocel.events):,} events")
            obj_types = sorted({o.type for o in raw_ocel.objects})
            obj_filter = st.selectbox("Object type", ["All"] + obj_types, key=f"raw_obj_type_{raw_entity}")
            obj_rows = [
                {"ID": o.id, "Type": o.type,
                 **{a.name: a.value for a in o.attributes if a.time.year == 1970}}
                for o in raw_ocel.objects if obj_filter == "All" or o.type == obj_filter
            ]
            paged_table(obj_rows, f"raw_objects_{raw_entity}")

            event_types = sorted({e.type for e in raw_ocel.events})
            event_filter = st.selectbox("Event type", ["All"] + event_types, key=f"raw_event_type_{raw_entity}")
            event_rows = [
                {"ID": e.id, "Type": e.type, "Time": e.time.isoformat(),
                 "Relationships": ", ".join(f"{r.qualifier}->{r.target_id}" for r in e.relationships)}
                for e in raw_ocel.events if event_filter == "All" or e.type == event_filter
            ]
            paged_table(event_rows, f"raw_events_{raw_entity}")

    st.divider()
    st.subheader("Report console")
    st.caption("Generate any report, evidence package, or intervention suggestion for any entity or batch — from one place, no need to drill into Companies first.")
    if entity_ids:
        console_entity = st.selectbox("Entity", entity_ids, key="console_entity")
        console_ocel, console_result = all_datasets[console_entity]
        console_submissions = portfolio_history.list_submissions(console_entity)
        with st.expander("Pick a specific batch (defaults to the latest)"):
            console_picked = _pick_batch(console_entity, console_ocel, console_result, console_submissions, key_prefix="console")
        if console_picked is not None:
            console_ocel, console_result, _console_label = console_picked
            col1, col2, col3 = st.columns(3)
            col1.download_button(
                "Supervisory report (HTML)",
                data=build_report([], {console_entity: sorted(console_result.concerns, key=lambda c: -c.concern_score)[:5]}),
                file_name=f"satsa_report_{console_entity}.html", mime="text/html", key=f"console_dl_report_{console_entity}",
            )
            col2.download_button(
                "Evidence package (JSON)",
                data=export_evidence_packages(console_result.concerns, cse_id=console_entity),
                file_name=f"satsa_evidence_{console_entity}.json", mime="application/json", key=f"console_dl_evidence_{console_entity}",
            )
            col3.download_button(
                "Intervention suggestions (Moat 2)",
                data=build_intervention_report(console_entity, console_ocel, console_result.concerns),
                file_name=f"satsa_suggestions_{console_entity}.html", mime="text/html", key=f"console_dl_suggestions_{console_entity}",
            )


if __name__ == "__main__":
    main()
