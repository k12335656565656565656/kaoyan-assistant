"""Build a sanitized, portable handoff package for other developers."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
EXPORT_DIR = DIST_DIR / "kaoyan-assistant-portable"
ZIP_PATH = DIST_DIR / "kaoyan-assistant-portable.zip"

EXCLUDED_NAMES = {
    ".git",
    ".env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".streamlit",
    "temp",
    "dist",
    "node_modules",
}

EXCLUDED_FILES = {
    "CLAUDE.md",
    "AGENTS.md",
    "custom_subjects.json",
    "streamlit-kb-test.out.log",
    "streamlit-kb-test.err.log",
}

EXCLUDED_PREFIXES = (
    "data/user_materials/",
    "agent-skills/",
    "skills/",
)

TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".css",
    ".html",
    ".js",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".bat",
    ".example",
}


def should_exclude(path: Path) -> bool:
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    parts = path.relative_to(PROJECT_ROOT).parts
    normalized_dir_rel = f"{rel}/" if path.is_dir() and not rel.endswith("/") else rel
    if any(part in EXCLUDED_NAMES for part in parts):
        return True
    if path.name in EXCLUDED_FILES:
        return True
    if any(rel.startswith(prefix) or normalized_dir_rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return True
    if path.name == "memory.db" and rel == "data/memory.db":
        return True
    if path.suffix.lower() == ".log":
        return True
    if path.suffix.lower() == ".zip":
        return True
    return False


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name in {".gitignore", ".env.example"}


def sanitize_text(text: str) -> str:
    text = re.sub(r"sk-[A-Za-z0-9]+", "sk-your-key-here", text)
    text = re.sub(
        r"(?i)(?:[A-Z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)*[^\\/:*?\"<>|\r\n]*)",
        "[LOCAL_WINDOWS_PATH]",
        text,
    )

    def replace_ip(match: re.Match[str]) -> str:
        value = match.group(0)
        if value.startswith(("127.", "10.", "0.0.0.0")) or value == "localhost":
            return value
        return "x.x.x.x"

    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", replace_ip, text)
    return text


def copy_project() -> list[str]:
    copied = []
    for path in PROJECT_ROOT.rglob("*"):
        if should_exclude(path):
            continue
        rel = path.relative_to(PROJECT_ROOT)
        target = EXPORT_DIR / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if is_text_file(path):
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                shutil.copy2(path, target)
            else:
                target.write_text(sanitize_text(content), encoding="utf-8")
        else:
            shutil.copy2(path, target)
        copied.append(rel.as_posix())
    return copied


def write_manifest(copied_files: list[str]) -> None:
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_name": PROJECT_ROOT.name,
        "portable_package": EXPORT_DIR.name,
        "excluded": {
            "names": sorted(EXCLUDED_NAMES),
            "files": sorted(EXCLUDED_FILES),
            "prefixes": list(EXCLUDED_PREFIXES),
            "notes": [
                "Removed .env, SQLite runtime DB, user uploads, logs, internal AI-assistant instructions, and build outputs.",
                "Sanitized API key patterns, absolute Windows paths, and non-local IPv4 addresses inside copied text files.",
            ],
        },
        "startup": {
            "main_app": "python -m streamlit run app.py --server.port 8505 --server.fileWatcherType none",
            "knowledge_base": "python -m streamlit run app_kb.py --server.port 8501 --server.fileWatcherType none",
        },
        "copied_file_count": len(copied_files),
    }
    (EXPORT_DIR / "portable_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_zip() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with ZipFile(ZIP_PATH, "w", compression=ZIP_DEFLATED) as zf:
        for path in EXPORT_DIR.rglob("*"):
            zf.write(path, path.relative_to(EXPORT_DIR.parent))


def main() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if EXPORT_DIR.exists():
        shutil.rmtree(EXPORT_DIR)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    copied_files = copy_project()
    write_manifest(copied_files)
    build_zip()

    print(f"Portable package ready: {EXPORT_DIR}")
    print(f"Portable zip ready: {ZIP_PATH}")


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    main()
