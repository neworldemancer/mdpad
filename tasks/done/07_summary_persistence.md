# Task 07 — Persist summaries to a per-document sidecar

## Goal
Cache summaries on disk so reopening the same document reuses them instead of
regenerating from scratch. Sidecar file: `<name>.md.summ.json` next to the doc.

## Implementation
- `summaries.py`: `save(path)` writes `{unit_id: asdict(Summary)}` to JSON;
  `load(path)` clears the store and repopulates it from the sidecar (missing or
  unreadable → empty store), returning the count. Unit ids (section ids, block
  ids `sec::pN`, `__doc__`) are content-derived, so a cached summary still matches
  its section/block on reopen; the change-gate handles anything edited since.
- `app.py`: `_summ_path(name) -> DOCS_DIR/"{name}.summ.json"`. Load on
  `GET /api/file/{name}` (open) and in `main()` when a file arg is given; save
  after `POST /api/summaries/refresh` (when a file is open).
- `.gitignore`: `*.summ.json` (derived cache, not committed).

## Acceptance
- Generate summaries, restart / reopen the doc → summaries are present without
  regenerating (the sidecar exists and loads).
- Opening a different doc loads that doc's sidecar (or an empty store if none).
- No sidecar for the bundled example (no filename); no crash when absent.
