# Development brief: Context-aware agentic scientific writing environment

## 1. Product objective

Build a local-first prototype for writing and revising a long technical document with AI assistance.

The application should combine:

* a Markdown or LaTeX editor;
* a continuously rendered document preview;
* selection-based AI editing;
* structured document metadata;
* a persistent concept and dependency map;
* context retrieval limited to the material relevant to the selected section;
* support for OpenAI-compatible APIs and local model endpoints;
* version history and transparent application of edits.

The first target use case is the preparation of a technical vision/review book on representation dynamics and the physics of information processing.

The architecture should nevertheless remain generic enough for papers, reports, theses, grant applications, and books.

## 2. Core design principle

The model should not receive the entire manuscript on every request.

Instead, each request should construct a compact context package from:

1. the selected text;
2. the containing section;
3. the section’s metadata;
4. directly linked concepts;
5. dependent or referenced sections;
6. relevant source notes;
7. a short global manuscript description;
8. the current user instruction.

The context package must be visible and inspectable by the user.

## 3. Prototype scope

### Required

* Local web application.
* Markdown source editing.
* Mathematical notation using LaTeX syntax.
* Live rendered preview.
* Cached rendering.
* Selection-based AI actions.
* Direct manual editing.
* Section and concept metadata.
* OpenAI-compatible API configuration.
* Local endpoint configuration.
* Diff preview before accepting AI changes.
* Undo and version history.
* Project import and export as a ZIP archive.
* Error and diagnostics panel.

### Not required in version 1

* Real-time multi-user collaboration.
* Fine-tuning.
* custom model training;
* token-level semantic annotation of the entire manuscript;
* complete LaTeX package compatibility;
* publication-quality PDF typography;
* autonomous unsupervised rewriting of the entire book;
* proprietary cloud infrastructure.

## 4. Recommended technology stack

### Front end

* React with TypeScript.
* CodeMirror 6 or Monaco Editor.
* Split-pane interface.
* KaTeX for fast mathematical rendering.
* Markdown-it, unified/remark, or equivalent Markdown parser.
* React Flow or Cytoscape.js for the concept map.
* IndexedDB for local caching and recovery.

### Back end

Preferred:

* Python with FastAPI.

Alternative:

* Node.js if the development team strongly prefers a single-language stack.

Python is preferred because the later research functionality will likely use:

* embeddings;
* scientific Python;
* graph analysis;
* document processing;
* local model inference;
* experimental representation analysis.

### Storage

For the prototype:

* SQLite;
* project files on disk;
* JSON or YAML metadata;
* Git-compatible plain-text document storage.

### Packaging

* Docker Compose for reproducible startup.
* Optional desktop packaging through Tauri after the web prototype is stable.

Electron should be avoided unless required, because it adds considerable overhead.

## 5. User interface

### Main workspace

The primary screen contains:

#### Left pane: source editor

The user edits Markdown containing LaTeX mathematics.

#### Right pane: rendered preview

The preview updates after a short debounce interval.

Rendered blocks should be cached by content hash. Unchanged sections must not be rerendered when the user scrolls or modifies an unrelated section.

#### Collapsible project sidebar

Contains:

* document tree;
* chapters and sections;
* source notes;
* concepts;
* unresolved questions;
* figures;
* model sessions;
* version history.

#### Bottom or side diagnostics panel

Contains:

* Markdown parsing errors;
* LaTeX rendering errors;
* broken references;
* missing figure files;
* invalid metadata;
* API errors;
* context-construction logs.

## 6. Editing workflow

The user can select text in either the editor or preview and choose an action.

Initial actions:

* Rewrite.
* Shorten.
* Expand.
* Make more rigorous.
* Remove unsupported claims.
* Add mathematical formulation.
* Explain the argument.
* Challenge this section.
* Check consistency with the manuscript.
* Connect to another concept.
* Add citation placeholder.
* Convert notes into prose.
* Custom instruction.

Example:

> These formulas are bullshit. Remove the unjustified physical analogy and retain only what can presently be defended.

The application then:

