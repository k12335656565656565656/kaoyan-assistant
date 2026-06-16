# AGENTS.md

## Project Goal

Build a professional-course subject knowledge recognition system inside the existing Streamlit exam assistant.

This module is not an OCR-only feature. Its purpose is to convert uploaded or pasted course material into reviewable, user-confirmed knowledge points that can be stored in a private knowledge base and reused for later study workflows.

## Core Product Workflow

1. User uploads a PDF, uploads an image, or pastes raw text into one unified material input area.
2. System routes the material through the correct extraction path.
3. System returns a unified extraction result with source type, processing method, extracted text, confidence, and warnings.
4. User reviews and manually edits extracted text before any knowledge extraction starts.
5. AI generates structured draft knowledge points in JSON.
6. User edits, deletes, and confirms draft knowledge points.
7. Confirmed knowledge points are saved into the user's private knowledge base.
8. Confirmed knowledge points can later power explanations, review cards, exam-style questions, and follow-up expansion.

## MVP Priority

Focus on the smallest end-to-end workflow that creates trustworthy knowledge points:

1. Unified material input
2. Reliable text extraction routing
3. Manual extracted-text confirmation
4. Structured draft knowledge point generation
5. User confirmation flow
6. Safe persistence of confirmed knowledge points

Defer advanced automation, polishing, and secondary study tools until the confirmation loop is working.

## Coding Rules

- Keep changes small, isolated, and reviewable.
- Do not rewrite the whole app to introduce this feature.
- Do not modify unrelated modules.
- Prefer adding new logic in `services/`, `repositories/`, `schemas/`, and `pages/` rather than expanding `app.py`.
- Keep Streamlit page code thin and move business rules into reusable Python modules.
- Use environment variables for API keys and secrets. Never hardcode credentials in new code.
- Update `requirements.txt` only when a new dependency is truly required.
- Preserve current user-facing behavior unless the task explicitly changes it.
- Prefer stable data contracts over ad hoc dictionaries spread through page code.

## Database Migration Rules

- Never drop existing tables as part of this project work.
- Never delete existing user data during a migration.
- Add columns and tables in a backward-compatible way.
- Make old rows readable even if new fields are missing.
- Centralize database reads and writes in repository modules.
- Include a safe migration path before any code depends on a new schema.

## LLM Output Rules

- Knowledge extraction output must be valid JSON, not a plain summary.
- Every draft knowledge point should preserve `source_text` from the original material.
- Distinguish source-grounded extraction from AI expansion.
- If a field is inferred or weakly supported, mark it as uncertain or AI expansion.
- Do not present unsupported facts as confirmed knowledge.
- Keep the output schema stable even when some fields are empty.

## Before-Editing Checklist

- Confirm the task scope and avoid unrelated cleanup.
- Read the relevant page, service, repository, and schema files first.
- Check whether an existing utility already solves part of the problem.
- Identify whether the change requires new dependencies, schema updates, or environment variables.
- Verify that the proposed change preserves the extracted-text confirmation step before knowledge extraction.
- Plan the smallest reviewable change set.

## After-Editing Checklist

- Re-read the edited files for scope creep and unintended side effects.
- Verify imports, function boundaries, and naming consistency.
- Confirm that secrets were not introduced into code, logs, or commands.
- Confirm that knowledge extraction still expects structured JSON output.
- Confirm that any schema or migration change preserves existing data.
- Update related documentation or task tracking when architecture or workflow assumptions change.
- Summarize assumptions and remaining follow-up work for the next task.
