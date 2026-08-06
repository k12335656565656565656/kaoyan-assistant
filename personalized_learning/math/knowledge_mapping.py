"""Small, explainable knowledge-point mapper for imported exam questions."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping


_CJK_RUN = re.compile(r"[\u3400-\u9fff]{2,}")
_SEPARATOR = re.compile(r"[与和及、/（）()：:，,；;\s]+")
_STOP_TERMS = {
    "定义", "性质", "概念", "计算", "方法", "应用", "基础", "综合", "常见", "函数", "矩阵",
    "随机", "变量", "公式", "定理", "方程", "分布", "条件", "问题", "考研数学", "详解",
}

_MATH_ALIASES = {
    "001-数列极限的定义与性质.md": ("数列", "x_n", "数列收敛"),
    "002-函数极限的概念与计算.md": ("极限", "\\lim", "lim", "等价无穷小", "无穷小"),
    "003-函数的连续性与间断点.md": ("连续性", "连续函数", "间断点"),
    "004-导数的定义与几何意义.md": ("导数定义", "导数的几何意义", "切线"),
    "005-导数的计算法则.md": ("求导", "导数计算", "导函数"),
    "006-微分中值定理.md": ("中值定理", "拉格朗日", "罗尔定理", "柯西中值"),
    "007-洛必达法则.md": ("洛必达", "l'hopital"),
    "008-函数的单调性与极值.md": ("单调性", "单调递增", "单调递减", "极值", "最值"),
    "009-函数的凹凸性与拐点.md": ("凹凸性", "拐点"),
    "011-不定积分的计算方法.md": ("原函数", "不定积分", "换元积分", "分部积分"),
    "012-定积分的定义与性质.md": ("定积分", "积分上限", "广义积分"),
    "013-泰勒公式.md": ("泰勒", "麦克劳林", "高阶无穷小"),
    "016-一阶微分方程.md": ("微分方程", "初值问题", "一阶线性"),
    "020-向量与空间解析几何.md": ("空间解析几何", "方向向量", "法向量"),
    "021-行列式的定义与性质.md": ("行列式", "det"),
    "026-矩阵的秩.md": ("矩阵的秩", "秩", "rank"),
    "027-向量的概念与运算.md": ("向量", "向量组"),
    "030-线性方程组.md": ("线性方程组", "齐次方程组", "非齐次方程组"),
    "031-特征值与特征向量.md": ("特征值", "特征向量"),
    "033-相似矩阵.md": ("相似矩阵", "相似变换"),
    "034-矩阵的对角化.md": ("对角化", "可对角化"),
    "036-二次型及其标准形.md": ("二次型", "惯性指数", "标准形"),
    "037-二次型的正定性.md": ("正定", "正惯性", "负定"),
    "041-随机事件与概率.md": ("随机事件", "事件概率"),
    "042-条件概率与乘法公式.md": ("条件概率", "乘法公式"),
    "043-事件的独立性.md": ("事件独立", "相互独立"),
    "045-随机变量及其分布.md": ("随机变量", "分布函数"),
    "048-随机变量函数的分布.md": ("随机变量函数", "函数的分布"),
    "049-二维随机变量.md": ("二维随机变量", "联合分布"),
    "052-随机变量的数字特征.md": ("数学期望", "方差", "协方差", "相关系数"),
    "056-大数定律与中心极限定理.md": ("大数定律", "中心极限定理"),
    "058-三大统计分布.md": ("卡方分布", "t分布", "F分布"),
    "059-参数估计.md": ("参数估计", "点估计", "最大似然"),
    "061-区间估计与假设检验.md": ("区间估计", "假设检验", "拒绝域"),
    "064-多元函数微分学.md": ("偏导数", "全微分", "隐函数", "多元函数"),
    "065-二重积分与三重积分.md": ("二重积分", "三重积分"),
    "067-无穷级数.md": ("无穷级数", "级数收敛", "收敛性"),
    "068-曲线积分与曲面积分.md": ("曲线积分", "曲面积分"),
    "087-幂级数展开与求和.md": ("幂级数", "收敛半径", "收敛区间"),
    "088-一阶线性微分方程.md": ("一阶线性微分方程",),
    "089-二阶常系数线性微分方程.md": ("二阶微分方程", "特征根"),
    "108-假设检验详解.md": ("假设检验", "显著性水平"),
}


def _catalog_value(item, key: str, default: str = "") -> str:
    if isinstance(item, Mapping):
        return str(item.get(key) or default).strip()
    if key == "id":
        return str(item).strip()
    return default


def _title_from_id(value: str) -> str:
    return re.sub(r"^\d{3}-|\.md$", "", str(value or "")).strip()


def _terms(title: str) -> tuple[str, ...]:
    title = _title_from_id(title)
    terms = []
    for run in _CJK_RUN.findall(title):
        for part in _SEPARATOR.split(run):
            if len(part) >= 2 and part not in _STOP_TERMS and part not in terms:
                terms.append(part)
    if title and title not in terms and len(title) >= 3:
        terms.insert(0, title)
    return tuple(terms)


def suggest_knowledge_point_ids(
    question_text: str,
    explanation: str = "",
    knowledge_catalog: Iterable[object] = (),
    max_points: int = 2,
) -> tuple[str, ...]:
    """Return provisional IDs only when catalog wording appears in the evidence.

    This is deliberately conservative: it fills the missing tags left by image
    extraction, but it does not invent a knowledge point from a weak match.
    """
    evidence = f"{question_text or ''}\n{explanation or ''}"
    if not evidence.strip():
        return ()
    scored = []
    for item in knowledge_catalog:
        knowledge_id = _catalog_value(item, "id")
        if not knowledge_id:
            continue
        title = _title_from_id(knowledge_id)
        terms = _terms(title)
        score = 0
        for term in terms:
            occurrences = evidence.count(term)
            if occurrences:
                score += 4 if len(term) >= 4 else 2
                score += min(occurrences - 1, 2)
        for alias in _MATH_ALIASES.get(knowledge_id, ()):
            occurrences = evidence.lower().count(alias.lower())
            if occurrences:
                score += 5 * min(occurrences, 2)
        if score:
            scored.append((score, int(re.match(r"^(\d+)", knowledge_id).group(1)) if re.match(r"^(\d+)", knowledge_id) else 9999, knowledge_id, title))

    # Duplicate catalog titles are kept in data for compatibility; only keep
    # the first ID for one conceptual title.
    selected = []
    seen_titles = set()
    for _, _, knowledge_id, title in sorted(scored, key=lambda value: (-value[0], value[1], value[2])):
        title_key = re.sub(r"[与和及、（）()\s]", "", title)
        if title_key in seen_titles:
            continue
        selected.append(knowledge_id)
        seen_titles.add(title_key)
        if len(selected) >= max(1, int(max_points)):
            break
    return tuple(selected)


def load_knowledge_catalog(corpus_dir: Path) -> tuple[dict, ...]:
    """Load the local math markdown catalog without changing its source files."""
    root = Path(corpus_dir)
    if not root.exists():
        return ()
    catalog = []
    for path in sorted(root.glob("*.md"), key=lambda item: item.name):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        catalog.append({"id": path.name, "text": text})
    return tuple(catalog)