1. identifies the selected text;
2. identifies its section;
3. constructs the context package;
4. sends the request to the configured model;
5. receives a proposed replacement;
6. displays a semantic and line-level diff;
7. shows any additional claims or assumptions introduced;
8. lets the user accept, reject, or modify the proposal.

The application must never silently replace text.

## 7. Document markup

Use ordinary Markdown as the canonical source format, with lightweight structured extensions.

Example:

```markdown
---
id: ch15-spectral-descriptions
title: Spectral descriptions of representation spaces
status: draft
purpose: Introduce intrinsic operators and mode decompositions.
claims:
  - spectral modes may separate reusable geometry from dataset-specific occupancy
concepts:
  - representation-geometry
  - graph-laplacian
  - mode-occupation
depends_on:
  - ch04-representation-geometry
  - ch14-geometry-versus-occupancy
sources:
  - asimov-1985-grand-tour
  - spectral-graph-reference
epistemic_status: proposed
---

## Spectral descriptions of representation spaces

...
```

This front matter is preferable to inserting proprietary control tokens into the prose.

The visible text remains portable and readable outside the application.

## 8. Section map

Every section should have a structured record.

Minimum schema:

```json
{
  "id": "ch15-spectral-descriptions",
  "title": "Spectral descriptions of representation spaces",
  "summary": "Introduces intrinsic operators and spectral mode occupation.",
  "purpose": "Connect geometry, transfer, and quantization.",
  "status": "draft",
  "epistemic_status": "proposed",
  "concept_ids": [
    "representation-geometry",
    "spectral-mode",
    "mode-occupation"
  ],
  "depends_on": [
    "ch04-representation-geometry"
  ],
  "supports": [
    "ch16-quantization"
  ],
  "source_ids": [],
  "open_questions": [],
  "last_reviewed": null
}
```

Allowed epistemic states should include:

* established;
* supported;
* observed;
* proposed;
* speculative;
* analogy;
* unresolved;
* contradicted.

This is especially important for scientific writing. The system must help prevent speculation from being rewritten as established fact.

## 9. Concept map

Concepts should be stored separately from sections.

Example:

```json
{
  "id": "mode-occupation",
  "name": "Mode occupation",
  "definition": "Probability mass or activity assigned to spectral modes.",
  "aliases": [
    "spectral occupancy"
  ],
  "related_concepts": [
    "spectral-mode",
    "probability-distribution",
    "quantization"
  ],
  "introduced_in": "ch15-spectral-descriptions",
  "used_in": [
    "ch16-quantization",
    "ch24-efficient-adaptation"
  ],
  "open_issues": [
    "Define the operator whose modes are occupied.",
    "Determine whether occupation is sample-specific or population-level."
  ]
}
```

The concept map should initially be built through:

* explicit metadata;
* headings;
* user-created links;
* model-suggested links requiring approval.

It should not initially depend on opaque fully automatic extraction.

## 10. Context construction

Context retrieval should use a hybrid system.

### Layer 1: deterministic structural retrieval

Always include:

* selected text;
* containing section;
* parent section summary;
* global manuscript abstract;
* explicitly linked concepts;
* direct dependencies;
* explicitly linked source notes.

### Layer 2: lexical retrieval

Use BM25 or SQLite FTS5 to retrieve passages with matching terminology.

### Layer 3: embedding retrieval

Use embeddings to retrieve semantically related sections or notes.

### Layer 4: graph expansion

Optionally add one-hop neighbours in the section and concept graphs.

### Layer 5: context compression

If the package exceeds the model budget:

* retain selected text verbatim;
* retain local section verbatim;
* summarize remote sections;
* deduplicate repeated definitions;
* retain formulas relevant to the request;
* remove unrelated prose.

The retrieval process should generate a visible manifest such as:

```text
Context used:
- Selected paragraph: 212 tokens
- Current section: 1,140 tokens
- Chapter summary: 180 tokens
- Concept: quantization
- Concept: mode occupation
- Dependency: geometry versus occupancy
- Source note: graph spectral decomposition
Total: 2,430 tokens
```

## 11. Prompt architecture

