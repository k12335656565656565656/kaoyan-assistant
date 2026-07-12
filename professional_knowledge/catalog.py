"""Configuration-backed subject catalog for the professional knowledge workspace.

The bundled JSON file is the single source of truth for both catalog cards and
local material sources.  An optional user file can add subjects or override a
bundled subject by ``key`` without changing application code.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUBJECTS_CONFIG_PATH = Path(__file__).with_name("default_subjects.json")
CUSTOM_SUBJECTS_CONFIG_PATH = PROJECT_ROOT / "data" / "config" / "custom_subjects.json"
CONFIG_VERSION = 1

_CATALOG_FIELDS = (
    "title",
    "subject_label",
    "status",
    "stage",
    "summary",
    "capabilities",
    "source_strategy",
    "notes",
    "enabled",
)


@dataclass(frozen=True)
class RagKnowledgeBaseProfile:
    key: str
    title: str
    subject_label: str
    status: str
    stage: str
    summary: str
    capabilities: list[str] = field(default_factory=list)
    source_strategy: str = ""
    notes: str = ""
    enabled: bool = False
    max_points: int = 12
    extraction_guidance: str = ""


def _read_config(path: Path, *, tolerate_errors: bool) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            subjects = payload
        elif isinstance(payload, dict):
            subjects = payload.get("subjects")
        else:
            raise ValueError("配置根节点必须是对象或数组。")
        if not isinstance(subjects, list):
            raise ValueError("配置中的 subjects 必须是数组。")
        return [item for item in subjects if isinstance(item, dict)]
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        if tolerate_errors:
            return []
        raise RuntimeError(f"默认学科配置不可读取：{path}")


def _as_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串。")
    return value.strip()


def _optional_string(value: Any, field_name: str, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{field_name} 必须是字符串。")
    return value.strip()


def _canonicalize_profile_shape(raw_profile: Mapping[str, Any]) -> dict[str, Any]:
    """Accept the documented nested shape plus convenient flat catalog fields."""

    profile = copy.deepcopy(dict(raw_profile))
    catalog = profile.get("catalog")
    if catalog is None:
        catalog = {}
    if not isinstance(catalog, dict):
        raise ValueError("catalog 必须是对象。")
    for field_name in _CATALOG_FIELDS:
        if field_name in profile and field_name not in catalog:
            catalog[field_name] = profile.pop(field_name)
    profile["catalog"] = catalog
    return profile


def _profile_key(raw_profile: Mapping[str, Any]) -> str | None:
    key = raw_profile.get("key")
    if isinstance(key, str) and key.strip():
        return key.strip()
    catalog = raw_profile.get("catalog")
    if isinstance(catalog, dict):
        nested_key = catalog.get("key")
        if isinstance(nested_key, str) and nested_key.strip():
            return nested_key.strip()
    return None


def _merge_profile(base: Mapping[str, Any] | None, override: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base or {}))
    override_copy = _canonicalize_profile_shape(override)
    for key, value in override_copy.items():
        if key == "catalog" and isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(copy.deepcopy(value))
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _normalize_subject_profile(raw_profile: Mapping[str, Any]) -> dict[str, Any]:
    profile = _canonicalize_profile_shape(raw_profile)
    key = _profile_key(profile)
    if key is None:
        raise ValueError("学科配置缺少 key。")

    catalog_raw = profile.get("catalog")
    if not isinstance(catalog_raw, dict):
        raise ValueError("catalog 必须是对象。")

    capabilities_raw = catalog_raw.get("capabilities", [])
    if not isinstance(capabilities_raw, list) or not all(
        isinstance(item, str) for item in capabilities_raw
    ):
        raise ValueError("catalog.capabilities 必须是字符串数组。")
    enabled = catalog_raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("catalog.enabled 必须是布尔值。")

    max_points = profile.get("max_points", 12)
    if isinstance(max_points, bool) or not isinstance(max_points, int) or not 1 <= max_points <= 100:
        raise ValueError("max_points 必须是 1 到 100 之间的整数。")

    local_source_raw = profile.get("local_source")
    local_source: dict[str, Any] | None = None
    if local_source_raw is not None:
        if not isinstance(local_source_raw, dict):
            raise ValueError("local_source 必须是对象或 null。")
        fallback_dir_name = local_source_raw.get("fallback_dir_name")
        if fallback_dir_name is not None:
            fallback_dir_name = _optional_string(
                fallback_dir_name, "local_source.fallback_dir_name"
            ) or None
        local_source = {
            "key": _as_non_empty_string(local_source_raw.get("key"), "local_source.key"),
            "title": _as_non_empty_string(local_source_raw.get("title"), "local_source.title"),
            "tab_label": _as_non_empty_string(
                local_source_raw.get("tab_label"), "local_source.tab_label"
            ),
            "root_env_var": _as_non_empty_string(
                local_source_raw.get("root_env_var"), "local_source.root_env_var"
            ),
            "fallback_dir_name": fallback_dir_name,
        }

    catalog = {
        "title": _as_non_empty_string(catalog_raw.get("title"), "catalog.title"),
        "subject_label": _as_non_empty_string(
            catalog_raw.get("subject_label"), "catalog.subject_label"
        ),
        "status": _optional_string(catalog_raw.get("status"), "catalog.status"),
        "stage": _optional_string(catalog_raw.get("stage"), "catalog.stage"),
        "summary": _optional_string(catalog_raw.get("summary"), "catalog.summary"),
        "capabilities": [item.strip() for item in capabilities_raw if item.strip()],
        "source_strategy": _optional_string(
            catalog_raw.get("source_strategy"), "catalog.source_strategy"
        ),
        "notes": _optional_string(catalog_raw.get("notes"), "catalog.notes"),
        "enabled": enabled,
    }
    return {
        "key": key,
        "catalog": catalog,
        "local_source": local_source,
        "max_points": max_points,
        "extraction_guidance": _optional_string(
            profile.get("extraction_guidance"), "extraction_guidance"
        ),
    }


def list_default_subject_profiles() -> list[dict[str, Any]]:
    raw_profiles = _read_config(DEFAULT_SUBJECTS_CONFIG_PATH, tolerate_errors=False)
    return [_normalize_subject_profile(profile) for profile in raw_profiles]


def list_subject_profiles(
    custom_config_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return bundled profiles merged with valid custom profiles by subject key.

    A missing, malformed, or invalid custom file never prevents the bundled
    subjects from loading. Invalid entries are ignored independently.
    """

    profiles = list_default_subject_profiles()
    positions = {profile["key"]: index for index, profile in enumerate(profiles)}
    custom_path = Path(custom_config_path) if custom_config_path is not None else CUSTOM_SUBJECTS_CONFIG_PATH

    for raw_profile in _read_config(custom_path, tolerate_errors=True):
        key = _profile_key(raw_profile)
        if key is None:
            continue
        base = profiles[positions[key]] if key in positions else None
        try:
            normalized = _normalize_subject_profile(_merge_profile(base, raw_profile))
        except (TypeError, ValueError):
            continue
        if key in positions:
            profiles[positions[key]] = normalized
        else:
            positions[key] = len(profiles)
            profiles.append(normalized)
    return copy.deepcopy(profiles)


