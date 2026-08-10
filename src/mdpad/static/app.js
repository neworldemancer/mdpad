// mdpad frontend — one file, no build. Python does the interesting work; this
// wires the editor, live preview, outline, selection actions, and the diff.
"use strict";

const $ = (id) => document.getElementById(id);
const md = window.markdownit({ html: false, linkify: true, typographer: true });

// Stamp each rendered block with its markdown source line range so the editor
// selection and the preview can be kept in sync (block-level).
function _injectLine(tokens, idx, options, env, slf) {
  const t = tokens[idx];
  if (t.map) {
    t.attrSet("data-line-start", String(t.map[0]));
    t.attrSet("data-line-end", String(t.map[1]));
  }
  return slf.renderToken(tokens, idx, options);
}
["paragraph_open", "heading_open", "blockquote_open", "bullet_list_open",
 "ordered_list_open", "list_item_open", "table_open"].forEach((rule) => {
  md.renderer.rules[rule] = _injectLine;
});

const editor = $("editor");
const preview = $("preview");
let pending = null; // { start, end } of the selection a proposal applies to
let currentName = null; // filename of the open document, or null (unsaved example)
let dirty = false; // true when the editor has unsaved changes

const ACTIONS = {
  rewrite: "Rewrite the selected text more clearly while preserving meaning and all math.",
  expand: "Expand the selected text with more detail and rigor, preserving meaning and math.",
  shorten: "Shorten the selected text, keeping the essential claims and all math.",
};

// ---- rendering ----------------------------------------------------------
function renderMath() {
  if (window.renderMathInElement) {
    window.renderMathInElement(preview, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
    });
  }
}

let renderTimer = null;
function renderPreview() {
  preview.innerHTML = md.render(editor.value);
  renderMath();
  syncFromEditor(false);
}
function scheduleRender() {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(renderPreview, 350);
}

// ---- outline (lightweight client scan, navigation only) ----------------
function lineStartOffset(lineIndex) {
  const lines = editor.value.split("\n");
  let off = 0;
  for (let i = 0; i < lineIndex; i++) off += lines[i].length + 1;
  return off;
}