Use structured prompts rather than one generic conversation.

### System instruction

Define:

* scientific writing standards;
* prohibition against inventing citations;
* preservation of notation;
* respect for epistemic status;
* requirement to distinguish observation from proposal;
* requirement to output a patch rather than an entire manuscript.

### Manuscript context

Include:

* project description;
* audience;
* desired tone;
* notation conventions;
* global claims;
* glossary.

### Local context

Include the dynamically retrieved package.

### User request

Include the exact user instruction.

### Required response schema

The model should return structured JSON:

```json
{
  "replacement_text": "...",
  "change_summary": [
    "Removed unsupported claim of physical quantization.",
    "Retained spectral analogy as a research hypothesis."
  ],
  "new_claims": [],
  "new_terms": [],
  "suggested_links": [
    "ch14-geometry-versus-occupancy"
  ],
  "warnings": [
    "The operator defining the spectrum remains unspecified."
  ]
}
```

The backend must validate this schema.

## 12. Provider configuration

Support an OpenAI-compatible provider interface.

Configuration fields:

* provider name;
* base URL;
* API key;
* model identifier;
* embedding model identifier;
* maximum context size;
* temperature;
* timeout;
* additional HTTP headers.

Example providers:

* OpenAI API;
* OpenRouter;
* local llama.cpp server;
* Ollama, where compatible;
* vLLM;
* institutional proxy.

API keys must be stored in the operating system keychain where available. They must not be committed to project files.

For a browser-only prototype, API calls must go through the local backend so that the API key is not exposed to client-side code.

## 13. Rendering and caching

### Markdown rendering

Parse the document into an abstract syntax tree.

Each section or block receives a stable identifier.

### Cache key

Use a hash of:

* source block;
* renderer version;
* rendering options;
* referenced local assets.

### Behaviour

* Render only changed blocks.
* Store rendered HTML locally.
* Preserve scroll position between updates.
* Synchronize editor selection and preview position.
* Lazy-load images.
* Cache generated previews of PDF or SVG figures.
* Do not rerender the whole document on scrolling.

### Full PDF export

For publication output, provide a separate export step:

1. convert Markdown to LaTeX or use Pandoc;
2. compile through a controlled TeX environment;
3. report compilation errors;
4. cache the output PDF;
5. regenerate only when explicitly requested or after a configurable idle period.

## 14. Figures and assets

Project ZIP structure:

```text
project/
├── manuscript/
│   ├── book.md
│   └── sections/
├── metadata/
│   ├── sections.yaml
│   ├── concepts.yaml
│   ├── glossary.yaml
│   └── project.yaml
├── sources/
│   ├── notes/
│   └── bibliography.bib
├── assets/
│   ├── images/
│   ├── diagrams/
│   └── movies/
├── cache/
├── versions/
└── config/
    └── provider.example.yaml
```

Secrets must not be included in exported ZIP files.

## 15. Version control

Every accepted model change should create a revision record containing:

* timestamp;
* selected section;
* user instruction;
* context manifest;
* provider and model;
* proposed patch;
* accepted patch;
* optional user note.

The manuscript itself should remain compatible with Git.

The prototype may use an internal SQLite history, but exporting a clean Git repository should be possible.

## 16. Agent roles

Version 1 does not need a free-running autonomous agent.

Implement bounded agents as explicit commands.

### Editor agent

Rewrites selected text.

### Critic agent

Identifies weak reasoning, unsupported claims, undefined notation, and contradictions.

### Context curator

Suggests relevant sections, concepts, and source notes.

### Structure agent

Proposes chapter movement, merges, splits, and dependency changes.

### Consistency agent

Checks terminology, notation, definitions, and repeated claims.

### Research-gap agent

Lists statements requiring sources or experimental support.

Each action must be initiated by the user and produce a reviewable result.

## 17. Background indexing

When a section changes:

1. parse the changed section;
2. update its lexical index;
3. recompute its embedding;
4. update concept links if approved;
5. update dependent summaries;
6. flag sections that may now be inconsistent.

Do not re-embed the complete manuscript after every keystroke.

