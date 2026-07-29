# Task 05 — Session-integral token counter

## Goal
Track and display the **cumulative** tokens used across the whole session (every
revise + every summary/change-detection call), not just the last call's estimate.
Use the provider's actual `usage` when available; fall back to the local estimate.

> The existing "≈ N tokens" in the context spectrum is the *context size of the
> current call* — keep that. This adds a separate **running session total**.

## Subtasks

### ST-1 — `src/mdpad/provider.py`: capture real usage + accumulate
In `_chat_completion`, read `resp.json().get("usage", {})` and add
`prompt_tokens`/`completion_tokens` into a module-level accumulator
`USAGE = {"input": 0, "output": 0, "calls": 0}` (increment `calls`). When a
response has no `usage`, add the `len/4` estimate of the sent text so the total is
never stuck at 0. Expose `usage_totals() -> dict`.

### ST-2 — `src/mdpad/app.py`: expose the total
`GET /api/usage` → `provider.usage_totals()` = `{input, output, calls}`. Include a
compact `usage` field in the `/api/revise` and `/api/summaries/refresh` responses
so the UI can update without a separate round-trip.

### ST-3 — `static/index.html` + `styles.css` + `app.js`: display
Add a small, always-visible counter in the topbar (e.g. next to the provider dot):
`Σ 12.3k tok` (thousands with one decimal). Update it from the `usage` field after
every revise and summaries call, and fetch `GET /api/usage` once on boot. Muted
mono styling; title tooltip shows `input / output / calls`.

## Acceptance
- After several revises and a summaries regeneration, the topbar counter shows the
  summed input+output tokens for the session (monotonic, never resets mid-session).
- Falls back to estimates when the endpoint omits `usage`; never blocks the UI.
- `uv run pytest` green; `node --check app.js` clean.
