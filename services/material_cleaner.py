import re
from dataclasses import asdict, dataclass, field


PAGE_MARKER_RE = re.compile(r"^===\s*第\s*(\d+)\s*页\s*===$")
QUESTION_RE = re.compile(r"^(?:题\s*)?(\d+)\s*[.．、:：]\s*(.*)$")
SECTION_RE = re.compile(r"^(数据结构|计算机组成原理|组成原理|操作系统|计算机网络|计网)\s*[:：]?$")
INLINE_QUESTION_START_RE = re.compile(r"(?:(?<=^)|(?<=\s))(?:题\s*)?\d{1,3}\s*[.．、:：]")

NOISE_TOKENS = (
    "找研讯",
    "找真题",
    "找辅导",
    "聚创考研",
    "juchuang",
    "微信",
    "考研网",
    "扫描二维码",
    "公众号",
    "各个学校计算机考研/软件考研真题",
    "cskaoyan",
    "科大知博书店",
)

INLINE_NOISE_PATTERNS = (
    re.compile(r"\s*各个学校计算机考研/软件考研真题\s*免费分享\s*https?://\S+", re.IGNORECASE),
    re.compile(r"\s*各个学校计算机考研/软件考研真题\s*免费分享\s*", re.IGNORECASE),
    re.compile(r"\s*免费分享\s*https?://github\.com/csseky/cskaoyan\S*", re.IGNORECASE),
    re.compile(r"\s*https?://github\.com/csseky/cskaoyan\S*", re.IGNORECASE),
    re.compile(r"\s*github\.com/csseky/cskaoyan\S*", re.IGNORECASE),
    re.compile(r"(?:(?<=，)|(?<=,)|(?<=\s)|^)https(?=，|,|\s|$)", re.IGNORECASE),
)

NOISE_EXACT_LINES = {
    "选择题",
    "单项选择题",
    "多项选择题",
    "暂无",
}

PROMOTIONAL_LINE_PATTERNS = (
    re.compile(r"(关注|扫描|扫码).*(公众号|二维码|微信)", re.IGNORECASE),
    re.compile(r"(免费分享|考研资讯|复试资料|考研经验)", re.IGNORECASE),
    re.compile(r"github\.com/csseky/cskaoyan", re.IGNORECASE),
    re.compile(r"微信公众号.{0,20}计算机与软件考研", re.IGNORECASE),
)

QUESTION_CONTEXT_HINTS = (
    "下列",
    "已知",
    "设有",
    "执行",
    "原因",
    "作用",
    "功能",
    "正确",
    "错误",
    "操作",
    "算法",
    "协议",
)

SUSPICIOUS_TOKENS = ("微信", "公众号", "二维码", "扫码", "github", "广告")
MAX_REPORT_ITEMS = 8


