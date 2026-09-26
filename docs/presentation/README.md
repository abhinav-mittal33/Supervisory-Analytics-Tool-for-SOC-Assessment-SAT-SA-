# SAT-SA SIH presentation

`SAT-SA_SIH_deck.pdf` — the six-page submission deck, built to the specification in
[`../sat_sa_reference_deck_blueprint.md`](../sat_sa_reference_deck_blueprint.md).

**Honest fidelity note:** this was built as HTML/CSS/inline-SVG and rendered to PDF
with headless Chrome (no design-tool pixel-overlay tracing was available in this
environment). Layout zones, colour families, and every piece of content match the
blueprint's instructions; it is a faithful reproduction of the structure and intent,
not a pixel-identical trace of the reference PDF. `ui_mock.png` (page 5's screenshot)
is a static HTML mockup built from the real, running app's own `styles.css` and real
data — not a live browser capture, since the offline demo server's SPA hydration
timing didn't cooperate with headless screenshot tooling in this session.

**Before submitting:**
- Fill in every `[verify SIH portal ...]` / `[actual ...]` placeholder on page 1 and
  page 3 (PS ID, theme, team ID/name, prototype/demo links) from the real submission
  portal — none of these were invented.
- Swap the generic brain/hexagon mark for the official SIH logo asset from the
  organizer portal.
- Re-check every number on pages 4–5 against a freshly re-run benchmark before
  presenting it as current (they're real, dated to this session's run, not invented —
  see `docs/deployment_requirements.md` and `tests/test_gate4_sampling.py`).

**To regenerate after editing `deck.html`:**

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="SAT-SA_SIH_deck.pdf" --print-to-pdf-no-header \
  "file://$(pwd)/deck.html"
```

Run from inside this directory so the relative `ui_mock.png` reference resolves.
