# Architecture Notes

## Current High-Level Architecture Assumption

Based on the current repository layout, the app appears to be a Streamlit application with a large `app.py` entry point and SQLite-backed persistence.

Assumptions:

- Streamlit currently handles both UI and a large share of business logic
- SQLite is used for user-scoped application data
- Existing knowledge-base capabilities already exist in adjacent modules and can inform future extraction work
- The new professional-course workflow should be added incrementally rather than through a rewrite

## Recommended Target Architecture

Introduce the new workflow as a small set of focused modules that reduce pressure on `app.py`.

Recommended layout:

```text
services/
  material_router.py
  ocr_service.py
  pdf_text_service.py
  llm_service.py
  knowledge_extractor.py
  review_card_service.py

repositories/
  material_repo.py
  knowledge_repo.py

schemas/
  material_schema.py
  knowledge_schema.py

pages/
  material_workspace.py
  knowledge_editor.py
  review_cards.py
```

## Professional Knowledge Workflow Foundation (2026-07)

The first stability pass now implements the following boundaries:

- `professional_knowledge/default_subjects.json` is the bundled subject registry; personal overrides are merged from `data/config/custom_subjects.json`.
- `repositories/material_repo.py` owns backward-compatible material schema migration, extraction persistence, confirmed text, workflow snapshots, status, and resume queries.
- `repositories/knowledge_repo.py` owns idempotent confirmed-point writes and material count reconciliation.
- `knowledge_base.py` still contains Streamlit orchestration, but material writes no longer depend on page-local SQL or session state alone.

The next decomposition target is to move the import, confirmation, and repository views out of `knowledge_base.py` into focused page modules without changing this persistence contract.

## Separation of Responsibilities

### Services

Service modules should hold business logic and orchestration.

- `material_router.py`: choose extraction route and normalize output
- `ocr_service.py`: image OCR and OCR fallback for PDFs
- `pdf_text_service.py`: direct PDF text extraction and quality checks
- `llm_service.py`: model client, prompting wrapper, retry handling, JSON validation hooks
- `knowledge_extractor.py`: transform confirmed text into structured draft knowledge points
- `review_card_service.py`: later-stage study artifact generation

### Repositories

Repository modules should own database persistence and retrieval.

- `material_repo.py`: persist material metadata, extraction results, and traceability fields if needed
- `knowledge_repo.py`: draft and confirmed knowledge-point storage, retrieval, and update logic

### Schemas

Schema modules should define stable data contracts.

- `material_schema.py`: unified extraction result, status fields, and validation helpers
- `knowledge_schema.py`: draft and confirmed knowledge-point structures

### Pages

Page modules should focus on user interaction.

- `material_workspace.py`: unified material input and extracted-text confirmation
- `knowledge_editor.py`: draft review, edit, delete, and confirm workflow
- `review_cards.py`: later review artifact display and generation

## Material Routing Pipeline

The extraction path should normalize all inputs into one contract before any knowledge extraction begins.

Pipeline:

1. Receive one of three input types: PDF, image, or pasted text
2. Detect source type and call the appropriate handler
3. Run text cleanup and quality checks
4. Return a unified result object
5. Present extracted text to the user for manual correction
6. Wait for user confirmation before continuing

Suggested result object:

```json
{
  "source_type": "pdf | image | pasted_text",
  "process_method": "pdf_text_extract | pdf_ocr | image_ocr | pasted_text",
  "extracted_text": "...",
  "confidence": 0.0,
  "warnings": []
}
```

Routing behavior:

- Pasted text uses direct cleanup
- Image uses OCR
- PDF uses direct extraction first
- PDF falls back to OCR when extracted text is too short, low-confidence, or visibly garbled

## Knowledge Extraction Pipeline

The knowledge extraction path should be source-aware, reviewable, and safe by default.

Pipeline:

1. Receive user-confirmed extracted text
2. Split or segment text as needed for model limits
3. Ask the LLM for structured draft knowledge points in JSON
4. Validate JSON shape before using it
5. Attach or preserve source evidence for each draft item
6. Mark uncertain or expanded fields explicitly
7. Present drafts in an editable confirmation UI
8. Save only user-confirmed knowledge points

Trust constraints:

- Source-grounded content should remain distinguishable from AI expansion
- Unsupported facts must never be treated as confirmed knowledge
- The system should fail safely when JSON is invalid or extraction quality is too poor
