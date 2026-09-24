# Product Contract

## Problem

NCIIPC examiners currently sample SOC alert/case data by hand from Critical Sector
Entities (CSEs) because manual review surfaces problems that policies, audits, and KPI
dashboards do not. Manual review does not scale.

## What this tool does

- Identifies which CSEs need supervisory attention.
- Prioritises which cases to manually review, under a fixed examiner-hour budget.
- Detects execution gaps (documentation says fine, operational evidence says
  otherwise) and negative space (expected evidence is materially absent).
- Improves the efficiency, consistency, and scalability of supervision.

## What this tool is not, and never becomes

No SIEM, no real-time monitor, no SOAR, no autonomous responder, no national
monitoring platform, no chatbot-first architecture, no replacement for examiner
judgment. Every output is an input to a human decision, never the decision itself.

## The eight capabilities every finding maps to

Threat Detection, Investigation, Escalation, Incident Response, Security Operations,
Governance & Oversight, Operational Discipline, Cyber Resilience.

## The literal success criterion (PS Sections 8-9)

Validated against expert manual review, demonstrating effectiveness comparable to or
better than current manual sampling, **at the same review-effort budget**. This system
is judged on how well it directs scarce human review hours, not on how many anomalies
it can print. Headline metrics: Recall@Budget and Supervisory Yield (Section 10.7 of
the build spec).

## Deployment constraint

Fully air-gapped. No internet, no cloud, no SaaS, no externally hosted AI/API,
anywhere, ever, including the optional local LLM explainer.

## Non-negotiables (see assumptions.md and validation_plan.md for how these are enforced)

1. No system guarantees 100% correctness — state a measurable acceptance bar and beat
   it, with quantified uncertainty.
2. Claim discipline: never claim priority, never claim a peer pattern is a rule, never
   claim a causal graph is truth.
3. Exactly two moats (Evidence Discovery, Intervention Decision). Sampling and the
   temporal axis are engineering, not moats.
4. Unit of analysis is objects and their relationships, not isolated records.
5. Peer-normal is never a compliance requirement, only a baseline for expected
   evidence volume.
6. No LLM in the analytical core, ever. Every detector, statistic, causal estimate,
   finding, and sampling decision is deterministic, statistical, or rule-based.
7. Numerical integrity: every number is calculated live, explicit planted ground
   truth, or measured during validation — never a hand-written placeholder.
8. Reject list: no SIEM, no generic alert classifier, no autonomous responder, no
   blockchain, no GNN "for innovation," no cloud, no giant deep-learning model, no
   100+ hand-tuned rules, no polished UI before analytics are validated.