function buildOutline() {
  const list = $("outline");
  list.innerHTML = "";
  editor.value.split("\n").forEach((line, i) => {
    const m = /^(#{1,3})\s+(.+?)\s*#*$/.exec(line);
    if (!m) return;
    const li = document.createElement("li");
    li.className = "lvl-" + m[1].length;
    li.tabIndex = 0;
    li.innerHTML = `<span class="tick"></span><span>${escapeHtml(m[2])}</span>`;
    li.dataset.line = String(i);
    const go = () => focusLine(i);
    li.addEventListener("click", go);
    li.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
    list.appendChild(li);
  });
}

function focusLine(i) {
  const off = lineStartOffset(i);
  editor.focus();
  editor.setSelectionRange(off, off);
  const ratio = i / Math.max(1, editor.value.split("\n").length);
  editor.scrollTop = ratio * editor.scrollHeight;
  markActiveSection();
}

function markActiveSection() {
  const caretLine = editor.value.slice(0, editor.selectionStart).split("\n").length - 1;
  const items = [...document.querySelectorAll(".outline li")];
  let active = null;
  for (const li of items) if (Number(li.dataset.line) <= caretLine) active = li;
  items.forEach((li) => li.classList.toggle("active", li === active));
  if (active) $("breadcrumb").textContent = active.textContent.trim().toLowerCase().replace(/\s+/g, "-");
}

// ---- editor <-> preview block sync -------------------------------------
function _lineOf(pos) {
  return editor.value.slice(0, Math.max(0, pos)).split("\n").length - 1;
}

// Highlight the preview block(s) overlapping the editor's current selection.
function syncFromEditor(scroll) {
  const a = _lineOf(editor.selectionStart), b = _lineOf(editor.selectionEnd);
  let first = null;
  preview.querySelectorAll("[data-line-start]").forEach((el) => {
    const s = +el.getAttribute("data-line-start"), e = +el.getAttribute("data-line-end");
    const hit = s <= b && e > a;             // block range [s,e) overlaps [a,b]
    el.classList.toggle("sync-hl", hit);
    if (hit && !first) first = el;
  });
  if (first && scroll) first.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

// Click a preview block -> select its source lines in the editor.
function selectSourceLines(el) {
  const s = +el.getAttribute("data-line-start"), e = +el.getAttribute("data-line-end");
  const lines = editor.value.split("\n").length;
  const from = lineStartOffset(s);
  const to = e >= lines ? editor.value.length : lineStartOffset(e) - 1;
  editor.focus();
  editor.setSelectionRange(from, Math.max(from, to));
  syncFromEditor(true);
}

// Scroll the editor so `line` sits near the top third of the textarea.
function scrollEditorToLine(line) {
  const cs = getComputedStyle(editor);
  const lh = parseFloat(cs.lineHeight) || 20;
  const pad = parseFloat(cs.paddingTop) || 0;
  editor.scrollTop = Math.max(0, line * lh + pad - editor.clientHeight / 3);
}

// ---- draggable pane dividers + resizable dock --------------------------
let drag = null;
function initResizers() {
  const ws = document.querySelector(".workspace");
  const saved = JSON.parse(localStorage.getItem("mdpad.layout") || "{}");
  if (saved.sidebar) ws.style.setProperty("--w-sidebar", saved.sidebar + "px");
  if (saved.editor) ws.style.setProperty("--w-editor", saved.editor + "px");
  if (saved.dock) $("dock").style.height = saved.dock + "px";
  document.querySelectorAll(".gutter").forEach((g) =>
    g.addEventListener("mousedown", (e) => beginDrag(e, g, g.dataset.resize)));
  const dr = document.querySelector(".dock-resize");
  if (dr) dr.addEventListener("mousedown", (e) => beginDrag(e, dr, "dock"));
}
function beginDrag(e, handle, which) {
  e.preventDefault();
  drag = {
    which, handle, startX: e.clientX, startY: e.clientY,
    ws: document.querySelector(".workspace"),
    sidebarW: document.querySelector(".sidebar").getBoundingClientRect().width,
    editorW: document.querySelector(".editor-pane").getBoundingClientRect().width,
    mapW: document.querySelector(".context-map").getBoundingClientRect().width,
    dockH: $("dock").getBoundingClientRect().height,
  };
  handle.classList.add("dragging");
  document.body.style.cursor = which === "dock" ? "row-resize" : "col-resize";
  window.addEventListener("mousemove", onDrag);
  window.addEventListener("mouseup", endDrag);
}
function onDrag(e) {
  if (!drag) return;
  if (drag.which === "sidebar") {
    drag.ws.style.setProperty("--w-sidebar", Math.max(140, Math.min(drag.sidebarW + (e.clientX - drag.startX), 480)) + "px");
  } else if (drag.which === "editor") {
    drag.ws.style.setProperty("--w-editor", Math.max(240, drag.editorW + (e.clientX - drag.startX)) + "px");
  } else if (drag.which === "map") {
    drag.ws.style.setProperty("--w-map", Math.max(200, Math.min(drag.mapW - (e.clientX - drag.startX), 600)) + "px");
  } else {
    $("dock").style.height = Math.max(120, Math.min(drag.dockH - (e.clientY - drag.startY), window.innerHeight * 0.85)) + "px";
  }
}
function endDrag() {
  if (!drag) return;
  const prev = JSON.parse(localStorage.getItem("mdpad.layout") || "{}");
  localStorage.setItem("mdpad.layout", JSON.stringify({
    sidebar: sidebarOpen ? Math.round(document.querySelector(".sidebar").getBoundingClientRect().width) : prev.sidebar,
    editor: Math.round(document.querySelector(".editor-pane").getBoundingClientRect().width),
    dock: $("dock").hidden ? prev.dock : Math.round($("dock").getBoundingClientRect().height),
    map: mapOpen ? Math.round(document.querySelector(".context-map").getBoundingClientRect().width) : prev.map,
  }));
  drag.handle.classList.remove("dragging");
  document.body.style.cursor = "";
  window.removeEventListener("mousemove", onDrag);
  window.removeEventListener("mouseup", endDrag);
  drag = null;
}

// ---- provider settings (localStorage + server .env) --------------------
let serverHasKey = false; // true when the backend holds an API key (.env)
let savedModel = "";      // model id from localStorage, applied once models load

function loadSettings() {
  const s = JSON.parse(localStorage.getItem("mdpad.provider") || "{}");
  $("p-base").value = s.base_url || "";
  $("p-key").value = s.api_key || "";
  savedModel = s.model || "";
  $("p-temp").value = s.temperature ?? 0.3;
  $("p-max").value = s.max_tokens ?? 1024;
}
function readSettings() {
  return {
    base_url: $("p-base").value.trim(),
    api_key: $("p-key").value.trim(),
    model: $("p-model").value,
    temperature: parseFloat($("p-temp").value) || 0.3,
    max_tokens: parseInt($("p-max").value, 10) || 1024,
  };
}
function saveSettings() {
  localStorage.setItem("mdpad.provider", JSON.stringify(readSettings()));
  refreshProviderDot();
}
function refreshProviderDot() {
  const s = readSettings();
  // "live" when a model is chosen and a key exists (server .env or user-supplied)
  $("provider-dot").classList.toggle("live", !!(s.model && (serverHasKey || s.api_key)));
}

// Fetch the model list from the backend (which uses the server .env key by
// default, or the base URL / key the user typed) and fill the dropdown.
async function fetchModels() {
  const sel = $("p-model");
  const qs = new URLSearchParams();
  const base = $("p-base").value.trim();
  const key = $("p-key").value.trim();
  if (base) qs.set("base_url", base);
  if (key) qs.set("api_key", key);
  let data;
  try {
    data = await (await fetch("/api/models?" + qs.toString())).json();
  } catch (e) {
    return toast("Model list failed: " + e.message);
  }
  serverHasKey = data.has_key;
  sel.innerHTML = "";
  const ids = data.models || [];
  if (!ids.length) {
    const o = document.createElement("option");
    o.value = ""; o.textContent = data.error ? "(no models)" : "(none)";
    sel.appendChild(o);
    if (data.error) toast("Models: " + data.error);
  } else {
    ids.forEach((id) => {
      const o = document.createElement("option");
      o.value = id; o.textContent = id;
      sel.appendChild(o);
    });
    sel.value = savedModel && ids.includes(savedModel) ? savedModel : ids[0];
  }
  saveSettings();
}

// Prefill the base URL from the server default, then load models.
async function initProvider() {
  try {
    const cfg = await (await fetch("/api/config")).json();
    serverHasKey = cfg.has_key;
    if (!$("p-base").value.trim()) $("p-base").value = cfg.base_url || "";
  } catch { /* keep whatever is in localStorage */ }
  await fetchModels();
}

// ---- revise flow --------------------------------------------------------
// Auto-generate any summaries the document is missing (whole doc + all levels)
// so a revise builds on real summaries, not excerpt fallbacks. Only the missing
// ones are generated, so it is a one-time cost per new/changed section.
async function ensureSummaries() {
  try {
    toast("Generating summaries…");
    const res = await fetch("/api/summaries/refresh", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: editor.value, mode: "missing", provider: readSettings() }),
    });
    const data = await res.json();
    if (data.generated) { setUsage(data.usage); refreshSummaryStatus(); }
  } catch { /* proceed anyway; the revise falls back to excerpts */ }
}

