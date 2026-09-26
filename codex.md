# SAT-SA interface changes

Updated: 26 September 2026

## What changed

The Streamlit interface now follows a simple examiner route: **Overview → Findings → open a finding → record a verdict**. **Import data** and **Review plan** are first-class menu pages; **Audit trail** remains available. Clicking a finding row opens a full finding page. The separate finding-ID dropdown has been removed.

The visual style is based on UK public-service conventions: black text on white, clear blue selection and links, square controls, strong headings, simple tables, a pale grey menu, visible focus outlines, and restrained use of status colour. The CSS and theme use local system assets only.

### Finding page

A finding now shows its rationale, capability, authority, rule and version, all scoring fields, confidence, evidence quality, estimated review time, affected objects, supporting cases and events, source record IDs, provenance, case timeline, and complete linked event and object fields. The examiner's existing cost override, timer, verdict form, and validation remain on that same page. A Back to findings button returns to the table.

The Overview table lets an examiner select an entity row and then select one of its findings. The Findings page offers search, capability filtering, selected/all findings, and bounded pages. Table selection opens the corresponding detail record.

### Import data

The previous upload and ingestion functions were still present in the application, but the earlier interface hid them inside a sidebar choice. The **Import data** page now exposes entity ID, CSV/JSON/SQLite upload, detected schema, editable field mapping, and Run assessment in the main workspace. A successful import offers **Review imported findings**, which selects that submission in the Findings page. The existing ingestion pipeline, adapters, mapping suggestions, and fusion calls are unchanged.

### Files

- `src/satsa/ui/app.py`: interface navigation, table selection, detailed finding view, import presentation, and view-only filters.
- `src/satsa/ui/styles.css`: UK public-service inspired local styling.
- `.streamlit/config.toml`: local light colour theme; usage telemetry remains disabled.
- `codex.md`: this change record.

## Design references

- [GOV.UK Design System: tables](https://design-system.service.gov.uk/components/table/)
- [GOV.UK Design System: service navigation](https://design-system.service.gov.uk/components/service-navigation/)
- [GOV.UK Design System: summary list](https://design-system.service.gov.uk/components/summary-list/)
- [GOV.UK Design System: focus states](https://design-system.service.gov.uk/get-started/focus-states/)
- [IBM Carbon: data tables](https://carbondesignsystem.com/components/data-table/usage/)

## Verification

- Existing focused tests: 22 passed across UI trace, offline deployment, report, portfolio risk and verdict tests. The only warnings were existing statistical PerfectSeparation warnings.
- Streamlit AppTest: Overview, Import data, Findings, Review plan and Audit trail render; finding table and import format control render; detail sections and verdict action render.
- `git diff --check` passed.

## Scope and limits

Only interface files and this record were edited for this task. The analytical backend, schemas, detectors, scoring, ingestion behaviour, validation rules and report builder were not changed. The Overview still uses the existing three sample entities. Imported submissions remain single-CSE session assessments because the backend has no multi-entity import repository. Pagination limits displayed rows; analysis and search still use the existing in-memory data. The app does not yet provide server-side querying or historical-period storage.

Run locally with `.venv/bin/streamlit run src/satsa/ui/app.py`.

## 26 September 2026 — SAT-SA reference deck research brief

Added [the six-page deck blueprint](docs/sat_sa_reference_deck_blueprint.md) after visually inspecting `/Users/abhinavmittal/Downloads/1790369431005.pdf` page by page and checking the current source. It specifies how to reproduce the reference's layouts, illustrations, diagrams, tables, graphics, typography and footer, then provides slide-ready SAT-SA copy, speaker notes, exact implementation architecture, formulas, links to actual modules, research references and explicit claim limits. It identifies fields that must come from the real SIH portal/team submission rather than copying the unrelated 2025 phishing example. This task changed documentation only; no UI or backend code was edited.

Verification: source PDF rendered and inspected; 142 tests collected. The full sandbox run yielded 140 passes and 2 tests blocked by local-server socket permission. The API test file then passed 3/3 with local-server permission. `git diff --check` passed. Figures in the blueprint describe prior local synthetic benchmarks and must not be presented as field validation.
