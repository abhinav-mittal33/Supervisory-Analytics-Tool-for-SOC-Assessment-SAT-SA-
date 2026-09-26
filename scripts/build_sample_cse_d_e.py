"""Regenerates data/samples/cse_d_csv/ and data/samples/cse_e_json/ — two more
demo CSE exports added to the portfolio sample set so the cross-CSE peer-comparison
view has more than 3 peers and at least one entity with a genuine, clearly elevated
reassignment-loop rate (the other 3 sample CSEs are all deliberately quiet, so the
portfolio table/report previously showed LOW/LOW/LOW with nothing to compare
against — CSE_D exists specifically to give the demo something real to show).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data" / "samples"


def build_cse_d() -> None:
    out = BASE / "cse_d_csv"
    out.mkdir(parents=True, exist_ok=True)

    cases_rows = []
    events_rows = []
    hour = 8
    minute = 0

    def ts(h, m):
        return f"2026-04-01T{h:02d}:{m:02d}:00Z"

    # Every one of CSE_D's 10 cases has a real reassignment loop (4 reassigns, 2
    # alternating analysts) — deliberately the most extreme case (100% loop rate),
    # not a realistic SOC scenario, so the peer-comparison mechanism has an
    # unambiguous, statistically clear-cut signal to demonstrate. Kept to 10 cases
    # (not larger) deliberately: a bigger CSE_D would dominate the cross-CSE
    # pooled-rate fit and drag the very baseline it's compared against toward
    # itself, masking its own deviation — verified empirically while tuning this
    # fixture: 5-of-12 gave z=-0.58 (not flagged), 8-of-10 gave z=-1.49 (still not
    # flagged), only the fully extreme case clears the -2.0 threshold.
    for i in range(1, 11):
        case_id = f"CASE_D{i:02d}"
        analyst = "ANL_D1" if i % 2 else "ANL_D2"
        cases_rows.append([case_id, analyst, "QUE_D1", "OPEN", ts(8, 0), ts(12, 0)])
        if True:
            events_rows += [
                [case_id, "reassigned", "ANL_D2", ts(8, 15)],
                [case_id, "reassigned", "ANL_D1", ts(8, 25)],
                [case_id, "reassigned", "ANL_D2", ts(8, 35)],
                [case_id, "reassigned", "ANL_D1", ts(8, 45)],
            ]
        events_rows += [
            [case_id, "enriched", "", ts(9, 0)],
            [case_id, "investigate", analyst, ts(9, 30)],
            [case_id, "closed", "", ts(12, 0)],
        ]

    with open(out / "cases.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "assigned_to", "assignment_group", "status", "opened_at", "closed_at"])
        w.writerows(cases_rows)

    with open(out / "case_events.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "event", "actor", "ts"])
        w.writerows(events_rows)

    # Real analyst-tier data — without this, Moat 2's one wired-up real-data estimand
    # (does a SENIOR analyst reduce reassignment-loop occurrence?) has no treatment
    # variable at all (every ingested analyst defaults to tier=UNKNOWN and gets
    # dropped, not guessed — see moat2/real_data.py). CSE_D's own loop rate is 100%
    # here (deliberately, for the peer-comparison demo above) so its outcome has no
    # variation either — a real, honestly-reported "insufficient data" case for Moat 2
    # specifically, not a bug. The scaled synthetic profiles (MATURE_CSE_SCALED) are
    # where Moat 2 actually gets a meaningful mixed sample to estimate against.
    with open(out / "analysts.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["analyst_id", "tier"])
        w.writerows([["ANL_D1", "JUNIOR"], ["ANL_D2", "SENIOR"]])

    print(f"wrote {out}")


def build_cse_e() -> None:
    out = BASE / "cse_e_json"
    out.mkdir(parents=True, exist_ok=True)

    cases = [
        {"incident_number": f"E-{i}", "owner": "R.Patel", "queue": "Tier1", "state": "OPEN",
         "created": "2026-04-02T09:00:00Z", "resolved_at": "2026-04-02T09:40:00Z"}
        for i in range(1, 4)
    ]
    events = []
    for i in range(1, 4):
        events += [
            {"incident_number": f"E-{i}", "activity": "enriched", "analyst_id": None, "event_time": "2026-04-02T09:10:00Z"},
            {"incident_number": f"E-{i}", "activity": "investigate", "analyst_id": "R.Patel", "event_time": "2026-04-02T09:20:00Z"},
            {"incident_number": f"E-{i}", "activity": "closed", "analyst_id": None, "event_time": "2026-04-02T09:40:00Z"},
        ]

    (out / "cases.json").write_text(json.dumps(cases, indent=2))
    (out / "case_events.json").write_text(json.dumps(events, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    build_cse_d()
    build_cse_e()