async function runAction(instruction) {
  const start = editor.selectionStart, end = editor.selectionEnd;
  if (start === end) return toast("Select some text first.");
  await ensureSummaries();
  toast("Building context…");
  let data;
  try {
    const res = await fetch("/api/revise", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: editor.value, sel_start: start, sel_end: end,
        instruction, provider: readSettings(),
      }),
    });
    data = await res.json();
  } catch (e) {
    return toast("Request failed: " + e.message);
  }
  pending = { start, end };
  showDock(data, editor.value.slice(start, end));
  setUsage(data.usage);
  hideToast();
}

function showDock(data, selected) {
  $("dock").hidden = false;
  // context spectrum + legend
  const items = data.context.items;
  const max = Math.max(...items.map((i) => i.tokens), 1);
  $("ctx-total").textContent = "≈ " + data.context.total_tokens + " tokens";
  $("ctx-spectrum").innerHTML = items
    .map((i) => `<div class="bar" style="height:${Math.round((i.tokens / max) * 100)}%" title="${i.label}"></div>`)
    .join("");
  $("ctx-legend").innerHTML = items
    .map((i) => `<li><b>${escapeHtml(i.label)}</b><span class="n">≈ ${i.tokens}</span></li>`)
    .join("");
  const pr = data.prompt || {};
  $("prompt-full").value = "[system]\n" + (pr.system || "") + "\n\n[user]\n" + (pr.user || "");

  // review
  const p = data.proposal;
  $("diff-original").textContent = selected;
  if (data.error) {
    $("status-line").innerHTML = `<span class="warn">Error: ${escapeHtml(data.error)}</span>`;
    $("diff-proposed").textContent = "";
    setDecision(false);
    return;
  }
  $("diff-proposed").textContent = p.replacement_text;
  const bits = [p.mock ? "Mock (no provider)" : "Model response", p.explanation];
  if (p.warnings && p.warnings.length) bits.push("⚠ " + p.warnings.join(" · "));
  $("status-line").innerHTML = bits.filter(Boolean).map(escapeHtml).join(" — ");
  setDecision(true);
}

