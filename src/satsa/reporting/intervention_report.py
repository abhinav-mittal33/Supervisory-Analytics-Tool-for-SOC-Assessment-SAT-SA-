"""Entity-wide Moat 2 "suggestion" report — a separate, downloadable document
listing every controllable-intervention signal Moat 2 can support real proof for at
this entity, with the effect/CI/robustness value behind each one, and — critically —
which actual findings sit behind that number and why each was flagged. Strictly
read-only: never mutates a finding's score, verdict, or any other field.

Two tiers, not one gate:
- **Preliminary** — the entity-wide statistical signal for a finding_type, computed
  the moment enough real data exists, regardless of whether any individual finding
  has been examiner-confirmed yet. This is honest: the underlying estimate uses
  every case at the entity with a known analyst tier, not one specific finding — it
  was never actually tied to a single finding's verdict status in the first place.
  Labeled unmistakably as preliminary; never presented as an official decision.
- **Confirmed** — the same computation, but only for findings an examiner has
  actually verdicted TRUE_SUPERVISORY_FINDING, run through the real, unmodified
  `analyze_intervention` gate (`MoatTwoGateError` still applies). This is the
  official record Section 12 describes — this report does not bypass it, it just
  ALSO shows the preliminary signal so the engine isn't silent until that happens.
"""
from __future__ import annotations

import html

from satsa.evidence.package import EvidencePackage
from satsa.evidence.verdict import Verdict
from satsa.moat2.intervention import MoatTwoGateError, analyze_intervention
from satsa.moat2.real_data import OUTCOME_COL, TREATMENT_COL, build_case_outcome_dataframe, has_enough_variation
from satsa.ocel.model import OCEL

_SUPPORTED_FINDING_TYPES = {
    "REASSIGNMENT_LOOP", "ESCALATION_SLA_VIOLATION", "MISSING_ENRICHMENT",
    "EXCESSIVE_REASSIGNMENT_CARDINALITY",
}
_FEASIBILITY_NOTE = "Staffing/roster change — assign more SENIOR-tier analysts to at-risk cases."


def _esc(value: object) -> str:
    return html.escape(str(value))


def _recommendation_sentence(decision: str) -> str:
    if decision == "ACT":
        return (
            "Recommendation: ACT. The effect is strong enough, and robust enough to a "
            "plausible unmeasured confounder, to justify making this change."
        )
    return (
        "Recommendation: INVESTIGATE FURTHER before acting. Either the effect isn't "
        "clearly distinguishable from zero, or a fairly small unmeasured confounder could "
        "explain it away — not strong enough evidence yet to commit resources on."
    )


def _why_bullets(pkgs: list[EvidencePackage]) -> str:
    items = []
    for p in pkgs:
        why = p.assumptions[0] if p.assumptions else "(no rationale logged)"
        confirmed = " — <strong>confirmed</strong>" if p.verdict == "TRUE_SUPERVISORY_FINDING" else ""
        items.append(f"<li><span class='mono'>{_esc(p.finding_id)}</span>{confirmed}: {_esc(why)}</li>")
    return "".join(items)


def _opportunity_card(title: str, tier_class: str, op, why_html: str) -> str:
    decision_class = "decision-act" if op.decision == "ACT" else "decision-investigate"
    return f"""<div class="card {tier_class}">
  <div class="card-head"><span>{_esc(title)}</span>
    <span class="badge {decision_class}">{_esc(op.decision)}</span></div>
  <table class="kv">
    <tr><th>Target</th><td>SENIOR-tier analyst assigned</td>
        <th>Outcome</th><td>Case avoids this problem</td></tr>
    <tr><th>Estimated effect</th><td>{op.effect:+.4f}</td>
        <th>95% CI</th><td>[{op.ci_low:+.4f}, {op.ci_high:+.4f}]</td></tr>
    <tr><th>Robustness value</th><td>{op.robustness_value:.3f} (ACT threshold: 0.3)</td>
        <th>Feasibility</th><td>{_esc(op.feasibility_note)}</td></tr>
  </table>
  <p>{_recommendation_sentence(op.decision)}</p>
  <p class="label">Findings behind this signal</p>
  <ul class="why">{why_html}</ul>
  <p class="muted">{_esc(op.estimand_description)}</p>
</div>"""


