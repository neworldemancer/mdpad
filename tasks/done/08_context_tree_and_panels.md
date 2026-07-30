# Task 08 — Context subtree view + resizable/collapsible side panels

## Goal
1. **Context panel as a subtree.** Render the summary hierarchy for the caret's
   paragraph as a tree: at each level a 3-branch split — **previous / current /
   next** — where only the **current** branch descends. Show only the **title**
   at each node; **hover reveals the full summary** (native `title` tooltip).
   Colour nodes by validity state.
2. **Right panel: draggable separator + hideable.** Add a movable gutter between
   the preview and the Context panel; keep the topbar **Context** toggle to hide it.
3. **Left sidebar: collapsible, toggled by "Settings".** The Settings button
   opens/closes the whole left sidebar (0 ↔ its width); the sidebar's own gutter
   hides when collapsed. (Interpretation of "closable/openable by settings" — the
   settings form shows when the sidebar is open.)

## Backend (context.py + app.py) — done by lead
- `context.build_tree(*, sections, blocks, target_block, store, states) -> dict`:
  `{"levels": [ {level:int, prev:node|null, current:node, next:node|null}, ... ]}`
  where `node = {title, summary, state}`. L0 = Document; each ancestor level uses
  `adjacent()` for prev/next; leaf = paragraph (owner.level+1) via `block_adjacent`,
  title = first ~6 words of the paragraph, current node's `summary` = full text,
  `state` = "current". `states` comes from `summ.validity`.
- `POST /api/context/map` also returns `"tree"` (keep `items`/`counts` for compat).

## Frontend (index.html, styles.css, app.js) — subagent
- **Tree render** in `#context-map` from `data.tree.levels`: one block per level,
  indented by level, showing prev (muted) · current (bold, accent) · next (muted).
  Each node: title text with `title=<summary>` for hover; a small state dot
  (valid=accent, stale/expired=amber, missing=grey, current=ink). Safe DOM only.
- **Right gutter**: add `<div class="gutter" data-resize="map">` before
  `#context-map`; extend the workspace grid with a `6px` col before the map col;
  extend the drag logic (`beginDrag/onDrag/endDrag`) with a `"map"` case
  (`--w-map`, clamp 200–600, persist as `layout.map`); show the gutter only when
  the panel is open (in `setMap`). Restore saved width on open.
- **Left sidebar toggle**: `setSidebar(open)` sets `--w-sidebar` (0 ↔ saved/232),
  hides the sidebar gutter when collapsed, and shows the settings form when open;
  the `#settings-toggle` ("Settings") button calls it. Persist in `localStorage`.

## Acceptance
- Context panel shows a tree (prev/curr/next per level), titles only, hover shows
  the summary; colours reflect validity.
- The right panel has a draggable separator and still hides via the Context toggle;
  width persists.
- Settings collapses/expands the left sidebar; state persists; `uv run pytest`
  green; `node --check app.js` clean.