function setDecision(enabled) {
  $("accept").disabled = !enabled;
}

function accept() {
  if (!pending) return;
  const text = editor.value;
  editor.value = text.slice(0, pending.start) + $("diff-proposed").textContent + text.slice(pending.end);
  pending = null;
  closeDock();
  buildOutline(); markActiveSection(); renderPreview();
  toast("Edit applied.");
}

function closeDock() { $("dock").hidden = true; pending = null; }

// ---- file open/save ------------------------------------------------------
function updateFilename() {
  $("filename").textContent = currentName || "example (unsaved)";
}

async function refreshFiles() {
  let data;
  try {
    data = await (await fetch("/api/files")).json();
  } catch (e) {
    return toast("Could not list files: " + e.message);
  }
  const sel = $("file-open");
  sel.innerHTML = '<option value="" disabled selected>Open…</option>';
  (data.files || []).forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    sel.appendChild(opt);
  });
  if (currentName) sel.value = currentName;
}

async function openFile(name) {
  let data;
  try {
    const res = await fetch("/api/file/" + encodeURIComponent(name));
    data = await res.json();
    if (!res.ok) return toast("Open failed: " + (data.detail || res.statusText));
  } catch (e) {
    return toast("Open failed: " + e.message);
  }
  editor.value = data.text;
  currentName = data.name;
  dirty = false;
  closeDock();
  renderPreview(); buildOutline(); markActiveSection(); updateFilename();
  refreshSummaryStatus(); refreshContextMap();  // reflect this doc's loaded summaries
  toast("Opened " + name);
}

function newFile() {
  if (dirty && !confirm("Discard unsaved changes?")) return;
  editor.value = "# Untitled\n\n";
  currentName = null;             // unsaved; Save will prompt for a name
  dirty = false;
  $("file-open").value = "";
  closeDock();
  renderPreview(); buildOutline(); markActiveSection(); updateFilename();
  refreshSummaryStatus(); refreshContextMap();
  editor.focus();
  editor.setSelectionRange(editor.value.length, editor.value.length);
  toast("New document");
}

async function saveFile() {
  let name = currentName;
  if (!name) {
    name = prompt("Save as (filename.md):", "untitled.md");
    if (!name) return;
    if (!name.endsWith(".md")) name += ".md";
  }
  let data;
  try {
    const res = await fetch("/api/file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, text: editor.value }),
    });
    data = await res.json();
    if (!res.ok || !data.ok) return toast("Save failed: " + (data.detail || res.statusText));
  } catch (e) {
    return toast("Save failed: " + e.message);
  }
  currentName = data.name;
  dirty = false;
  updateFilename();
  await refreshFiles();
  toast("Saved " + data.name);
}

// ---- summaries (autosave, background refresh, manual regenerate) -------
async function autosaveTick() {
  if (!dirty || !currentName) return;
  try {
    await saveFile(); // clears `dirty`, updates state, toasts "Saved <name>"
  } catch (e) {
    toast("Autosave failed: " + e.message);
  }
}

async function summaryTick() {
  try {
    const res = await fetch("/api/summaries/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: editor.value, mode: "invalidated", provider: readSettings() }),
    });
    const data = await res.json();
    if (!res.ok) return; // silent — background tick
    toast(`Summaries: ${data.generated} regenerated, ${data.checked} checked`);
    setUsage(data.usage);
    refreshSummaryStatus();
  } catch {
    /* silent — background tick, never surface an error */
  }
}