def build_intervention_report(cse_id: str, ocel: OCEL, concerns: list[EvidencePackage]) -> str:
    by_type: dict[str, list[EvidencePackage]] = {}
    for c in concerns:
        if c.finding_type in _SUPPORTED_FINDING_TYPES:
            by_type.setdefault(c.finding_type, []).append(c)

    preliminary_html = ""
    confirmed_html = ""
    insufficient_html = ""
    unsupported_html = "".join(
        f"<li>{_esc(ft)}: no real-data causal estimand is wired up for this finding_type yet.</li>"
        for ft in sorted({c.finding_type for c in concerns} - _SUPPORTED_FINDING_TYPES)
    )

    for finding_type, pkgs in by_type.items():
        flagged_ids = {p.affected_objects[0] for p in pkgs if p.affected_objects}
        df = build_case_outcome_dataframe(ocel, flagged_ids)
        if not has_enough_variation(df):
            insufficient_html += (
                f"<li><strong>{_esc(finding_type)}</strong> — not enough real data at this entity "
                f"({len(df)} case(s) with a known analyst tier, or no consistent/inconsistent mix) to "
                "estimate a real effect. Correctly abstains rather than guessing.</li>"
            )
            continue

        prelim_verdict = Verdict("preliminary", "TRUE_SUPERVISORY_FINDING",
                                  "Operational Discipline", "PROCESS_VIOLATION", "EXPECTED")
        prelim_op = analyze_intervention(prelim_verdict, df, treatment=TREATMENT_COL, outcome=OUTCOME_COL,
                                          feasibility_note=_FEASIBILITY_NOTE)
        preliminary_html += _opportunity_card(finding_type.replace("_", " ").title(), "tier-preliminary",
                                               prelim_op, _why_bullets(pkgs))

        confirmed_pkgs = [p for p in pkgs if p.verdict == "TRUE_SUPERVISORY_FINDING"]
        for p in confirmed_pkgs:
            try:
                real_verdict = Verdict(p.finding_id, "TRUE_SUPERVISORY_FINDING", p.verdict_capability_link,
                                        p.verdict_sub_type, p.verdict_authority_violated, p.duplicate_of_finding_id)
                op = analyze_intervention(real_verdict, df, treatment=TREATMENT_COL, outcome=OUTCOME_COL,
                                           feasibility_note=_FEASIBILITY_NOTE)
            except MoatTwoGateError as exc:
                confirmed_html += f"<li>{_esc(p.finding_id)}: {_esc(exc)}</li>"
                continue
            confirmed_html += _opportunity_card(
                f"{finding_type.replace('_', ' ').title()} — {p.finding_id}", "tier-confirmed", op, _why_bullets([p])
            )

    sections = ""
    if confirmed_html:
        sections += f"<h2>Confirmed interventions</h2><p class='muted'>Tied to an examiner-confirmed finding — the official record.</p>{confirmed_html}"
    if preliminary_html:
        sections += (
            "<h2>Preliminary signals</h2><p class='muted'>Real, computed entity-wide effects — but not yet "
            "tied to an examiner-confirmed finding. Do not act on these alone; record a verdict to move one "
            "into Confirmed above.</p>" + preliminary_html
        )
    if insufficient_html:
        sections += f"<h2>Not enough data yet</h2><ul>{insufficient_html}</ul>"
    if unsupported_html:
        sections += f"<h2>No estimand available yet</h2><ul>{unsupported_html}</ul>"
    if not sections:
        sections = "<p class='muted'>No case-level findings at this entity match a supported estimand.</p>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>SAT-SA Intervention Suggestions — {_esc(cse_id)}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #0b0c0c; margin: 0; padding: 2.5rem 3rem 4rem; max-width: 900px; }}
  h1 {{ font-size: 1.9rem; border-top: 6px solid #0b0c0c; padding-top: 8px; }}
  h2 {{ font-size: 1.2rem; margin-top: 2rem; border-bottom: 2px solid #b1b4b6; padding-bottom: 6px; }}
  .muted {{ color: #505a5f; }}
  .mono {{ font-family: Consolas, monospace; font-size: 0.92em; }}
  .card {{ border: 1px solid #b1b4b6; padding: 14px 18px; margin: 12px 0; }}
  .card.tier-confirmed {{ border-left: 5px solid #00703c; }}
  .card.tier-preliminary {{ border-left: 5px solid #b58840; }}
  .card-head {{ display: flex; justify-content: space-between; align-items: center; font-weight: 700; }}
  .badge {{ padding: 3px 10px; font-size: 0.85em; font-weight: 700; color: #fff; }}
  .decision-act {{ background: #00703c; }}
  .decision-investigate {{ background: #b58840; }}
  table.kv {{ width: 100%; margin: 8px 0; }}
  table.kv th {{ color: #505a5f; font-weight: 400; text-align: left; padding: 3px 10px 3px 0; white-space: nowrap; }}
  table.kv td {{ padding: 3px 18px 3px 0; }}
  .label {{ color: #505a5f; margin: 10px 0 2px; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.03em; }}
  ul.why {{ margin: 4px 0 0; padding-left: 1.2em; }}
</style></head>
<body>
<h1>Intervention Suggestions — {_esc(cse_id)}</h1>
<p class="muted">Generated locally, offline. Advisory only — never alters a finding's
score, verdict, or priority.</p>
{sections}
</body></html>"""
