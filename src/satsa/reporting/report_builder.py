"""Generates a single, self-contained, offline HTML report (PS Functional
Requirements 15-17: dashboards/reports, trend across entities/time periods,
drill-down from findings to evidence).

No server, no template engine dependency, no external asset (font/JS/CSS) —
everything is inlined, including the bar chart (hand-rolled SVG, not matplotlib —
keeps this project's zero-new-dependency posture, Rule 4 of the global CLAUDE.md).
Palette matches the examiner UI's own stylesheet (`ui/styles.css`) so the
downloaded report doesn't look like a different product.

Every interpolated value is `html.escape()`-d before insertion — this file renders
data that may originate from a real CSE's ingested export (Section: Input Validation
— user-controlled data never reaches template rendering unescaped).
"""
from __future__ import annotations

import html

from satsa.evidence.package import EvidencePackage
from satsa.portfolio.entity_risk import EntityRiskIndicator
from satsa.temporal.cycles import TrendClassification

_TIER_COLOR = {"LOW": "#00703c", "MEDIUM": "#b58840", "HIGH": "#d4351c", "CRITICAL": "#942514"}
_MIN_BAR_WIDTH = 3  # px — a real zero score must still be visibly present, not an invisible 0-width rect


def _esc(value: object) -> str:
    return html.escape(str(value))


def _risk_bar_chart(indicators: list[EntityRiskIndicator]) -> str:
    if not indicators:
        return "<p class='muted'>No entities loaded.</p>"

    max_score = max(i.entity_risk_score for i in indicators)
    bar_height, gap, track_width = 22, 14, 360
    rows = []
    for idx, ind in enumerate(indicators):
        y = idx * (bar_height + gap)
        bar_w = max(_MIN_BAR_WIDTH, (ind.entity_risk_score / max_score) * track_width) if max_score > 0 else _MIN_BAR_WIDTH
        color = _TIER_COLOR.get(ind.entity_risk_tier, "#505a5f")
        rows.append(
            f'<text x="0" y="{y + bar_height - 6}" font-size="13" font-family="Arial, sans-serif" fill="#0b0c0c">{_esc(ind.cse_id)}</text>'
            f'<rect x="130" y="{y}" width="{track_width}" height="{bar_height}" fill="#f3f2f1"/>'
            f'<rect x="130" y="{y}" width="{bar_w:.1f}" height="{bar_height}" fill="{color}"/>'
            f'<text x="{140 + track_width}" y="{y + bar_height - 6}" font-size="13" font-family="Arial, sans-serif" fill="#0b0c0c">'
            f'{ind.entity_risk_score:.2f} · {_esc(ind.entity_risk_tier)}</text>'
        )
    svg_height = len(indicators) * (bar_height + gap)
    note = (
        "<p class='muted'>All entities score 0.00 this cycle — no cross-CSE deviation "
        "detected among the entities loaded. Bars below use a minimum visible width so "
        "a zero score still reads as a real result, not a rendering failure.</p>"
        if max_score <= 0 else ""
    )
    return (
        f'<svg width="{140 + track_width + 120}" height="{svg_height}" xmlns="http://www.w3.org/2000/svg">{"".join(rows)}</svg>'
        f"{note}"
    )


def _concern_card(c: EvidencePackage) -> str:
    rationale = "".join(f"<li>{_esc(note)}</li>" for note in c.assumptions) or "<li class='muted'>(none logged)</li>"
    affected = ", ".join(c.affected_objects) or "—"
    return f"""<div class="card">
  <div class="card-head">
    <span class="mono">{_esc(c.finding_id)}</span>
    <span class="badge" data-finding-type="{_esc(c.finding_type)}">{_esc(c.finding_type.replace('_', ' ').title())}</span>
  </div>
  <table class="kv">
    <tr><th>Capability</th><td>{_esc(c.capability)}</td>
        <th>Authority</th><td>{_esc(c.authority)}</td></tr>
    <tr><th>Confidence</th><td>{c.confidence:.2f}</td>
        <th>Evidence quality</th><td>{_esc(c.evidence_quality)}</td></tr>
    <tr><th>Affected</th><td colspan="3" class="mono">{_esc(affected)}</td></tr>
  </table>
  <p class="label">Rationale</p>
  <ul class="rationale">{rationale}</ul>
</div>"""


