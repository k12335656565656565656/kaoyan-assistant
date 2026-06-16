# Development Roadmap

## PR 1: Secret Management And Dependency Cleanup

Goal:
Move new and existing secret usage toward environment-variable-based configuration and remove avoidable dependency confusion.

Scope:

- Define environment-variable conventions for API keys
- Audit current secret handling
- Identify unused or duplicated dependencies
- Update documentation for local setup and deployment expectations

## PR 2: Unified Material Input Router

Goal:
Create one material workspace that supports PDF upload, image upload, and pasted text with shared routing behavior.

Scope:

- Add unified input UI
- Add source-type detection
- Add a normalized extraction result object
- Implement PDF direct extraction plus OCR fallback rules
- Show extraction warnings and confidence

## PR 3: Structured Knowledge Point Schema

Goal:
Define stable schema objects for draft and confirmed knowledge points.

Scope:

- Create schema definitions for extraction results and knowledge points
- Include source evidence fields
- Distinguish AI expansion from source-grounded content
- Plan backward-compatible persistence fields

## PR 4: JSON-Based Knowledge Extraction

Goal:
Generate structured draft knowledge points from confirmed text in machine-validated JSON.

Scope:

- Add LLM prompt templates focused on schema output
- Validate JSON before downstream use
- Add fallback handling for malformed model output
- Preserve source text in every draft item

## PR 5: Editable Draft Knowledge Point Confirmation UI

Goal:
Let users review, edit, delete, and confirm generated draft knowledge points.

Scope:

- Build an editor flow for draft items
- Prevent saving before user confirmation
- Surface uncertain fields clearly
- Keep the page state stable across Streamlit reruns

## PR 6: Confirmed Knowledge Point Persistence

Goal:
Save only confirmed knowledge points into the user's private knowledge base.

Scope:

- Add repository methods for insert, update, and retrieval
- Introduce safe schema migration if needed
- Preserve user isolation and source traceability
- Keep draft and confirmed states conceptually separate

## PR 7: Review Card Generation

Goal:
Generate reusable review cards from confirmed knowledge points.

Scope:

- Define card-generation inputs and outputs
- Generate concise review artifacts from confirmed data
- Keep the workflow source-aware and user-traceable
- Prepare for future spaced-review features

## PR 8: OCR/PDF Extraction Quality Improvements

Goal:
Increase extraction quality and routing confidence after the MVP flow works end to end.

Scope:

- Improve garbled-text detection
- Tune PDF text extraction thresholds
- Improve OCR preprocessing and confidence heuristics
- Add better user warnings and recovery actions