async function refreshSummaryStatus() {
  const el = $("summary-status");
  try {
    const res = await fetch("/api/summaries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: editor.value }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "status failed");
    el.textContent = data.summarized + "/" + data.total + " summarized";
  } catch {
    el.textContent = ""; // degrade gracefully — status is best-effort
  }
}

async function regenerateSummaries() {
  let est;
  try {
    const res = await fetch("/api/summaries/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: editor.value, mode: "sync" }),
    });
    est = await res.json();
    if (!res.ok) return toast("Estimate failed: " + (est.detail || res.statusText));
  } catch (e) {
    return toast("Estimate failed: " + e.message);
  }
  if (est.count === 0) return toast("Summaries already up to date.");
  if (!confirm("~" + est.est_tokens + " tokens for " + est.count + " summaries (missing + changed). Continue?")) return;
  try {
    const res = await fetch("/api/summaries/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: editor.value, mode: "sync", provider: readSettings() }),
    });
    const data = await res.json();
    if (!res.ok) return toast("Regenerate failed: " + (data.detail || res.statusText));
    toast(data.error
      ? "Regenerate: " + data.error
      : `Summaries: ${data.generated} generated, ${data.skipped} skipped`);
    setUsage(data.usage);
  } catch (e) {
    return toast("Regenerate failed: " + e.message);
  }
  refreshSummaryStatus();
}

// ---- helpers ------------------------------------------------------------
function fmtTok(n) { return n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n); }
function setUsage(u) {
  if (!u) return;
  $("usage").textContent = "Σ " + fmtTok((u.input || 0) + (u.output || 0)) + " tok";
  $("usage").title = `in ${u.input || 0} · out ${u.output || 0} · ${u.calls || 0} calls`;
}
async function refreshUsage() { try { setUsage(await (await fetch("/api/usage")).json()); } catch { /* ignore */ } }
function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
let toastTimer = null;
function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(hideToast, 2600);
}
function hideToast() { $("toast").hidden = true; }

// ---- left sidebar (collapsible, toggled by Settings) --------------------
let sidebarOpen = localStorage.getItem("mdpad.sidebarOpen") !== "0";

function setSidebar(open) {
  sidebarOpen = open;
  localStorage.setItem("mdpad.sidebarOpen", open ? "1" : "0");
  const saved = JSON.parse(localStorage.getItem("mdpad.layout") || "{}");
  const ws = document.querySelector(".workspace");
  ws.style.setProperty("--w-sidebar", open ? (saved.sidebar || 232) + "px" : "0");
  ws.style.setProperty("--gw-sidebar", open ? "6px" : "0");  // collapse the gutter column too
  if (open) $("settings").hidden = false;
}

// ---- summary-context panel ---------------------------------------------
let mapOpen = localStorage.getItem("mdpad.mapOpen") === "1";
let mapTimer = null;

function setMap(open) {
  mapOpen = open;
  localStorage.setItem("mdpad.mapOpen", open ? "1" : "0");
  const saved = JSON.parse(localStorage.getItem("mdpad.layout") || "{}");
  const ws = document.querySelector(".workspace");
  ws.style.setProperty("--w-map", open ? (saved.map || 300) + "px" : "0");
  ws.style.setProperty("--gw-map", open ? "6px" : "0");  // collapse the gutter column too
  $("map-toggle").classList.toggle("on", open);
  if (open) refreshContextMap();
}
function scheduleMap() {
  if (!mapOpen) return;
  clearTimeout(mapTimer);
  mapTimer = setTimeout(refreshContextMap, 250);
}
let mapView = localStorage.getItem("mdpad.mapView") || "text";
let _lastMap = null;

async function refreshContextMap() {
  if (!mapOpen) return;
  try {
    const res = await fetch("/api/context/map", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: editor.value, offset: editor.selectionStart }),
    });
    _lastMap = await res.json();
  } catch { return; }
  renderContextMap(_lastMap);
}

function renderContextMap(data) {
  const el = $("context-map");
  el.innerHTML = "";
  const head = document.createElement("div");
  head.className = "map-head";
  const title = document.createElement("span");
  title.textContent = "Context hierarchy";
  const toggle = document.createElement("button");
  toggle.className = "ghost map-view";
  toggle.textContent = mapView === "visual" ? "Text" : "Visual";
  toggle.title = "Toggle text / visual view";
  toggle.addEventListener("click", () => {
    mapView = mapView === "visual" ? "text" : "visual";
    localStorage.setItem("mdpad.mapView", mapView);
    if (_lastMap) renderContextMap(_lastMap);
  });
  head.appendChild(title); head.appendChild(toggle);
  el.appendChild(head);

  const c = data.counts || {};
  const counts = document.createElement("div");
  counts.className = "map-counts";
  counts.textContent = `valid ${c.valid || 0} · stale ${(c.stale || 0) + (c.expired || 0)} · missing ${c.missing || 0}`;
  el.appendChild(counts);

  const levels = (data.tree && data.tree.levels) || [];
  if (mapView === "visual") renderMapVisual(el, levels);
  else renderMapText(el, levels);
}