def _trend_html(trend: dict[str, TrendClassification] | None) -> str:
    if not trend:
        return (
            "<p class='muted'>Requires ≥2 ingestion cycles for the same CSE — not yet run "
            "for this report. No trend data is fabricated in its place.</p>"
        )
    rows = "".join(
        f"<tr><td>{_esc(k)}</td><td data-classification=\"{_esc(v.value)}\"><strong>"
        f"{_esc(v.value.replace('_', ' ').title())}</strong></td></tr>"
        for k, v in trend.items()
    )
    return f"<table class='kv-table'><tr><th>Finding type</th><th>Classification</th></tr>{rows}</table>"


def build_report(
    entity_risk: list[EntityRiskIndicator],
    top_concerns: dict[str, list[EvidencePackage]],
    trend: dict[str, TrendClassification] | None = None,
) -> str:
    entity_rows = "".join(
        f"<tr><td class='mono'>{_esc(i.cse_id)}</td><td>{i.entity_risk_score:.2f}</td>"
        f'<td><span class="pill" style="background:{_TIER_COLOR.get(i.entity_risk_tier, "#505a5f")}">'
        f"{_esc(i.entity_risk_tier)}</span></td></tr>"
        for i in entity_risk
    )
    _no_concerns = '<p class="muted">(no concerns this cycle)</p>'
    drilldown_sections = "".join(
        f"<h3>{_esc(cse_id)}</h3>"
        f"{''.join(_concern_card(c) for c in concerns) or _no_concerns}"
        for cse_id, concerns in top_concerns.items()
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>SAT-SA Supervisory Report</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #0b0c0c; margin: 0; padding: 2.5rem 3rem 4rem; max-width: 960px; }}
  h1 {{ font-size: 2rem; border-top: 6px solid #0b0c0c; padding-top: 8px; margin-bottom: 4px; }}
  h2 {{ font-size: 1.3rem; margin-top: 2.5rem; border-bottom: 2px solid #b1b4b6; padding-bottom: 6px; }}
  h3 {{ font-size: 1.05rem; margin-top: 1.6rem; }}
  .muted {{ color: #505a5f; }}
  .mono {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 0.92em; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 0.5rem; }}
  table.kv-table th, table.kv-table td, table:not(.kv):not(.kv-table) th, table:not(.kv):not(.kv-table) td {{
    border: 1px solid #b1b4b6; padding: 8px 12px; text-align: left; }}
  table:not(.kv):not(.kv-table) th {{ background: #f3f2f1; }}
  .pill {{ color: #fff; padding: 3px 10px; font-size: 0.85em; font-weight: 700; }}
  .card {{ border: 1px solid #b1b4b6; border-left: 5px solid #1d70b8; padding: 14px 18px; margin: 12px 0; background: #fff; }}
  .card-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
  .badge {{ background: #f3f2f1; color: #003078; padding: 3px 10px; font-size: 0.85em; font-weight: 700; }}
  table.kv {{ width: 100%; margin: 6px 0; }}
  table.kv th {{ color: #505a5f; font-weight: 400; text-align: left; padding: 3px 10px 3px 0; white-space: nowrap; }}
  table.kv td {{ padding: 3px 18px 3px 0; }}
  .label {{ color: #505a5f; margin: 10px 0 2px; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.03em; }}
  ul.rationale {{ margin: 4px 0 0; padding-left: 1.2em; }}
</style></head>
<body>
<h1>SAT-SA — Supervisory Portfolio Report</h1>
<p class="muted">Generated locally, offline — no external data or network call involved in producing this file.</p>

<h2>Entity risk indicators</h2>
{_risk_bar_chart(entity_risk)}
<table><tr><th>CSE</th><th>Risk score</th><th>Tier</th></tr>{entity_rows}</table>

<h2>Trend (two-cycle comparison)</h2>
{_trend_html(trend)}

<h2>Drill-down — top findings per entity</h2>
{drilldown_sections}

<hr/>
<p class="muted">Entity risk tiers use documented, uncalibrated engineering thresholds
(src/satsa/portfolio/entity_risk.py) pending real portfolio history. Peer comparison
and trend classification abstain (INSUFFICIENT_EVIDENCE) below a minimum peer-group
size rather than guessing.</p>
</body></html>"""
