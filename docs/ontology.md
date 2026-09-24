# Ontology

## Anomaly -> Finding -> Concern (three strictly narrowing stages)

- **Anomaly** — statistically/structurally unusual, nothing more.
- **Finding** — an anomaly that also violates an applicable OKF expectation:
  `finding_score = anomaly_score * conformance_deviation * evidence_quality`.
- **Concern** — a finding that is also material:
  `concern_score = finding_score * capability_materiality * severity_weight`.

Only Concerns enter the sampling layer.

## Examiner verdict taxonomy

Every reviewed finding gets exactly one verdict. A verdict without the required
capability link, authority link, and — for `TRUE_SUPERVISORY_FINDING` — sub-type, is
invalid and rejected at the schema/UI level, never silently accepted partial.

| Verdict | Meaning | What it updates |
|---|---|---|
| `TRUE_SUPERVISORY_FINDING` | Genuine capability weakness | Beta-Binomial success; feeds Moat 2 |
| `FALSE_POSITIVE` | Real pattern, not a supervisory concern | Beta-Binomial failure |
| `INCONCLUSIVE` | Cannot decide with available evidence | No posterior update |
| `DATA_QUALITY_ISSUE` | Artifact of broken/missing data | Updates reliability model, not true-finding-rate posterior |
| `EXPECTED_LEGITIMATE_BEHAVIOR` | Unusual but explicitly allowed under approved SOP | Updates OKF exception candidate list, not posterior |
| `DUPLICATE_OF_EXISTING_FINDING` | Same root cause as an already-confirmed finding | Links to original finding_id, no double-count |
| `OUT_OF_SCOPE` | Real anomaly, doesn't map to any of the 8 capabilities | Logged for completeness, excluded from supervisory metrics |

`TRUE_SUPERVISORY_FINDING` sub-types (exactly one required):

| Sub-type | Meaning |
|---|---|
| `PROCESS_VIOLATION` | A specific process step was skipped or done wrong |
| `CAPABILITY_INADEQUACY` | SOC lacks capacity/skill/tooling to do the expected thing at all |
| `CONTROL_FAILURE` | A deployed control did not function as intended |
| `GOVERNANCE_GAP` | Root issue is a policy/oversight/accountability gap |

## The eight capabilities

Threat Detection, Investigation, Escalation, Incident Response, Security Operations,
Governance & Oversight, Operational Discipline, Cyber Resilience.

## ABSTAIN

If reliability for a given CSE/period/capability falls below a documented threshold,
output `ABSTAIN` for that scope, with exactly one sub-reason:
`INSUFFICIENT_EVIDENCE`, `DATA_QUALITY_FAILURE`, `MISSING_DENOMINATOR`,
`INSUFFICIENT_EXPOSURE`, `BROKEN_OBJECT_LINKAGE`. Never a low-confidence finding
dressed as a real one.