@dataclass
class MaterialCleanResult:
    cleaned_text: str
    warnings: list[str] = field(default_factory=list)
    removed_noise_lines: int = 0
    removed_inline_noise: int = 0
    question_blocks: int = 0
    skipped_empty_questions: int = 0
    original_text_length: int = 0
    cleaned_text_length: int = 0
    removal_ratio: float = 0.0
    page_markers: int = 0
    removed_line_samples: list[str] = field(default_factory=list)
    inline_noise_samples: list[str] = field(default_factory=list)
    preserved_suspicious_samples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def clean_material_for_extraction(text: str) -> MaterialCleanResult:
    """Clean OCR/PDF text while preserving page and question-level citations."""
    normalized = _split_embedded_question_lines(_normalize_text(text))
    if not normalized:
        return MaterialCleanResult(cleaned_text="")

    entries = []
    current = None
    current_page = ""
    current_section = ""
    question_blocks = 0
    removed_noise_lines = 0
    removed_inline_noise = 0
    skipped_empty_questions = 0
    removed_line_samples = []
    inline_noise_samples = []
    preserved_suspicious_samples = []
    page_markers = 0

    def flush_current():
        nonlocal current, question_blocks
        if not current:
            return
        block_text = _compact_question_lines(current["lines"])
        if block_text:
            entries.append(
                {
                    "kind": "question",
                    "page": current.get("page", ""),
                    "question": current.get("question", ""),
                    "section": current.get("section", ""),
                    "text": block_text,
                }
            )
            question_blocks += 1
        current = None

    for raw_line in normalized.split("\n"):
        original_line = _clean_line(raw_line)
        line = strip_inline_material_noise(original_line)
        if not line:
            if original_line:
                removed_inline_noise += 1
                _append_sample(
                    inline_noise_samples,
                    f"第{current_page or '?'}页：{_truncate_preview(original_line)} -> [已清理]",
                )
            continue
        if line != original_line:
            removed_inline_noise += 1
            _append_sample(
                inline_noise_samples,
                f"第{current_page or '?'}页：{_truncate_preview(original_line)} -> {_truncate_preview(line)}",
            )

        page_match = PAGE_MARKER_RE.match(line)
        if page_match:
            flush_current()
            current_page = page_match.group(1)
            page_markers += 1
            continue

        question_match = QUESTION_RE.match(line)
        if question_match:
            flush_current()
            question_no, question_text = question_match.groups()
            if question_text and _is_empty_placeholder(question_text):
                skipped_empty_questions += 1
                current = None
                continue
            current = {
                "page": current_page,
                "question": question_no,
                "section": current_section,
                "lines": [question_text] if question_text else [],
            }
            continue

        section_match = SECTION_RE.match(line)
        if section_match:
            flush_current()
            current_section = section_match.group(1)
            continue

        if current is not None:
            if _is_context_noise_line(line):
                removed_noise_lines += 1
                _append_sample(removed_line_samples, f"第{current_page or '?'}页：{_truncate_preview(line)}")
                continue
            if not _is_empty_placeholder(line):
                current["lines"].append(line)
                if _looks_suspicious_but_allowed(line):
                    _append_sample(
                        preserved_suspicious_samples,
                        f"第{current_page or '?'}页 题{current.get('question') or '?'}：{_truncate_preview(line)}",
                    )
        else:
            if _is_noise_line(line):
                removed_noise_lines += 1
                _append_sample(removed_line_samples, f"第{current_page or '?'}页：{_truncate_preview(line)}")
                continue
            entries.append(
                {
                    "kind": "general",
                    "page": current_page,
                    "question": "",
                    "section": current_section,
                    "text": line,
                }
            )
            if _looks_suspicious_but_allowed(line):
                _append_sample(
                    preserved_suspicious_samples,
                    f"第{current_page or '?'}页：{_truncate_preview(line)}",
                )

    flush_current()

    cleaned_text = _format_entries(entries)

    original_text_length = len(normalized)
    cleaned_text_length = len(cleaned_text)
    removal_ratio = 0.0
    if original_text_length:
        removal_ratio = max(0.0, min(1.0, 1 - (cleaned_text_length / original_text_length)))

    warnings = []
    if removed_noise_lines:
        warnings.append(f"已清理 {removed_noise_lines} 行页眉、广告或重复噪声。")
    if removed_inline_noise:
        warnings.append(f"已清理 {removed_inline_noise} 处行内广告或来源噪声。")
    if skipped_empty_questions:
        warnings.append(f"已跳过 {skipped_empty_questions} 个空题或占位片段。")
    if question_blocks:
        warnings.append(f"已按页码和题号整理为 {question_blocks} 个可引用片段。")
    if preserved_suspicious_samples:
        warnings.append("检测到疑似噪声但已保留的内容，避免误删题干，请在对比区人工核对。")

    return MaterialCleanResult(
        cleaned_text=cleaned_text,
        warnings=warnings,
        removed_noise_lines=removed_noise_lines,
        removed_inline_noise=removed_inline_noise,
        question_blocks=question_blocks,
        skipped_empty_questions=skipped_empty_questions,
        original_text_length=original_text_length,
        cleaned_text_length=cleaned_text_length,
        removal_ratio=removal_ratio,
        page_markers=page_markers,
        removed_line_samples=removed_line_samples,
        inline_noise_samples=inline_noise_samples,
        preserved_suspicious_samples=preserved_suspicious_samples,
    )