function renderMapText(el, levels) {
  const tree = document.createElement("div");
  tree.className = "map-tree";
  levels.forEach((lvl) => {
    const block = document.createElement("div");
    block.className = "map-level-block";
    block.style.paddingLeft = (lvl.level * 12) + "px";
    const label = document.createElement("div");
    label.className = "map-level";
    label.textContent = "L" + lvl.level;
    block.appendChild(label);
    [[lvl.prev, false], [lvl.current, true], [lvl.next, false]].forEach(([node, isCurrent]) => {
      if (!node) return;
      const row = document.createElement("div");
      row.className = "map-tree-row" + (isCurrent ? " current" : "");
      attachTip(row, node.summary || node.title);
      const dot = document.createElement("span");
      dot.className = "dot state-" + (node.state || "missing");
      const t = document.createElement("span");
      t.className = "title";
      t.textContent = node.title || "";
      row.appendChild(dot); row.appendChild(t);
      block.appendChild(row);
    });
    tree.appendChild(block);
  });
  el.appendChild(tree);
}

const SVGNS = "http://www.w3.org/2000/svg";
function _svg(tag, attrs) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}
function _tipped(el, text) {
  const t = _svg("title", {}); t.textContent = text || ""; el.appendChild(t); return el;
}

// Custom hover tooltip that renders the summary as markdown + KaTeX (the native
// `title` attribute can only show plain text).
function showTip(summary, x, y) {
  const tip = $("map-tip");
  // Set raw text (not markdown-it) so KaTeX sees intact $...$ / backslashes;
  // markdown would eat "_", strip escapes, and break the math.
  tip.textContent = summary || "";
  if (window.renderMathInElement) {
    window.renderMathInElement(tip, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
    });
  }
  tip.hidden = false;
  posTip(x, y);
}
function posTip(x, y) {
  const tip = $("map-tip");
  if (tip.hidden) return;
  const pad = 14, r = tip.getBoundingClientRect();
  let px = x + pad, py = y + pad;
  if (px + r.width > window.innerWidth) px = x - r.width - pad;
  if (py + r.height > window.innerHeight) py = window.innerHeight - r.height - pad;
  tip.style.left = Math.max(4, px) + "px";
  tip.style.top = Math.max(4, py) + "px";
}
function hideTip() { $("map-tip").hidden = true; }
function attachTip(el, summary) {
  el.addEventListener("mouseenter", (e) => showTip(summary, e.clientX, e.clientY));
  el.addEventListener("mousemove", (e) => posTip(e.clientX, e.clientY));
  el.addEventListener("mouseleave", hideTip);
}
// A node-link view: current nodes form the vertical spine; each splits into the
// next level's previous/current/next. Title in the circle's label, summary on hover.
function renderMapVisual(el, levels) {
  const width = el.clientWidth || 300;
  const rowH = 76, r = 15, padY = 34;
  const cx = width / 2;
  const offset = Math.min(width * 0.30, 108);
  const height = padY * 2 + Math.max(0, levels.length - 1) * rowH;
  const svg = _svg("svg", { class: "map-svg", width: "100%", viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "xMidYMin meet" });
  const pos = (i, role) => ({ x: role === "prev" ? cx - offset : role === "next" ? cx + offset : cx, y: padY + i * rowH });

  for (let i = 1; i < levels.length; i++) {
    const p = pos(i - 1, "current");
    ["prev", "current", "next"].forEach((role) => {
      if (!levels[i][role]) return;
      const cc = pos(i, role);
      svg.appendChild(_svg("line", { class: "map-edge", x1: p.x, y1: p.y, x2: cc.x, y2: cc.y }));
    });
  }
  levels.forEach((lvl, i) => {
    ["prev", "current", "next"].forEach((role) => {
      const n = lvl[role];
      if (!n) return;
      const { x, y } = pos(i, role);
      const isCur = role === "current";
      const g = _svg("g", { class: "map-node" + (isCur ? " cur" : "") + " state-" + (n.state || "missing") });
      g.appendChild(_svg("circle", { cx: x, cy: y, r: isCur ? r + 3 : r }));
      const label = _svg("text", { x: x, y: y + (isCur ? r + 3 : r) + 12, "text-anchor": "middle", class: "map-node-label" });
      const words = (n.title || "").split(/\s+/).slice(0, 3).join(" ");
      label.textContent = words.length > 18 ? words.slice(0, 17) + "…" : words;
      g.appendChild(label);
      attachTip(g, n.summary || n.title);
      svg.appendChild(g);
    });
  });
  el.appendChild(svg);
}