def get_subject_profile(
    subject_key: str, custom_config_path: str | Path | None = None
) -> dict[str, Any] | None:
    normalized_key = (subject_key or "").strip()
    for profile in list_subject_profiles(custom_config_path=custom_config_path):
        if profile["key"] == normalized_key:
            return profile
    return None


def _to_rag_profile(profile: Mapping[str, Any]) -> RagKnowledgeBaseProfile:
    catalog = profile["catalog"]
    return RagKnowledgeBaseProfile(
        key=profile["key"],
        title=catalog["title"],
        subject_label=catalog["subject_label"],
        status=catalog["status"],
        stage=catalog["stage"],
        summary=catalog["summary"],
        capabilities=list(catalog["capabilities"]),
        source_strategy=catalog["source_strategy"],
        notes=catalog["notes"],
        enabled=catalog["enabled"],
        max_points=profile["max_points"],
        extraction_guidance=profile["extraction_guidance"],
    )


# Retained for callers that imported the old module-level constant. Runtime
# list/get APIs below include custom configuration and should be preferred.
RAG_KNOWLEDGE_BASES: list[RagKnowledgeBaseProfile] = [
    _to_rag_profile(profile) for profile in list_default_subject_profiles()
]


def list_rag_knowledge_bases(
    custom_config_path: str | Path | None = None,
) -> list[RagKnowledgeBaseProfile]:
    return [
        _to_rag_profile(profile)
        for profile in list_subject_profiles(custom_config_path=custom_config_path)
    ]


def get_rag_knowledge_base_by_subject(
    subject_label: str, custom_config_path: str | Path | None = None
) -> RagKnowledgeBaseProfile | None:
    normalized_label = (subject_label or "").strip()
    for profile in list_rag_knowledge_bases(custom_config_path=custom_config_path):
        if profile.subject_label == normalized_label:
            return profile
    return None


def list_enabled_subjects(custom_config_path: str | Path | None = None) -> list[str]:
    subjects = [
        item.subject_label
        for item in list_rag_knowledge_bases(custom_config_path=custom_config_path)
        if item.enabled
    ]
    subjects.append("其他")
    return list(dict.fromkeys(subjects))


def save_custom_subject_profile(
    profile: Mapping[str, Any], custom_config_path: str | Path | None = None
) -> dict[str, Any]:
    """Validate and atomically upsert one custom subject profile.

    Partial overrides are accepted for bundled or already-saved subjects. New
    subjects must provide the required catalog fields. The returned dictionary
    is the complete normalized profile that was persisted.
    """

    if not isinstance(profile, Mapping):
        raise ValueError("profile 必须是对象。")
    key = _profile_key(profile)
    if key is None:
        raise ValueError("学科配置缺少 key。")

    path = Path(custom_config_path) if custom_config_path is not None else CUSTOM_SUBJECTS_CONFIG_PATH
    defaults = {item["key"]: item for item in list_default_subject_profiles()}
    saved_raw = _read_config(path, tolerate_errors=True)
    saved: list[dict[str, Any]] = []
    saved_by_key: dict[str, dict[str, Any]] = {}
    for raw_item in saved_raw:
        saved_key = _profile_key(raw_item)
        if saved_key is None:
            continue
        base = saved_by_key.get(saved_key) or defaults.get(saved_key)
        try:
            normalized_item = _normalize_subject_profile(_merge_profile(base, raw_item))
        except (TypeError, ValueError):
            continue
        if saved_key in saved_by_key:
            for index, existing in enumerate(saved):
                if existing["key"] == saved_key:
                    saved[index] = normalized_item
                    break
        else:
            saved.append(normalized_item)
        saved_by_key[saved_key] = normalized_item

    base = saved_by_key.get(key) or defaults.get(key)
    normalized = _normalize_subject_profile(_merge_profile(base, profile))
    replaced = False
    for index, existing in enumerate(saved):
        if existing["key"] == key:
            saved[index] = normalized
            replaced = True
            break
    if not replaced:
        saved.append(normalized)

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(
                {"version": CONFIG_VERSION, "subjects": saved},
                temporary_file,
                ensure_ascii=False,
                indent=2,
            )
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return copy.deepcopy(normalized)