Use a debounce interval and content hashes.

## 18. Embeddings

Embeddings are useful but should not be treated as the manuscript’s fundamental representation.

Store one or more embeddings for:

* section summaries;
* full sections split into chunks;
* concept definitions;
* source notes.

Keep metadata linking every vector back to exact text offsets.

For the initial prototype, use:

* SQLite FTS5 for lexical retrieval;
* FAISS, sqlite-vec, or a simple local vector store for embeddings.

The application should remain functional without embeddings.

## 19. Fine-tuning

Do not include fine-tuning in the first prototype.

Reasons:

* there will initially be too little high-quality training data;
* the main problem is retrieval and editing control;
* user preferences can be represented through examples and structured instructions;
* provider models will change faster than a custom fine-tune can be maintained;
* a 96 GB GPU is not the limiting issue; dataset construction and evaluation are.

Log accepted and rejected edits from the beginning.

After sufficient data exists, evaluate:

* a small adapter for edit-style preference;
* a reranker for context selection;
* a classifier for epistemic status;
* a model for concept-link prediction;
* a domain-specific critic.

Fine-tuning the core writing model should be considered only after hundreds or preferably thousands of curated editing examples exist.

## 20. Minimal API endpoints

```text
POST /projects
GET  /projects/{project_id}
POST /projects/{project_id}/import
GET  /projects/{project_id}/export

GET  /documents/{document_id}
PATCH /documents/{document_id}

GET  /sections/{section_id}
PATCH /sections/{section_id}

POST /render/blocks
POST /render/pdf

POST /context/build
POST /agents/edit
POST /agents/critic
POST /agents/consistency
POST /agents/structure

GET  /revisions
POST /revisions/{revision_id}/accept
POST /revisions/{revision_id}/reject

GET  /providers
POST /providers/test

POST /index/update
POST /index/rebuild
```

## 21. Acceptance criteria for prototype

The prototype is successful when a user can:

1. import a ZIP project;
2. open a Markdown manuscript;
3. edit the source and see a synchronized rendered preview;
4. select a paragraph;
5. instruct a model to revise it;
6. inspect exactly which context was sent;
7. inspect a diff;
8. accept or reject the change;
9. undo the accepted change;
10. browse the section and concept maps;
11. export the complete project;
12. configure either OpenAI or an OpenAI-compatible local endpoint;
13. render a cached PDF;
14. view useful errors without examining server logs.

## 22. Suggested implementation phases

### Phase 1 — Editor foundation

* project format;
* Markdown editor;
* preview;
* mathematics;
* section parsing;
* cached block rendering;
* import and export.

### Phase 2 — Controlled AI editing

* provider interface;
* selection-based actions;
* context package;
* JSON response validation;
* diff review;
* revision history.

### Phase 3 — Structured context

* section metadata;
* concept records;
* dependency graph;
* lexical search;
* embedding retrieval;
* visible context manifest.

### Phase 4 — Scientific-quality controls

* epistemic status;
* notation checker;
* unsupported-claim warnings;
* citation placeholders;
* contradiction detection.

### Phase 5 — Productization

* desktop packaging;
* project templates;
* user onboarding;
* performance improvements;
* model cost reporting;
* optional collaboration.

## 23. First Claude Code instruction

Build Phase 1 and the smallest viable part of Phase 2.

Do not implement autonomous agents, fine-tuning, collaboration, or advanced graph inference.

The first deliverable must include:

* FastAPI backend;
* React and TypeScript frontend;
* CodeMirror Markdown editor;
* rendered Markdown and KaTeX preview;
* heading-based section parsing;
* block-level rendering cache;
* SQLite project metadata;
* OpenAI-compatible provider configuration;
* one “Revise selection” command;
* context consisting of selected text, current section, and project description;
* structured model response;
* diff acceptance;
* local revision history;
* ZIP project import and export;
* Docker Compose setup;
* README with exact run instructions;
* automated tests for section parsing, context construction, cache invalidation, and patch application.

Use plain, documented interfaces. Avoid premature abstraction. All model calls must be replaceable through one provider interface.
