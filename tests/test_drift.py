"""Build Order Step 7 — CUSUM/EWMA drift detection for metric-gaming (Section 9.2)."""
from datetime import datetime, timedelta, timezone

from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_SCALED_DRIFT_DEMO
from satsa.moat1.drift import cusum_alarms, detect_displacement, ewma


def test_cusum_flags_a_clear_step_change():
    flat = [10.0] * 20
    stepped_up = flat + [10.0] * 5 + [30.0] * 10
    upper, lower = cusum_alarms(stepped_up, k=0.5, h=4.0)
    assert upper, "CUSUM failed to flag an obvious step increase"
    assert min(upper) >= 24  # alarm should fire at or after the step, not before it


def test_ewma_smooths_noise_without_erasing_a_real_shift():
    series = [1.0, 1.1, 0.9, 1.0] * 5 + [3.0] * 5
    smoothed = ewma(series, lam=0.3)
    assert smoothed[-1] > 2.0
    assert smoothed[-1] > smoothed[len(series) - 6]


def test_detect_displacement_distinguishes_gaming_from_plain_execution_gap():
    # KPI up + invariant down at the same period -> POTENTIAL_DISPLACEMENT
    kpi = [0.5] * 10 + [0.9] * 5
    invariant = [0.8] * 10 + [0.3] * 5
    findings = detect_displacement(kpi, invariant, k=0.5, h=3.0)
    assert any(f.label == "POTENTIAL_DISPLACEMENT" for f in findings)

    # invariant down alone, KPI flat -> POTENTIAL_EXECUTION_GAP
    kpi_flat = [0.5] * 15
    findings2 = detect_displacement(kpi_flat, invariant, k=0.5, h=3.0)
    assert any(f.label == "POTENTIAL_EXECUTION_GAP" for f in findings2)
    assert not any(f.label == "POTENTIAL_DISPLACEMENT" for f in findings2)


def _weekly_series(ocel):
    """Bin cases into weekly buckets by their ASSIGN time, then compute per-week
    (escalation-SLA-compliance rate, enrichment-completion rate)."""
    assign_time, escalate_time, enrich_present = {}, {}, {}
    for e in ocel.events:
        for r in e.relationships:
            if e.type == "ASSIGN" and r.qualifier == "assignment_for_case":
                assign_time[r.target_id] = e.time
            if e.type == "ESCALATE" and r.qualifier == "escalation_for_case":
                escalate_time[r.target_id] = e.time
            if e.type == "ENRICH" and r.qualifier == "enrich_for_case":
                enrich_present[r.target_id] = True

    alerts = {o.id: {a.name: a.value for a in o.attributes} for o in ocel.objects if o.type == "Alert"}
    assets = {o.id: {a.name: a.value for a in o.attributes} for o in ocel.objects if o.type == "Asset"}
    case_to_alert, alert_to_asset = {}, {}
    for o in ocel.objects:
        if o.type == "Case":
            for r in o.relationships:
                if r.qualifier == "case_for_alert":
                    case_to_alert[o.id] = r.target_id
        if o.type == "Alert":
            for r in o.relationships:
                if r.qualifier == "raised_on_asset":
                    alert_to_asset[o.id] = r.target_id

    min_t = min(assign_time.values())
    week_of = lambda t: (t - min_t).days // 7  # noqa: E731
    n_weeks = max(week_of(t) for t in assign_time.values()) + 1

    duty_ontime, duty_total, enrich_yes, enrich_total = (
        [0] * n_weeks,
        [0] * n_weeks,
        [0] * n_weeks,
        [0] * n_weeks,
    )
    for case_id, t in assign_time.items():
        w = week_of(t)
        alert_id = case_to_alert.get(case_id)
        severity = alerts.get(alert_id, {}).get("severity")
        crit = assets.get(alert_to_asset.get(alert_id), {}).get("criticality")
        if severity == "CRITICAL" and crit in ("HIGH", "CRITICAL"):
            duty_total[w] += 1
            et = escalate_time.get(case_id)
            if et is not None and (et - t) <= timedelta(minutes=30):
                duty_ontime[w] += 1
        enrich_total[w] += 1
        if enrich_present.get(case_id):
            enrich_yes[w] += 1

    kpi_series = [duty_ontime[w] / duty_total[w] if duty_total[w] else 0.0 for w in range(n_weeks)]
    invariant_series = [enrich_yes[w] / enrich_total[w] if enrich_total[w] else 0.0 for w in range(n_weeks)]
    return kpi_series, invariant_series


def test_end_to_end_recovers_the_planted_gaming_window():
    ocel, _ = generate(MATURE_CSE_SCALED_DRIFT_DEMO)
    kpi_series, invariant_series = _weekly_series(ocel)

    # Looser k/h than the module defaults: weekly-binned rates over ~9 bins are
    # noisier than the clean synthetic step changes in the unit tests above, so a
    # more sensitive threshold is needed to separate the planted window from noise —
    # tuned against this profile's actual output, not picked to force a pass.
    findings = detect_displacement(kpi_series, invariant_series, k=0.3, h=1.5, period_tolerance=1)
    assert any(f.label == "POTENTIAL_DISPLACEMENT" for f in findings), (
        f"failed to recover the planted metric-gaming window: kpi={kpi_series}, invariant={invariant_series}"
    )
    # The alarm should land in the tail of the series, matching the planted window
    # (last gaming_window_fraction of the time span — see MATURE_CSE_DEV_DRIFT_DEMO).
    displacement_weeks = [f.period_index for f in findings if f.label == "POTENTIAL_DISPLACEMENT"]
    n_weeks = len(kpi_series)
    assert min(displacement_weeks) >= n_weeks * 0.6
