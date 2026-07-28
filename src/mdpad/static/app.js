// mdpad frontend — one file, no build. Python does the interesting work; this
// wires the editor, live preview, outline, selection actions, and the diff.
"use strict";

const $ = (id) => document.getElementById(id);
const md = window.markdownit({ html: false, linkify: true, typographer: true });

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
        { left: "$", right: "$", display: false },
      ],
      throwOnError: false,
    });
  }
}

let renderTimer = null;
function renderPreview() {
  preview.innerHTML = md.render(editor.value);
  renderMath();
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

// ---- provider settings (localStorage) ----------------------------------
function loadSettings() {
  const s = JSON.parse(localStorage.getItem("mdpad.provider") || "{}");
  $("p-base").value = s.base_url || "";
  $("p-key").value = s.api_key || "";
  $("p-model").value = s.model || "";
  $("p-temp").value = s.temperature ?? 0.3;
  $("p-max").value = s.max_tokens ?? 1024;
  refreshProviderDot();
}
function readSettings() {
  return {
    base_url: $("p-base").value.trim(),
    api_key: $("p-key").value.trim(),
    model: $("p-model").value.trim(),
    temperature: parseFloat($("p-temp").value) || 0.3,
    max_tokens: parseInt($("p-max").value, 10) || 1024,
  };
}
function saveSettings() {
  const s = readSettings();
  localStorage.setItem("mdpad.provider", JSON.stringify(s));
  refreshProviderDot();
}
function refreshProviderDot() {
  const s = readSettings();
  $("provider-dot").classList.toggle("live", !!(s.base_url && s.api_key && s.model));
}

// ---- revise flow --------------------------------------------------------
async function runAction(instruction) {
  const start = editor.selectionStart, end = editor.selectionEnd;
  if (start === end) return toast("Select some text first.");
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
  toast("Opened " + name);
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

// ---- helpers ------------------------------------------------------------
function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
let toastTimer = null;
function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(hideToast, 2600);
}
function hideToast() { $("toast").hidden = true; }

// ---- wiring -------------------------------------------------------------
document.querySelectorAll(".act").forEach((btn) =>
  btn.addEventListener("click", () => {
    const act = btn.dataset.act;
    if (act === "custom") {
      const instr = prompt("Instruction for the selected text:");
      if (instr) runAction(instr);
    } else {
      runAction(ACTIONS[act]);
    }
  })
);
$("settings-toggle").addEventListener("click", () => {
  $("settings").hidden = !$("settings").hidden;
});
["p-base", "p-key", "p-model", "p-temp", "p-max"].forEach((id) =>
  $(id).addEventListener("change", saveSettings)
);
$("accept").addEventListener("click", accept);
$("reject").addEventListener("click", closeDock);
$("dock-close").addEventListener("click", closeDock);
editor.addEventListener("input", () => { dirty = true; scheduleRender(); buildOutline(); markActiveSection(); });
editor.addEventListener("keyup", markActiveSection);
editor.addEventListener("click", markActiveSection);
$("file-open").addEventListener("change", (e) => {
  const name = e.target.value;
  if (dirty && !confirm("Discard unsaved changes?")) {
    e.target.value = currentName || "";
    return;
  }
  openFile(name);
});
$("save").addEventListener("click", saveFile);

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
  await refreshFiles();
  renderPreview(); buildOutline(); markActiveSection();
})();
