"""Build the deployable 313 history knowledge catalog from structured DOCX notes.

This is an offline build tool. The web application reads only the generated
JSON artifact and never depends on the author's local document directory.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = PROJECT_ROOT.parent / "General Examination in History"
DEFAULT_OUTPUT = PROJECT_ROOT / "professional_knowledge" / "builtin_history_points.json"

SOURCE_SPECS = (
    ("中国古代史（合集）.docx", "中国古代史"),
    ("中国近现代史.docx", "中国近现代史"),
    ("世界古代史.docx", "世界古代中世纪史"),
    ("世界近现代史.docx", "世界近现代史"),
)

GENERIC_TITLES = {
    "背景",
    "原因",
    "经过",
    "内容",
    "措施",
    "性质",
    "影响",
    "意义",
    "评价",
    "特点",
    "结果",
    "文化",
    "经济",
    "政治",
    "演化",
    "概况",
    "起源",
    "缺陷",
    "东亚",
    "西亚",
    "非洲",
}

NOISE_PATTERNS = (
    re.compile(r"^子主题\s*\d*$"),
    re.compile(r"^[□☐■◆◇•·]+$"),
    re.compile(r"^(?:暂无|待补充|未命名)$"),
)

EMBEDDED_PAGE_HEADER_PATTERNS = (
    re.compile(r"中国古代史强化教程\s*\d+\s*"),
    re.compile(r"中国近现代史强化教程\s*\d+\s*"),
    re.compile(r"世界史古代中世纪史强化教程\s*\d+\s*"),
    re.compile(r"世界近现代史强化教程\s*\d+\s*"),
)

TERMINAL_SECTION_TOKENS = (
    "意义",
    "影响",
    "评价",
    "作用",
    "结果",
    "历史地位",
)

OBVIOUS_CORRECTIONS = (
    ("英国资产阶级革命1868年", "英国资产阶级革命（17世纪）"),
    ("隋朝灭亡581x 618", "隋朝灭亡（618年）"),
    ("1975，马嘉里事件", "1875年马嘉里事件"),
    ("1975,马嘉里事件", "1875年马嘉里事件"),
    ("秦朗的中央机构", "秦朝的中央机构"),
    ("互相牵剖", "互相牵制"),
    ("决断杖集中", "决策权集中"),
    ("内朝”或曰“中朝”", "“内朝”或“中朝”"),
    ("三公的职位强高", "三公的地位崇高"),
    ("中框权力机构", "中枢权力机构"),
    ("委大致于六部", "委大政于六部"),
    ("中书门下主民", "中书门下主政"),
    ("与等相合称", "与宰相合称"),
    ("对政叔的直接控制", "对政务的直接控制"),
    ("第三次技水革命", "第三次技术革命"),
    ("河南省实阳市", "河南省安阳市"),
    ("小屯村及其肩围", "小屯村及其周围"),
    ("哲•学家", "哲学家"),
)

EXACT_TEXT_CORRECTIONS = {
    "总结民国初年（北洋政府": "总结民国初年（北洋政府）",
}

INVALID_SOURCE_LINES = {
    # This source paragraph ends at an attributive particle and has no object.
    # Omitting it is safer than inventing a historical conclusion.
    "东汉以来门阀士族势力恶性膨胀的",
}

CONTEXTUAL_TITLES = {
    (
        "三国（—265）魏晋（265-318-420）南北朝（420-589）",
        "文化",
    ): "魏晋南北朝文化",
}


@dataclass(frozen=True)
class ParagraphNode:
    level: int
    text: str


def _paragraph_level(paragraph) -> int:
    properties = paragraph._p.pPr
    numbering = properties.numPr if properties is not None else None
    if numbering is None or numbering.ilvl is None:
        return -1
    return int(numbering.ilvl.val)


def _clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    for pattern in EMBEDDED_PAGE_HEADER_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.lstrip("□☐■◆◇•· ").strip()
    text = EXACT_TEXT_CORRECTIONS.get(text, text)
    for old, new in OBVIOUS_CORRECTIONS:
        text = text.replace(old, new)
    text = text.replace("★", "").replace("🌟", "").replace("\ufffd", "")
    text = text.replace("•", "·")
    text = text.replace("【知识拓展】", "知识拓展：")
    text = re.sub(r"\*{1,3}", "", text)
    text = text.translate(str.maketrans({",": "，", ";": "；", ":": "："}))
    text = re.sub(r"\s+([，。；：！？])", r"\1", text)
    text = re.sub(r"([，。；：！？])\s+", r"\1", text)
    text = re.sub(r"。；", "；", text)
    text = re.sub(r"([。！？；]){2,}", r"\1", text)
    if text in INVALID_SOURCE_LINES:
        return ""
    return text


def _is_noise(value: str) -> bool:
    text = _clean_text(value)
    return not text or any(pattern.fullmatch(text) for pattern in NOISE_PATTERNS)


def _load_nodes(path: Path) -> list[ParagraphNode]:
    nodes: list[ParagraphNode] = []
    for paragraph in Document(path).paragraphs:
        text = _clean_text(paragraph.text)
        if not _is_noise(text):
            nodes.append(ParagraphNode(_paragraph_level(paragraph), text))
    return nodes


def _compact_title(value: str, *, limit: int = 68) -> str:
    text = _clean_text(value)
    text = re.sub(r"^[（(]?\d+[）).、:：]\s*", "", text)
    text = text.lstrip("-—： ")
    if len(text) <= limit:
        return text
    for separator in ("—", "：", ":", "（", "(", "，", "。"):
        head = text.split(separator, 1)[0].strip()
        if 4 <= len(head) <= limit:
            return head
    return text[:limit].rstrip("，。；;：:-— ")


def _unique_name(parent: str, title: str, seen: set[str]) -> str:
    clean_parent = _clean_text(parent)
    title = _compact_title(title)
    contextual_title = CONTEXTUAL_TITLES.get((clean_parent, title))
    if contextual_title:
        title = contextual_title
    elif title in GENERIC_TITLES or len(title) <= 2:
        compact_parent = _compact_title(clean_parent, limit=32)
        title = f"{compact_parent} · {title}" if compact_parent else title
    candidate = title
    serial = 2
    while candidate in seen:
        candidate = f"{title}（{serial}）"
        serial += 1
    seen.add(candidate)
    return candidate


def _section_lines(nodes: list[ParagraphNode], start: int) -> list[ParagraphNode]:
    lines: list[ParagraphNode] = []
    for node in nodes[start + 1 :]:
        if node.level <= 1:
            break
        lines.append(node)
    return lines


def _complete_excerpt(value: str, max_chars: int) -> str:
    """Return a readable excerpt without cutting a sentence or word in half."""
    text = _clean_text(value)
    if len(text) <= max_chars:
        return text
    window = text[: max_chars + 1]
    sentence_ends = [match.end() for match in re.finditer(r"[。！？；]", window)]
    useful_ends = [end for end in sentence_ends if end >= min(36, max_chars // 2)]
    if useful_ends:
        return text[: useful_ends[-1]].strip()
    clause_ends = [match.end() for match in re.finditer(r"[，、：]", window)]
    useful_clauses = [end for end in clause_ends if end >= min(28, max_chars // 2)]
    if useful_clauses:
        return text[: useful_clauses[-1]].rstrip("，、：") + "。"
    return ""


def _split_outline_heading(value: str, section_number: int) -> tuple[str, str]:
    """Turn a source paragraph into a short heading plus complete body text."""
    text = _clean_text(value)
    text = re.sub(r"^[（(]?\d+[）).、，,:：]\s*", "", text).strip()
    if len(text) <= 42:
        return text.rstrip("，；： "), ""

    for separator in ("—", "：", "，"):
        if separator not in text:
            continue
        heading, body = (part.strip() for part in text.split(separator, 1))
        if 2 <= len(heading) <= 18 and body:
            return heading, _complete_excerpt(body, 180) or body

    body = _complete_excerpt(text, 180)
    return f"要点 {section_number}", body


def _trim_join(lines: list[str], *, max_chars: int) -> str:
    output: list[str] = []
    used = 0
    for line in lines:
        clean = _clean_text(line)
        if not clean or clean in output:
            continue
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(clean) > remaining:
            clean = _complete_excerpt(clean, remaining)
            if not clean:
                break
            output.append(clean)
            break
        output.append(clean)
        used += len(clean)
    return "\n".join(output)


def _split_direct_groups(section: list[ParagraphNode], level: int) -> list[list[ParagraphNode]]:
    groups: list[list[ParagraphNode]] = []
    current: list[ParagraphNode] = []
    for node in section:
        if node.level == level:
            if current:
                groups.append(current)
            current = [node]
        elif current:
            current.append(node)
    if current:
        groups.append(current)
    return groups


def _selected_major_groups(section: list[ParagraphNode]) -> list[list[ParagraphNode]]:
    direct_levels = [node.level for node in section if node.level >= 0]
    if not direct_levels:
        return []
    major_level = min(direct_levels)
    groups = _split_direct_groups(section, major_level)
    selected: list[list[ParagraphNode]] = []
    used_chars = 0
    for group in groups:
        heading = _compact_title(group[0].text, limit=36)
        group_chars = sum(len(node.text) for node in group)
        if selected and used_chars + group_chars > 1100:
            break
        selected.append(group)
        used_chars += group_chars
        if any(token in heading for token in TERMINAL_SECTION_TOKENS):
            break
        if len(selected) >= 4:
            break
    return selected


def _format_major_group(group: list[ParagraphNode], section_number: int) -> str:
    heading_node = group[0]
    heading, lead = _split_outline_heading(heading_node.text, section_number)
    descendants = group[1:]
    parts = [f"**2.{section_number} {heading}**"]
    if lead:
        parts.append(lead)
    if not descendants:
        return "\n\n".join(parts)

    child_levels = [node.level for node in descendants if node.level > heading_node.level]
    child_level = min(child_levels) if child_levels else None
    child_groups = _split_direct_groups(descendants, child_level) if child_level is not None else []
    if not child_groups:
        paragraph = _trim_join([node.text for node in descendants], max_chars=200)
        if paragraph:
            parts.append(paragraph)
        return "\n\n".join(parts)

    numbered_lines: list[str] = []
    for item_number, child_group in enumerate(child_groups[:5], start=1):
        child_heading = _clean_text(child_group[0].text)
        detail = _trim_join(
            [node.text for node in child_group[1:]],
            max_chars=120,
        ).replace("\n", "")
        child_heading = re.sub(r"^[（(]?\d+[）).、，,:：]\s*", "", child_heading).strip()
        if detail and len(child_heading) <= 42:
            numbered_lines.append(f"{item_number}. **{child_heading}**：{detail}")
        else:
            statement = child_heading
            if detail:
                statement = f"{statement}；{detail}"
            numbered_lines.append(f"{item_number}. {statement}")
    parts.append("\n\n".join(numbered_lines))
    return "\n\n".join(parts)


def _format_core_definition(parent: str, name: str, section: list[ParagraphNode]) -> str:
    if parent == "专题":
        location = f"专题：{name}"
    elif parent:
        location = f"{parent}，{name}"
    else:
        location = name
    parts = [f"**1. 历史定位**\n\n{location or name}"]
    major_groups = _selected_major_groups(section)
    if major_groups:
        parts.append("**2. 核心要点**")
        parts.extend(
            _format_major_group(group, index)
            for index, group in enumerate(major_groups, start=1)
        )
    else:
        fallback = _trim_join([node.text for node in section], max_chars=650)
        if fallback:
            parts.append(f"**2. 核心要点**\n\n{fallback}")
    output = "\n\n".join(parts)
    output = output.replace("。；", "；").replace("：：", "：")
    return output


def _extract_keywords(title: str, parent: str, lines: list[ParagraphNode]) -> list[str]:
    candidates: list[str] = []
    candidates.extend(re.findall(r"《[^》]{2,24}》", " ".join([title, *[item.text for item in lines[:18]]])))
    candidates.extend(re.findall(r"(?:公元前|公元)?\s*\d{3,4}\s*年", " ".join([title, *[item.text for item in lines[:12]]])))
    for value in (title, parent):
        candidates.extend(
            item.strip()
            for item in re.split(r"[·—,:：，、（）()；;\s]+", value)
            if 2 <= len(item.strip()) <= 18 and not re.fullmatch(r"\d+年?", item.strip())
        )
    for node in lines:
        if node.level <= 3 and 2 <= len(node.text) <= 20:
            candidates.append(_compact_title(node.text, limit=20))
        if len(candidates) >= 18:
            break
    return list(dict.fromkeys(item for item in candidates if item))[:10]


def _exam_styles(name: str, content: str) -> list[str]:
    text = f"{name} {content}"
    styles = ["名词解释", "简答题"]
    if any(token in text for token in ("战争", "革命", "改革", "运动", "条约", "制度", "王朝")):
        styles.append("按背景—过程/内容—影响组织论述")
    if any(token in text for token in ("比较", "关系", "演变", "发展", "差异", "评价")):
        styles.append("比较分析题")
    styles.append("结合材料概括并解释历史现象")
    return list(dict.fromkeys(styles))[:4]


def _review_priority(name: str, content: str) -> str:
    high_value_terms = (
        "战争",
        "革命",
        "改革",
        "制度",
        "王朝",
        "统一",
        "思想",
        "条约",
        "经济",
        "文化",
        "民族",
        "国际关系",
    )
    return "高" if any(term in f"{name} {content}" for term in high_value_terms) else "中"


def _build_point(
    *,
    exam_subject: str,
    parent: str,
    raw_title: str,
    section: list[ParagraphNode],
    seen_names: set[str],
) -> dict:
    name = _unique_name(parent, raw_title, seen_names)
    major_groups = _selected_major_groups(section)
    selected_nodes = [node for group in major_groups for node in group] or section
    headings = [
        _compact_title(node.text, limit=42)
        for node in selected_nodes
        if 2 <= node.level <= 3 and 2 <= len(node.text) <= 32
    ]
    body_lines = [node.text for node in section]
    # The deployable catalog is a retrieval index, not a copy of the source
    # books. Keep enough context to ground answers while avoiding multi-page
    # entries that are slow to search and difficult to review.
    source_text = _trim_join(body_lines, max_chars=1200)
    path = " > ".join(part for part in (parent, raw_title) if part)
    keywords = _extract_keywords(name, parent, section)
    return {
        "subject": "历史学统考",
        "chapter_name": exam_subject,
        "knowledge_name": name,
        "knowledge_type": "313内置知识点",
        "core_definition": _format_core_definition(parent, name, section),
        "exam_question_styles": _exam_styles(name, source_text),
        "keywords": keywords,
        "pitfalls": [
            "不要只背孤立年代，要把事件放回同时期的政治、经济与社会背景中。",
            "原因、导火线、条件和背景不能混写；影响要区分当时作用与长期作用。",
        ],
        "related_concepts": list(dict.fromkeys(headings))[:8],
        "example_or_application": (
            f"围绕“{name}”完成一道材料题：先从材料提取时间、人物或制度线索，"
            "再结合知识库说明背景、核心内容及历史影响。"
        ),
        "source_text": source_text,
        "source_location": path,
        "tags": [exam_subject, "313", "历史学统考", *keywords[:4]],
        "review_priority": _review_priority(name, source_text),
        "uncertainty_note": "由课程资料结构化整理；涉及精确年代、数字和学界争议时应与统考参考书复核。",
    }


def build_catalog(source_root: Path) -> list[dict]:
    points: list[dict] = []
    seen_names: set[str] = set()
    for filename, exam_subject in SOURCE_SPECS:
        path = source_root / filename
        if not path.is_file():
            raise FileNotFoundError(f"缺少历史资料：{path}")
        nodes = _load_nodes(path)
        parents: dict[int, str] = {}
        for index, node in enumerate(nodes):
            if node.level >= 0:
                parents[node.level] = node.text
                for level in list(parents):
                    if level > node.level:
                        parents.pop(level, None)
            if node.level != 1:
                continue
            section = _section_lines(nodes, index)
            if not section:
                continue
            point = _build_point(
                exam_subject=exam_subject,
                parent=parents.get(0, ""),
                raw_title=node.text,
                section=section,
                seen_names=seen_names,
            )
            if len(point["source_text"]) >= 80:
                points.append(point)
    return points


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    points = build_catalog(args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "version": 1,
                "subject": "历史学统考",
                "exam_code": "313",
                "point_count": len(points),
                "points": points,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    counts: dict[str, int] = {}
    for point in points:
        chapter = point["chapter_name"]
        counts[chapter] = counts.get(chapter, 0) + 1
    print(f"generated {len(points)} points -> {args.output}")
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
