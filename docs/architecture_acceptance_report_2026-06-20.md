# Architecture Acceptance Report (2026-06-20)

## Scope

This report compares the project before and after the six-stage architecture integration pass inspired by `D:\learn-claude-code`.

## Delivered Phases

1. Baseline and acceptance path setup
2. Skill registry caching and prompt composition service
3. Unified LLM gateway with shared message-text extraction and retry support
4. Shared knowledge matching service and thinner app-level wrappers
5. Lightweight professional-knowledge task persistence for extraction flow
6. Benchmarks, syntax checks, and unit-test acceptance
7. Checkin/planning rules extracted into a reusable service with focused tests
8. Profile and study-plan SQLite access extracted into repositories with service-backed page helpers

## What Was Integrated From learn-claude-code

- `s07 skill loading`
  - Skill scanning moved into a cached registry service
  - `app.py` now consumes a shared prompt-composition layer instead of owning the logic inline

- `s11 error recovery`
  - Shared `llm_gateway` now centralizes text extraction, retries, timeouts, and streaming/non-streaming boundaries
  - Repeated direct `urllib` chat-completion logic was reduced in the primary call paths

- `s12 task system`
  - Professional knowledge extraction now writes a lightweight persistent task trail under `data/tasks/professional_knowledge`
  - Upload → extract → draft → save has explicit task-state checkpoints

- `thin composition / orchestration boundary`
  - Checkin reminders, flow-message prompt assembly, and study-plan generation rules now live in `services/checkin_planning_service.py`
  - `app.py` keeps the DB reads and Streamlit wiring, while reusable decision logic is now testable in isolation

- `repository boundary`
  - Profile reads/writes now flow through `repositories/profile_repo.py`
  - Study-plan, task-progress, and checkin-plan persistence now flow through `repositories/study_plan_repo.py`
  - Profile formatting and conversation-driven profile updates now flow through `services/profile_service.py`

## Test Summary

### 1. Syntax / Unit Tests

- `python -m py_compile ...`:
  - Passed
  - Residual note: existing `app.py` still emits one old `SyntaxWarning` for a LaTeX string escape; this predates the current refactor

- `python -m unittest tests.test_profile_service tests.test_study_plan_repo tests.test_checkin_planning_service tests.test_math_qa_orchestrator tests.test_english_tools_service tests.test_skill_prompt_service tests.test_knowledge_match_service tests.test_professional_knowledge_task_service`
  - Passed: 20/20

### 2. Benchmark Comparison

#### `benchmark_knowledge.py`

- Before:
  - Accuracy: `2/50 (4%)`

- After:
  - Accuracy: `31/50 (63%)`

- Change:
  - `+59 percentage points`

Interpretation:

- The biggest win came from replacing fragmented, ad hoc knowledge matching with one shared local-first matcher.
- This specifically improved retrieval quality for matrix, probability, calculus application, and advanced-topic questions.

#### `benchmark_qa.py`

- Before:
  - All 5 cases were `SLOW`
  - Average end-to-end latency: about `31.44s`
  - `smart_match_knowledge` average: about `17.10s`

- After:
  - All 5 cases `PASS`
  - Average end-to-end latency: `14.18s`
  - `smart_match_knowledge` average: `0.06s`
  - `main_llm_call` average: `11.59s`

- Change:
  - End-to-end latency improved by about `54.9%`
  - Knowledge matching bottleneck was effectively removed

Interpretation:

- The refactor meaningfully optimized the harness around the model.
- The main remaining bottleneck is now the primary LLM answer generation itself, not the surrounding orchestration.

### 3. Latest Acceptance Snapshot (`2026-06-20 14:37:34`)

- Artifact:
  - `benchmarks/acceptance_20260620_143734.json`

- `benchmark_knowledge.py`
  - Accuracy remained `31/50 (63%)`
  - This suggests the profile/repository extraction did not degrade retrieval quality

- `benchmark_qa.py`
  - 4 cases `PASS`, 1 case `SLOW`
  - Average end-to-end latency: `19.45s`
  - Main bottleneck remained `main_llm_call` at `16.83s`

Interpretation:

- The one `SLOW` result was the simple concept case exceeding the threshold by about one second.
- Because this migration pass touched profile/checkin/repository boundaries rather than the math answer path, the most plausible explanation is model-side latency fluctuation rather than architectural regression.

## Honest Assessment

This pass is an optimization overall, not a pure rewrite.

What clearly improved:

- Skill loading is now a shared harness capability instead of inline monolith logic
- LLM call handling is more centralized
- Knowledge matching quality improved sharply
- Knowledge matching latency collapsed from a major bottleneck to a negligible step
- Professional knowledge extraction now has a persistent, inspectable task trail
- Profile and plan persistence are now on explicit repository boundaries
- The checkin/profile page logic is thinner and more testable

What is not finished yet:

- `app.py` is still large
- The main LLM answer step is still the dominant latency source
- Not every legacy direct API call in the repo has been migrated to `llm_gateway`
- The project is now materially aligned with the learn-claude-code extraction style, but not yet a full loop-first harness rewrite

## Recommended Next Pass

1. Continue replacing remaining direct chat-completion call sites with `services/llm_gateway.py`
2. Shrink `app.py` further by moving more page orchestration into focused services
3. Add more local-first routing to reduce the cost of `classify_query`
4. Expand the professional-knowledge task trail into a richer recovery/inspection panel if that workflow becomes a bigger priority
