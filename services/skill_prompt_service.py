from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SKILLS_DIR = Path("skills")
_CACHE_KEY: tuple[tuple[str, float], ...] | None = None
_CACHE_REGISTRY: dict[str, "SkillDefinition"] = {}


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    label: str
    description: str
    body: str
    path: str
    trigger_keywords: tuple[str, ...] = ()
    version: str = ""


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是"}


def _build_cache_key(skills_dir: Path) -> tuple[tuple[str, float], ...]:
    if not skills_dir.exists():
        return ()
    snapshot = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
            continue
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            snapshot.append((str(skill_file.resolve()), skill_file.stat().st_mtime))
    return tuple(snapshot)


def parse_skill_frontmatter(content: str) -> tuple[dict, str]:
    """Parse simple YAML-like frontmatter from SKILL.md."""
    lines = content.strip().split("\n")
    meta = {}
    body_start = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines):
            line = lines[i]
            if line.strip() == "---":
                body_start = i + 1
                break
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if val.startswith("[") and val.endswith("]"):
                    val = tuple(
                        item.strip().strip('"').strip("'")
                        for item in val[1:-1].split(",")
                        if item.strip()
                    )
                meta[key] = val
            i += 1
    body = "\n".join(lines[body_start:]).strip() if body_start > 0 else content.strip()
    return meta, body


def load_all_skills(skills_dir: Path | None = None, *, refresh: bool = False) -> dict[str, dict]:
    """Scan skills/ once and keep a lightweight registry cache."""
    global _CACHE_KEY, _CACHE_REGISTRY

    skills_dir = skills_dir or SKILLS_DIR
    cache_key = _build_cache_key(skills_dir)
    if not refresh and cache_key == _CACHE_KEY and _CACHE_REGISTRY:
        return {
            name: {
                "name": skill.name,
                "label": skill.label,
                "description": skill.description,
                "_body": skill.body,
                "_dir": skill.path,
                "trigger_keywords": list(skill.trigger_keywords),
                "version": skill.version,
            }
            for name, skill in _CACHE_REGISTRY.items()
        }

    registry: dict[str, SkillDefinition] = {}
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            try:
                content = skill_file.read_text(encoding="utf-8")
                meta, body = parse_skill_frontmatter(content)
            except OSError:
                continue
            if _coerce_bool(meta.get("hidden")):
                continue

            name = str(meta.get("name") or skill_dir.name)
            registry[name] = SkillDefinition(
                name=name,
                label=str(meta.get("label") or name),
                description=str(meta.get("description") or name),
                body=body.strip(),
                path=str(skill_dir),
                trigger_keywords=tuple(meta.get("trigger_keywords") or ()),
                version=str(meta.get("version") or ""),
            )

    _CACHE_KEY = cache_key
    _CACHE_REGISTRY = registry
    return load_all_skills(skills_dir, refresh=False)


def get_skill_catalog(skills_dir: Path | None = None) -> list[SkillDefinition]:
    load_all_skills(skills_dir)
    return list(_CACHE_REGISTRY.values())


def get_skill_prompt(name: str, skills_dir: Path | None = None) -> str:
    load_all_skills(skills_dir)
    skill = _CACHE_REGISTRY.get(name)
    return skill.body if skill else ""


def build_system_prompt_with_skills(active_skills: list[str], skills_dir: Path | None = None) -> str:
    """Compose active skill bodies into a system prompt fragment."""
    fragments = []
    for name in active_skills:
        body = get_skill_prompt(name, skills_dir)
        if body:
            definition = _CACHE_REGISTRY.get(name)
            heading = definition.description if definition else name
            fragments.append(f"## Skill: {heading}\n\n{body}")
    return "\n\n---\n\n".join(fragments) if fragments else ""
