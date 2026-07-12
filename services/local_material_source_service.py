from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from professional_knowledge.catalog import list_default_subject_profiles, list_subject_profiles


SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".png", ".jpg", ".jpeg"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class LocalMaterialSourceProfile:
    key: str
    subject_label: str
    title: str
    tab_label: str
    root_env_var: str
    fallback_dir_name: str | None = None


def _build_local_material_source_profiles(
    subject_profiles: list[dict],
) -> list[LocalMaterialSourceProfile]:
    profiles: list[LocalMaterialSourceProfile] = []
    for subject_profile in subject_profiles:
        local_source = subject_profile.get("local_source")
        catalog = subject_profile.get("catalog")
        if not isinstance(local_source, dict) or not isinstance(catalog, dict):
            continue
        profiles.append(
            LocalMaterialSourceProfile(
                key=local_source["key"],
                subject_label=catalog["subject_label"],
                title=local_source["title"],
                tab_label=local_source["tab_label"],
                root_env_var=local_source["root_env_var"],
                fallback_dir_name=local_source.get("fallback_dir_name"),
            )
        )
    return profiles


# Retained for callers that imported the old constant. Runtime list/get APIs
# below also include valid custom subject configuration.
LOCAL_MATERIAL_SOURCE_PROFILES: tuple[LocalMaterialSourceProfile, ...] = tuple(
    _build_local_material_source_profiles(list_default_subject_profiles())
)


def list_local_material_source_profiles(
    custom_config_path: str | Path | None = None,
) -> list[LocalMaterialSourceProfile]:
    return _build_local_material_source_profiles(
        list_subject_profiles(custom_config_path=custom_config_path)
    )


def get_local_material_source_profile(
    source_key: str, custom_config_path: str | Path | None = None
) -> LocalMaterialSourceProfile | None:
    for profile in list_local_material_source_profiles(custom_config_path=custom_config_path):
        if profile.key == source_key:
            return profile
    return None


def get_local_material_source_for_subject(
    subject_label: str, custom_config_path: str | Path | None = None
) -> LocalMaterialSourceProfile | None:
    for profile in list_local_material_source_profiles(custom_config_path=custom_config_path):
        if profile.subject_label == (subject_label or "").strip():
            return profile
    return None


def _resolve_candidate_root(raw: str) -> Path | None:
    if not raw:
        return None
    root = Path(raw).expanduser()
    if not root.exists() or not root.is_dir():
        return None
    return root.resolve()


def get_local_material_root(
    source_key: str, custom_config_path: str | Path | None = None
) -> Path | None:
    profile = get_local_material_source_profile(
        source_key, custom_config_path=custom_config_path
    )
    if profile is None:
        return None

    configured_root = _resolve_candidate_root((os.environ.get(profile.root_env_var) or "").strip())
    if configured_root is not None:
        return configured_root

    if profile.fallback_dir_name:
        fallback_root = _resolve_candidate_root(str(PROJECT_ROOT / profile.fallback_dir_name))
        if fallback_root is not None:
            return fallback_root
    return None


def get_local_material_source_hint(
    source_key: str, custom_config_path: str | Path | None = None
) -> str:
    profile = get_local_material_source_profile(
        source_key, custom_config_path=custom_config_path
    )
    if profile is None:
        return ""

    hints = [f"环境变量 `{profile.root_env_var}`"]
    if profile.fallback_dir_name:
        hints.append(f"仓库目录 `{PROJECT_ROOT / profile.fallback_dir_name}`")
    return " 或 ".join(hints)


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def list_local_material_files(
    source_key: str,
    limit: int = 300,
    custom_config_path: str | Path | None = None,
) -> list[dict]:
    root = get_local_material_root(source_key, custom_config_path=custom_config_path)
    if root is None:
        return []

    items: list[dict] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        try:
            resolved = path.resolve()
            if not _is_inside(resolved, root):
                continue
            rel = resolved.relative_to(root)
            stat = resolved.stat()
        except Exception:
            continue
        items.append(
            {
                "name": path.name,
                "relative_path": str(rel).replace("\\", "/"),
                "suffix": path.suffix.lower(),
                "size_bytes": stat.st_size,
            }
        )

    items.sort(key=lambda item: item["relative_path"].lower())
    return items[:limit]


def read_local_material(
    source_key: str,
    relative_path: str,
    custom_config_path: str | Path | None = None,
) -> tuple[str, bytes]:
    profile = get_local_material_source_profile(
        source_key, custom_config_path=custom_config_path
    )
    root = get_local_material_root(source_key, custom_config_path=custom_config_path)
    if profile is None or root is None:
        raise RuntimeError("本地资料目录未配置或不可用。")

    normalized = (relative_path or "").replace("\\", "/").strip().lstrip("/")
    target = (root / normalized).resolve()
    if not _is_inside(target, root):
        raise RuntimeError("非法路径：只能读取资料根目录内部文件。")
    if not target.is_file():
        raise RuntimeError("目标资料不存在。")
    if target.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise RuntimeError(f"不支持的文件类型：{target.suffix}")

    return target.name, target.read_bytes()


def get_cskaoyan_root() -> Path | None:
    return get_local_material_root("exam_408")


def list_cskaoyan_material_files(limit: int = 300) -> list[dict]:
    return list_local_material_files("exam_408", limit=limit)


def read_cskaoyan_material(relative_path: str) -> tuple[str, bytes]:
    return read_local_material("exam_408", relative_path)