def _normalize_text(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    cleaned = re.sub(r"[ \t\u3000]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _split_embedded_question_lines(text: str) -> str:
    if not text:
        return ""

    expanded_lines = []
    for raw_line in text.split("\n"):
        line = (raw_line or "").strip()
        if not line or PAGE_MARKER_RE.match(line):
            expanded_lines.append(line)
            continue

        positions = [match.start() for match in INLINE_QUESTION_START_RE.finditer(line)]
        if not positions:
            expanded_lines.append(line)
            continue

        if len(positions) == 1 and positions[0] == 0:
            expanded_lines.append(line)
            continue

        first_start = positions[0]
        prefix = line[:first_start].strip()
        if prefix:
            expanded_lines.append(prefix)

        for index, start in enumerate(positions):
            end = positions[index + 1] if index + 1 < len(positions) else len(line)
            segment = line[start:end].strip()
            if segment:
                expanded_lines.append(segment)

    return "\n".join(expanded_lines)


def _clean_line(line: str) -> str:
    line = (line or "").strip()
    line = line.replace("（", "(").replace("）", ")")
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def strip_inline_material_noise(text: str) -> str:
    cleaned = _clean_line(text)
    for pattern in INLINE_NOISE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\s*【缺失】\s*", "", cleaned)
    cleaned = re.sub(r"\s*【存疑】\s*", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _is_noise_line(line: str) -> bool:
    if _is_promotional_line(line):
        return True
    compact = re.sub(r"\s+", "", line).lower()
    if not compact:
        return True
    if line in NOISE_EXACT_LINES:
        return True
    if any(token.lower() in compact for token in NOISE_TOKENS):
        return True
    if re.fullmatch(r"[-_=—\s\d/]+", line):
        return True
    if re.fullmatch(r"202\d\s*考研.*真题.*解析", line):
        return True
    return False


def _is_context_noise_line(line: str) -> bool:
    if _is_promotional_line(line):
        return True
    compact = re.sub(r"\s+", "", line).lower()
    if not compact:
        return True
    if line in NOISE_EXACT_LINES:
        return True
    if _looks_like_question_content(line):
        return False
    return any(token.lower() in compact for token in NOISE_TOKENS)


def _is_empty_placeholder(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    return compact in {"", "暂无", "无", "空"}


def _is_promotional_line(line: str) -> bool:
    compact = re.sub(r"\s+", "", line or "").lower()
    if not compact:
        return False
    if any(pattern.search(line or "") for pattern in PROMOTIONAL_LINE_PATTERNS):
        return True
    if compact.startswith(("微信公众号", "微信号", "qq群", "qq号", "扫码", "扫描二维码")):
        return True
    if "http" in compact and any(token.lower() in compact for token in NOISE_TOKENS):
        return True
    return False


def _looks_like_question_content(line: str) -> bool:
    compact = re.sub(r"\s+", "", line or "")
    if re.match(r"^[A-D][.．]", line or ""):
        return True
    return any(token in compact for token in QUESTION_CONTEXT_HINTS)


def _looks_suspicious_but_allowed(line: str) -> bool:
    compact = re.sub(r"\s+", "", line or "").lower()
    if not compact:
        return False
    return any(token.lower() in compact for token in SUSPICIOUS_TOKENS) and not _is_promotional_line(line)


def _truncate_preview(text: str, limit: int = 72) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}..."


def _append_sample(target: list[str], sample: str) -> None:
    if sample and len(target) < MAX_REPORT_ITEMS:
        target.append(sample)


def _compact_question_lines(lines: list[str]) -> str:
    compacted = []
    pending_option = ""

    for line in lines:
        line = _clean_line(line)
        if not line:
            continue

        option_match = re.match(r"^([A-D])[.．]\s*(.*)$", line)
        if option_match:
            if pending_option:
                compacted.append(pending_option)
            label, content = option_match.groups()
            pending_option = f"{label}. {content}".strip()
            if content:
                compacted.append(pending_option)
                pending_option = ""
            continue

        if pending_option:
            compacted.append(f"{pending_option} {line}".strip())
            pending_option = ""
        else:
            compacted.append(line)

    if pending_option:
        compacted.append(pending_option)

    if _should_preserve_multiline_layout(compacted):
        preserved_lines = []
        for line in compacted:
            cleaned_line = strip_inline_material_noise(line)
            if cleaned_line:
                preserved_lines.append(cleaned_line)
        return "\n".join(preserved_lines).strip()

    text = " ".join(compacted)
    text = re.sub(r"\s+([,.;:，。；：])", r"\1", text)
    text = re.sub(r"([\(（])\s+", r"\1", text)
    text = re.sub(r"\s+([\)）])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return strip_inline_material_noise(text)


def _should_preserve_multiline_layout(lines: list[str]) -> bool:
    cleaned_lines = [_clean_line(line) for line in lines if _clean_line(line)]
    if len(cleaned_lines) < 6:
        return False

    layout_keywords = {"时间单元", "指令", "IF", "ID", "EX", "MEM", "M", "WB"}
    if sum(1 for line in cleaned_lines if line in layout_keywords) >= 3:
        return True

    short_lines = sum(1 for line in cleaned_lines if len(re.sub(r"\s+", "", line)) <= 6)
    tokenish_lines = sum(
        1
        for line in cleaned_lines
        if re.fullmatch(r"[A-Za-z0-9_+\-./()（）]{1,12}", line or "")
    )
    return short_lines >= 5 and tokenish_lines >= 3


def _format_entries(entries: list[dict]) -> str:
    output = []
    last_page = None
    for entry in entries:
        page = entry.get("page") or ""
        if page and page != last_page:
            output.append(f"=== 第{page}页 ===")
            last_page = page
        if entry.get("kind") == "question":
            section = entry.get("section") or ""
            section_prefix = f"{section} " if section else ""
            question = entry.get("question") or "?"
            output.append(f"{section_prefix}题{question}：{entry.get('text', '')}".strip())
            continue

        section = entry.get("section") or ""
        text = entry.get("text", "").strip()
        if not text:
            continue
        if section and not text.startswith(section):
            output.append(f"{section} {text}".strip())
        else:
            output.append(text)
    return "\n".join(output).strip()
