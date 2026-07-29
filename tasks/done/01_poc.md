# Proof of Concept (PoC)

## Goal

Build a one-evening prototype demonstrating AI-assisted editing of a long scientific document using structured context instead of naïve copy-paste.

The prototype is **not** intended to become production software.

It is an experiment to validate the workflow.

Success criterion:

> A researcher should feel that editing a long technical manuscript is substantially easier than using ChatGPT together with Overleaf or a normal Markdown editor.

Time budget:

1-2 efficient hours.

---

# Non-goals

Do NOT implement:

- authentication
- collaboration
- cloud backend
- user management
- vector databases
- autonomous agents
- fine tuning
- PDF export
- Git integration
- citations
- bibliography management
- document indexing
- complex knowledge graphs

Those belong to later iterations.

---

# Technology

Backend

- Python
- FastAPI

Frontend

- React
- TypeScript
- Vite

Editor

- CodeMirror 6

Rendering

- markdown-it
- KaTeX

Communication

REST API only.

No websocket required.

Storage

Local files.

SQLite only if clearly useful.

---

# Project structure

backend/

frontend/

example_project/

README.md

docker-compose.yml

---

# Example project

Create one example project.

```
example_project/

book.md

project.yaml

sections/
```

book.md should contain several sections with formulas.

Example:

# Introduction

...

## Representation Spaces

...

## MuRS

...

## Spectral View

...

This will be used during testing.

---

# UI

Single page.

Split layout.

-----------------------------------------

Sidebar

|

Markdown editor

|

Rendered preview

-----------------------------------------

Bottom panel

Status

Errors

Model output

-----------------------------------------

Sidebar contains

- document outline
- settings
- API configuration

Nothing more.

---

# Markdown editor

Requirements

- syntax highlighting
- undo
- standard shortcuts

Support

Markdown

LaTeX math

No rich text editing.

Markdown is the source of truth.

---

# Live preview

Render continuously.

Debounce updates.

Approximately

300–500 ms.

Render

- headings
- lists
- tables
- math

Scrolling should remain smooth.

---

# Section parsing

Automatically parse

# Chapter

## Section

### Subsection

Each section receives

id

title

content

path

line numbers

No manual IDs required.

---

# Metadata

Each section has metadata.

Initially generated automatically.

Editable.

Fields

summary

concepts

status

notes

Example

summary:
  Introduces representation geometry.

concepts:
  - representation
  - geometry

status:
  draft

notes:

Metadata may be stored separately.

Do not modify Markdown.

---

# Text selection

User selects text.

Context menu appears.

Actions

Rewrite

Expand

Shorten

Custom

---

# Custom instruction

Popup

Multi-line textbox.

Example

"Remove unsupported claims."

or

"Rewrite more rigorously."

---

# Context package

This is the important part.

Before sending anything to the LLM build

Project summary

↓

Current section metadata

↓

Current section

↓

Selected text

↓

User instruction

Display this package.

User should know exactly what was sent.

---

# Provider settings

Simple settings page.

Fields

Provider

Base URL

API key

Model

Temperature

Maximum tokens

Support

OpenAI

OpenRouter

LM Studio

Ollama

Any OpenAI-compatible endpoint.

---

# Backend prompt

System prompt

Scientific writing assistant.

Never invent citations.

Preserve equations.

Distinguish facts from hypotheses.

User prompt

Contains

project

section

selection

instruction

No conversation history.

---

# Response

Return JSON.

{
    replacement_text

    explanation

    warnings
}

No markdown.

Backend validates schema.

---

# Diff viewer

Never overwrite text automatically.

Show

Original

↓

Replacement

Buttons

Accept

Reject

Only on Accept

replace source text.

---

# Status panel

Display

selected section

tokens sent

response time

estimated cost

errors

warnings

---

# Error handling

Missing API key

Invalid endpoint

Timeout

Invalid JSON

Render errors

Should all be visible.

No crashes.

---

# Logging

Console only.

Log

request size

response size

latency

No telemetry.

---

# Testing workflow

Open book.md

↓

Navigate to "MuRS"

↓

Select one paragraph

↓

Custom instruction

"Rewrite to distinguish observations from hypotheses."

↓

Review diff

↓

Accept

↓

Preview updates

↓

Continue editing

Entire process should require under one minute.

---

# Acceptance criteria

The prototype is complete when all of the following work.

✓ Open Markdown project

✓ Live preview

✓ Render formulas

✓ Parse sections

✓ Select text

✓ Build context package

✓ Send request

✓ Receive JSON

✓ Show diff

✓ Accept replacement

✓ Reject replacement

✓ Continue editing

---

# Nice to have

Not required.

Section summaries generated automatically.

Recent prompts.

Dark mode.

Collapsible sidebar.

Keyboard shortcut

Ctrl+Enter

to submit.

---

# Deliverables

Running application.

README.

Docker Compose.

Example project.

Short demo GIF.

No unfinished experimental features.

The code should be simple, readable, and easy to extend.