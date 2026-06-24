# Architecture Migration Plan

## Goal

Refactor the current Streamlit monolith incrementally, using ideas from `D:\learn-claude-code`, without changing existing user-facing behavior unless a task explicitly requires it.

## Migration Principles

- Prefer extraction over rewrite.
- Keep each change small and reversible.
- Measure before and after with existing benchmark scripts.
- Move reusable logic into `services/`, `repositories/`, `schemas/`, and focused UI modules.

## Phase 1: Low-Risk Structure Extraction

Status: completed

Targets:

- Extract skill loading and prompt composition from `app.py`
- Keep existing behavior for active skill selection unchanged
- Avoid touching page rendering and API flow logic in the same step

Why this first:

- It maps directly to the `learn-claude-code` skill-loading pattern
- It is self-contained
- It reduces pressure on `app.py` without affecting the visible workflow

## Phase 2: LLM Gateway Consolidation

Status: completed

Targets:

- Centralize repeated chat completion request code
- Reuse one content extraction helper for `content` and `reasoning_content`
- Add retry, timeout, and error handling policies in one place

Reference idea:

- `learn-claude-code` error recovery and harness boundary design

Expected outcome:

- Less duplicated `urllib.request.Request(...)` logic
- Safer API failure handling
- Easier model configuration changes

## Phase 3: Thin Page Boundaries

Status: completed (third pass)

Targets:

- Move page-specific orchestration out of `app.py`
- Keep Streamlit page blocks as view logic and state wiring only
- Prioritize `material`, `english`, and `checkin` flows with the heaviest business logic

Expected outcome:

- `app.py` becomes a composition layer
- Core workflows become easier to test and evolve

Progress notes:

- Math QA orchestration moved into `services/math_qa_orchestrator.py`
- English grading / translation / OCR prompt-building moved into `services/english_tools_service.py`
- Checkin reminders, flow-message rules, and study-plan generation rules moved into `services/checkin_planning_service.py`
- Profile display formatting, recommendation caption assembly, and checkin-plan prompt generation no longer live inline in the checkin page block

## Phase 4: Repository Boundary Extraction

Status: completed

Targets:

- Move profile and plan-related SQLite access out of `app.py`
- Introduce focused repositories for `user_profiles`, `study_plans`, `plan_tasks`, and `checkin_plans`
- Keep current schema and behavior stable while reducing inline SQL in page-facing code

Progress notes:

- Added `repositories/profile_repo.py`
- Added `repositories/study_plan_repo.py`
- Added shared SQLite connection helper in `repositories/sqlite_utils.py`
- `app.py` profile/task/plan wrappers now delegate to repositories instead of owning SQL inline

## Phase 5: Task-Like Batch Workflows

Status: completed (lightweight version)

Targets:

- Introduce lightweight persistent task tracking only where it fits naturally
- Candidate workflow: professional knowledge extraction batches

Reference idea:

- `learn-claude-code` task-system pattern

Non-goal for now:

- Do not introduce multi-agent, worktree isolation, or background agent teams into the user app yet

## Phase 6: Acceptance And Comparison

Status: completed

Progress notes:

- Acceptance runner expanded to include profile and repository tests
- Focused unit-test suite now covers 20 cases across services and repositories
- Latest acceptance artifact: `benchmarks/acceptance_20260620_143734.json`

## Safety Guardrails

- Do not migrate everything from `learn-claude-code`
- Do not rewrite working features just to match a pattern
- Do not rely on subjective impressions of “better”; compare benchmark outputs

## Suggested Verification Per Step

- Run syntax validation
- Run focused manual smoke check for the touched flow
- Run `benchmark_qa.py` and `benchmark_knowledge.py` when behavior-facing logic changes
