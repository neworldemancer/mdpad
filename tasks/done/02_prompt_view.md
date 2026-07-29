# Task 02 — Full-prompt view above the diff

## Goal
Show the exact prompt sent to the model as a **normal read-only textarea above the
diff** in the review dock (not a collapsible in the context block, and definitely
not an alert). Keeps the request fully inspectable per the design invariant.

## Changes
- **`src/mdpad/static/index.html`** — remove the `<details class="prompt-view">…`
  block from `.context-block`. Add, as the first child of `.review-block` (above
  `.diff`):
  ```html
  <label class="prompt-label">Full prompt sent
    <textarea id="prompt-full" readonly></textarea>
  </label>
  ```
- **`src/mdpad/static/styles.css`** — drop the `.prompt-view` / old `#prompt-full`
  rules; style the read-only textarea: monospace, ~140px tall, full width,
  `resize: vertical`, muted border, scrolls.
- **`src/mdpad/static/app.js`** — in `showDock`, set `$("prompt-full").value = ...`
  (a `<textarea>` uses `.value`, not `.textContent`). Keep the `[system]` / `[user]`
  layout already assembled from `data.prompt`.

## Acceptance
- After a revise, the full system+user prompt shows in a read-only textarea directly
  above the Selected/Proposed diff.
- No `.prompt-view` remnants; page serves; `node --check app.js` passes.
