# Portable Sync Guide

This project can now be exported as a sanitized handoff package for other developers.

## Standalone Principle

The portable project must not depend on sibling workspace folders such as:

- `cskaoyan-master`
- `408-rag`
- `andrej-karpathy-skills`

These folders may exist in the original author's workspace as historical references, sample sources, or idea libraries, but they are not required for runtime, tests, or continued feature development in this project.

## What To Send

Run:

```bash
python pack_portable.py
```

It produces:

- `dist/kaoyan-assistant-portable/`
- `dist/kaoyan-assistant-portable.zip`

## What The Export Removes

- `.env`
- `data/memory.db`
- `data/user_materials/`
- local logs and temp files
- internal AI-assistant instruction files such as `CLAUDE.md` and `AGENTS.md`
- existing zip build artifacts

It also sanitizes copied text files by replacing:

- real API key patterns like `sk-...`
- absolute Windows paths like `C:\...` and `D:\...`
- non-local public IPv4 addresses

## What The Export Keeps

- source code
- startup scripts
- requirements files
- tests
- docs
- OCR / PDF / knowledge extraction pipeline code
- lightweight sample materials under `data/test_materials/`
- rendering assets under `data/katex/`
- template files under `data/reference/` and `templates/`
- self-contained regression fixtures needed by local tests

## Environment Variables The Receiver Should Set

Copy `.env.example` to `.env`, then fill in values as needed:

```env
AI_API_KEY=sk-your-key-here
AI_API_BASE=https://api.xiaomimimo.com/v1
AI_MODEL=mimo-v2.5
UMI_OCR_URL=http://localhost:1224
MEMORY_DB=data/memory.db
PADDLE_OCR_LANG=ch
```

## Recommended First-Run Commands

Main app:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.port 8505 --server.fileWatcherType none
```

Knowledge-base workbench:

```bash
python -m pip install -r requirements_kb.txt
python -m streamlit run app_kb.py --server.port 8501 --server.fileWatcherType none
```

## Notes For Collaborators

- `app.py` is the broader study assistant entry.
- `knowledge_base.py` and `app_kb.py` are the professional-course knowledge extraction / OCR / repository workflow.
- `services/` contains the core extraction pipeline.
- `tests/` contains regression coverage for OCR cleanup, PDF fallback, long-text chunking, and repository save flow.

## Suggested Collaboration Workflow

1. Import the portable package.
2. Create a fresh local `.env`.
3. Run tests before changing behavior:

```bash
python -m unittest discover -s tests -v
```

4. Keep user data and uploaded PDFs out of source control.
5. If new secrets or local paths are added, keep them in environment variables or local-only config files.
6. If you want to add new test materials, place them under `data/test_materials/` instead of relying on sibling workspace folders.
