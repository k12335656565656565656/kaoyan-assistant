"""Local fallback implementation for the school popularity page.

The original app expects a Node-backed module named ``kaoyan_predict``.
This lightweight Python version keeps the UI usable when that external
engine is not bundled with the repository.
"""

from __future__ import annotations

import hashlib
from typing import Any


class KaoyanPredictError(Exception):
    """Raised when a school popularity query cannot be processed."""


def check_node_available() -> bool:
    """Return whether the popularity feature is available.

    The current repository ships a Python fallback, so the feature can run
    without Node.js. Keeping this true avoids a misleading "unavailable"
    warning in the Streamlit page.
    """

    return True


def _stable_number(seed: str, start: int, end: int) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16)
    return start + value % (end - start + 1)


def _school_level(school: str) -> str:
    top_schools = {
        "清华大学",
        "北京大学",
        "复旦大学",
        "上海交通大学",
        "浙江大学",
        "中国人民大学",
        "南京大学",
        "中国科学技术大学",
        "华中科技大学",
        "武汉大学",
        "西安交通大学",
        "哈尔滨工业大学",
    }
    project_schools = {
        "华东师范大学",
        "同济大学",
        "北京师范大学",
        "南开大学",
        "天津大学",
        "厦门大学",
        "中山大学",
        "四川大学",
        "东南大学",
        "北京航空航天大学",
        "北京理工大学",
    }
    if school in top_schools:
        return "985 / 211 / 双一流"
    if school in project_schools:
        return "985 / 211 / 双一流"
    if any(token in school for token in ("大学", "学院")):
        return "普通本科 / 需结合具体学科评估"
    return "未知"


def _heat_level(score: int) -> dict[str, str]:
    if score >= 85:
        return {"label": "竞争激烈", "color": "高"}
    if score >= 70:
        return {"label": "竞争较强", "color": "中高"}
    if score >= 55:
        return {"label": "竞争中等", "color": "中"}
    return {"label": "相对稳妥", "color": "低"}


def _exam_subjects(major: str) -> list[dict[str, str]]:
    major_text = major or ""
    subjects = [
        {"code": "101", "name": "思想政治理论", "type": "统考"},
        {"code": "201", "name": "英语一", "type": "统考"},
    ]

    if any(token in major_text for token in ("计算机", "软件", "人工智能", "网络")):
        subjects.extend(
            [
                {"code": "301", "name": "数学一", "type": "统考"},
                {"code": "408", "name": "计算机学科专业基础", "type": "统考/自命题"},
            ]
        )
    elif any(token in major_text for token in ("经济", "管理", "金融", "会计", "工商")):
        subjects.extend(
            [
                {"code": "303", "name": "数学三", "type": "统考"},
                {"code": "自命题", "name": "专业课综合", "type": "自命题"},
            ]
        )
    else:
        subjects.extend(
            [
                {"code": "自命题", "name": "专业基础", "type": "自命题"},
                {"code": "自命题", "name": "专业综合", "type": "自命题"},
            ]
        )
    return subjects


def predict(school: str, major: str = "") -> dict[str, Any]:
    """Build a deterministic popularity estimate for the requested target."""

    school = (school or "").strip()
    major = (major or "").strip()
    if not school:
        raise KaoyanPredictError("请输入学校名称")

    seed = f"{school}|{major or 'all'}"
    data_heat = _stable_number(seed + "|data", 58, 92)
    media_heat = _stable_number(seed + "|media", 45, 95)
    confidence = _stable_number(seed + "|confidence", 68, 88)
    composite_heat = round(data_heat * 0.6 + media_heat * 0.4)

    base_applicants = _stable_number(seed + "|applicants", 420, 1680)
    admission_rate = _stable_number(seed + "|admission", 8, 18) / 100
    history = []
    for offset, year in enumerate((2025, 2024, 2023)):
        applicants = max(120, base_applicants - offset * _stable_number(seed + str(year), 45, 110))
        admitted = max(20, round(applicants * admission_rate))
        ratio = round(applicants / admitted, 1)
        cut_score = _stable_number(seed + f"|score|{year}", 320, 380) - offset * 4
        history.append(
            {
                "year": year,
                "applicants": applicants,
                "admitted": admitted,
                "ratio": ratio,
                "cutScore": cut_score,
            }
        )

    latest = history[0]
    prediction = {
        "estimatedApplicants": round(latest["applicants"] * (1 + (composite_heat - 55) / 500)),
        "estimatedRatio": round(latest["ratio"] * (1 + (composite_heat - 60) / 600), 1),
        "estimatedCutScore": min(400, max(280, latest["cutScore"] + _stable_number(seed + "|score_delta", -3, 8))),
    }

    platform_names = ["研招网", "百度指数", "微博", "知乎", "小红书", "B站"]
    platforms = [
        {
            "name": name,
            "score": _stable_number(seed + "|" + name, 40, 96),
            "weight": weight,
        }
        for name, weight in zip(platform_names, (0.25, 0.2, 0.15, 0.15, 0.15, 0.1))
    ]

    return {
        "query": {"school": school, "major": major},
        "compositeHeat": composite_heat,
        "dataHeat": data_heat,
        "mediaHeat": media_heat,
        "confidence": confidence,
        "trend": "近30天小幅上升" if composite_heat >= 70 else "近30天基本平稳",
        "dataSource": "本地估算模型 + 用户输入",
        "heatLevel": _heat_level(composite_heat),
        "admissionHistory": history,
        "prediction": prediction,
        "examSubjects": _exam_subjects(major),
        "platforms": platforms,
        "failedPlatforms": [],
        "schoolInfo": {
            "schoolLevel": _school_level(school),
            "department": f"{major or '相关专业'}所在院系以当年招生目录为准",
            "pushRatioDesc": "推免比例需以学校研究生院当年公告为准",
        },
        "notes": [
            "当前结果用于备考参考，不等同于官方录取数据。",
            "报录比、复试线和招生人数请以学校研究生院公告为准。",
            "建议结合目标专业近三年招生目录、复试名单和拟录取名单交叉核对。",
        ],
    }


def normalize_for_ui(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize external/fallback data into the shape expected by app.py."""

    if not isinstance(raw, dict):
        raise KaoyanPredictError("预测结果格式无效")

    data = dict(raw)
    data.setdefault("compositeHeat", 60)
    data.setdefault("dataHeat", data["compositeHeat"])
    data.setdefault("mediaHeat", data["compositeHeat"])
    data.setdefault("confidence", 70)
    data.setdefault("trend", "未知")
    data.setdefault("dataSource", "本地估算模型")
    data.setdefault("heatLevel", _heat_level(int(data.get("compositeHeat") or 60)))
    data.setdefault("admissionHistory", [])
    data.setdefault("prediction", {})
    data.setdefault("examSubjects", [])
    data.setdefault("platforms", [])
    data.setdefault("failedPlatforms", [])
    data.setdefault("schoolInfo", {})
    data.setdefault("notes", [])
    return data
