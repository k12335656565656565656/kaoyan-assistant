from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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


LOCAL_MATERIAL_SOURCE_PROFILES: tuple[LocalMaterialSourceProfile, ...] = (
    LocalMaterialSourceProfile(
        key="exam_408",
        subject_label="408综合",
        title="本地 408 资料",
        tab_label="本地 408 资料",
        root_env_var="CSKAOYAN_ROOT",
        fallback_dir_name="cskaoyan-master",
    ),
    LocalMaterialSourceProfile(
        key="medical_postgraduate",
        subject_label="医学考研",
        title="本地医学考研资料",
        tab_label="本地医学考研资料",
        root_env_var="MEDICAL_POSTGRADUATE_ROOT",
        fallback_dir_name="Medical Postgraduate Entrance Examination",
    ),
)


def list_local_material_source_profiles() -> list[LocalMaterialSourceProfile]:
    return list(LOCAL_MATERIAL_SOURCE_PROFILES)


def get_local_material_source_profile(source_key: str) -> LocalMaterialSourceProfile | None:
    for profile in LOCAL_MATERIAL_SOURCE_PROFILES:
        if profile.key == source_key:
            return profile
    return None


def get_local_material_source_for_subject(subject_label: str) -> LocalMaterialSourceProfile | None:
    for profile in LOCAL_MATERIAL_SOURCE_PROFILES:
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


def get_local_material_root(source_key: str) -> Path | None:
    profile = get_local_material_source_profile(source_key)
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


def get_local_material_source_hint(source_key: str) -> str:
    profile = get_local_material_source_profile(source_key)
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


def list_local_material_files(source_key: str, limit: int = 300) -> list[dict]:
    root = get_local_material_root(source_key)
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


def read_local_material(source_key: str, relative_path: str) -> tuple[str, bytes]:
    profile = get_local_material_source_profile(source_key)
    root = get_local_material_root(source_key)
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