// ---- wiring -------------------------------------------------------------
document.querySelectorAll(".act").forEach((btn) =>
  btn.addEventListener("click", () => {
    const act = btn.dataset.act;
    if (act === "custom") openCustom();
    else runAction(ACTIONS[act]);
  })
);
function openCustom() {
  if (editor.selectionStart === editor.selectionEnd) return toast("Select some text first.");
  $("custom-bar").hidden = false;
  const input = $("custom-instr");
  input.value = "";
  input.focus();
}
$("custom-instr").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    const v = $("custom-instr").value.trim();
    $("custom-bar").hidden = true;
    if (v) runAction(v);
  } else if (e.key === "Escape") {
    e.preventDefault();
    $("custom-bar").hidden = true;
    editor.focus();
  }
});
$("settings-toggle").addEventListener("click", () => {
  setSidebar(!sidebarOpen);
});
["p-model", "p-temp", "p-max"].forEach((id) =>
  $(id).addEventListener("change", saveSettings)
);
// Changing the endpoint/key re-lists models against it.
["p-base", "p-key"].forEach((id) =>
  $(id).addEventListener("change", () => { saveSettings(); fetchModels(); })
);
$("p-refresh").addEventListener("click", fetchModels);
$("accept").addEventListener("click", accept);
$("reject").addEventListener("click", closeDock);
$("dock-close").addEventListener("click", closeDock);
editor.addEventListener("input", () => { dirty = true; scheduleRender(); buildOutline(); markActiveSection(); scheduleMap(); });
$("map-toggle").addEventListener("click", () => setMap(!mapOpen));
editor.addEventListener("keyup", markActiveSection);
editor.addEventListener("click", markActiveSection);
// block-level selection sync: highlight on any selection change, scroll on mouseup
document.addEventListener("selectionchange", () => {
  if (document.activeElement === editor) { syncFromEditor(false); scheduleMap(); }
});
editor.addEventListener("mouseup", () => syncFromEditor(true));
preview.addEventListener("click", (e) => {
  const el = e.target.closest("[data-line-start]");
  if (el) selectSourceLines(el);
});
// double-click a block -> scroll the counterpart pane to the same block
preview.addEventListener("dblclick", (e) => {
  const el = e.target.closest("[data-line-start]");
  if (el) { selectSourceLines(el); scrollEditorToLine(+el.getAttribute("data-line-start")); }
});
editor.addEventListener("dblclick", () => syncFromEditor(true));
$("file-open").addEventListener("change", (e) => {
  const name = e.target.value;
  if (dirty && !confirm("Discard unsaved changes?")) {
    e.target.value = currentName || "";
    return;
  }
  openFile(name);
});
$("save").addEventListener("click", saveFile);
$("new-file").addEventListener("click", newFile);
$("regen-summaries").addEventListener("click", regenerateSummaries);

// ---- boot ---------------------------------------------------------------
(async function boot() {
  loadSettings();
  try {
    const doc = await (await fetch("/api/document")).json();
    editor.value = doc.text;
    currentName = doc.name || null;
  } catch {
    editor.value = "# mdpad\n\nCould not load the example document.";
    currentName = null;
  }
  dirty = false;
  updateFilename();
  initResizers();
  await refreshFiles();
  await initProvider();
  renderPreview(); buildOutline(); markActiveSection();
  refreshSummaryStatus();
  refreshUsage();
  setSidebar(sidebarOpen);
  setMap(mapOpen);
  setInterval(autosaveTick, 30000);
  setInterval(summaryTick, 600000);
})();
