"""
Python bridge for kaoyan-skill-v2.5 prediction engine.
Calls Node.js exam-forecast-real.mjs as a subprocess.
"""
import subprocess
import json
import os
from pathlib import Path
from dotenv import load_dotenv

PREDICT_DIR = Path(__file__).parent / "kaoyan_predict"
SCRIPT = PREDICT_DIR / "exam-forecast-real.mjs"
load_dotenv(Path(__file__).with_name(".env"))


class KaoyanPredictError(Exception):
    pass


def _node_binary():
    return os.environ.get("NODE_BINARY", "").strip() or "node"


def check_node_available():
    try:
        subprocess.run(
            [_node_binary(), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return True
    except Exception:
        return False


def predict(school, major="", session="27届", timeout=90, match_mode="fuzzy", degree_type="", major_code="", include_media=True, media_timeout_ms=12000):
    if not SCRIPT.exists():
        raise KaoyanPredictError("预测引擎文件缺失")
    if not school.strip():
        raise KaoyanPredictError("请输入学校名称")

    match_mode = "exact" if match_mode == "exact" else "fuzzy"
    degree_type = (degree_type or "").strip()
    major_code = (major_code or "").strip()

    args = [
        _node_binary(),
        str(SCRIPT),
        "-s", school.strip(),
        "-e", session,
        "--match-mode", match_mode,
        "-j",
    ]
    if major and major.strip():
        args.extend(["-m", major.strip()])
    elif not major_code:
        args.extend(["-m", school.strip()])
    if major_code:
        args.extend(["--major-code", major_code])
    if degree_type:
        args.extend(["--degree-type", degree_type])
    if not include_media:
        args.append("--no-media")
    else:
        args.extend(["--media-timeout-ms", str(media_timeout_ms)])

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(PREDICT_DIR),
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError:
        raise KaoyanPredictError("未检测到 Node.js，请先安装 Node.js 或在 .env 配置 NODE_BINARY")
    except subprocess.TimeoutExpired:
        raise KaoyanPredictError(f"查询超时（>{timeout}秒），请稍后重试")

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise KaoyanPredictError(f"预测引擎错误{': ' + stderr if stderr else ''}")

    stdout = (result.stdout or "").strip()
    if not stdout:
        raise KaoyanPredictError("预测引擎返回为空")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise KaoyanPredictError(f"解析预测结果失败: {e}")

    if not isinstance(data, dict) or "compositeHeat" not in data:
        raise KaoyanPredictError("预测数据格式异常")

    return data


def normalize_for_ui(data):
    """返回一个经过校验和补默认值的展示用 dict"""
    d = dict(data)

    d.setdefault("compositeHeat", 0)
    d.setdefault("dataHeat", 0)
    d.setdefault("mediaHeat", 0)
    d.setdefault("heatLevel", {"label": "未知", "color": "⬜", "min": 0})
    d.setdefault("dataSource", "未知")
    d.setdefault("confidence", 0)
    d.setdefault("trend", "稳定")

    p = d.setdefault("prediction", {})
    p.setdefault("estimatedApplicants", 0)
    p.setdefault("estimatedRatio", 0)
    p.setdefault("estimatedCutScore", 0)
    d["prediction"] = p

    d.setdefault("admissionHistory", [])
    d.setdefault("examSubjects", [])
    d.setdefault("notes", [])
    d.setdefault("platforms", [])
    d.setdefault("failedPlatforms", [])
    d.setdefault("programOptions", [])
    d.setdefault("hasAuthoritativeAdmissionHistory", False)
    d.setdefault("canPredict", False)
    d.setdefault("dataQuality", "unknown")
    d.setdefault("fieldSources", {})
    d.setdefault("admissionEvidence", [])
    d.setdefault("admissionEvidenceSummary", {})
    d.setdefault("predictionBasis", "none")

    si = d.setdefault("schoolInfo", {})
    si.setdefault("schoolLevel", "未知")
    si.setdefault("department", "未知")
    si.setdefault("pushRatioDesc", "")
    si.setdefault("plannedEnrollment", None)
    si.setdefault("plannedEnrollmentText", "")
    si.setdefault("sourceAuthority", "")
    si.setdefault("sourceUrl", "")
    si.setdefault("schoolLevelSource", "")
    si.setdefault("schoolLevelConfidence", "")
    si.setdefault("schoolLevelTags", [])
    si.setdefault("officialChannels", [])
    si.setdefault("admissionDataChannels", [])
    d["schoolInfo"] = si

    match_info = d.setdefault("matchInfo", {})
    match_info.setdefault("mode", "fuzzy")
    match_info.setdefault("requested", {})
    match_info.setdefault("matched", None)
    match_info.setdefault("isExact", False)
    d["matchInfo"] = match_info

    memory = d.setdefault("memory", {})
    memory.setdefault("summary", "")
    memory.setdefault("similarQueries", [])
    memory.setdefault("userProfile", {})
    d["memory"] = memory

    return d
