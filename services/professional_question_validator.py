import re

from services.professional_question_prompts import (
    is_408_knowledge_point,
    is_history_knowledge_point,
)


def is_placeholder_question(question):
    normalized = re.sub(r"[\s。！？!?,，:：；;、]+", "", str(question or "")).strip()
    return normalized in {"", "题目", "问题", "练习题", "概念自测", "请作答"}


def looks_like_408_exam_task(generated, mode, point=None):
    if point is not None and not is_408_knowledge_point(point):
        return True
    question = str(generated.get("question") or "")
    options = " ".join(str(item) for item in (generated.get("options") or []))
    body = f"{question} {options}".lower()
    bad_markers = (
        "只需要背定义",
        "所有相关题目",
        "任何题都可以直接套固定公式",
        "不需要说明过程",
        "围绕“",
        "某同学把它和相邻概念混用",
        "给出一个围绕",
    )
    if any(marker.lower() in body for marker in bad_markers):
        return False
    if mode == "blank":
        stable_cloze_patterns = [
            r"_{3,}|（\s*）|\(\s*\)|【\s*】|\[\s*\]",
            r"复杂度|稳定|不稳定|适用|条件|字段|标志位|补码|浮点|cache|tlb|fifo|lru|clock|tcp|udp|ip|crc|dma|alu|wpl|aov|kmp|b\+?树|dijkstra|floyd",
            r"线性表|链表|栈|队列|树|图|排序|查找|哈夫曼|进程|线程|调度|死锁|页面|页表|地址|窗口|子网|掩码|流水线|指令|总线|中断",
        ]
        return (
            sum(1 for pattern in stable_cloze_patterns if re.search(pattern, body, re.IGNORECASE)) >= 2
            and blank_marker_count(question) >= 1
        )
    concrete_patterns = [
        r"\d",
        r"[a-z]\s*->\s*[a-z]",
        r"[{}\[\]()]",
        r"\b0x[0-9a-f]+\b",
        r"[0-9a-f]{4,}h\b",
        r"ip|tcp|udp|ack|crc|cache|tlb|fifo|lru|clock|dma|alu|wpl|aov|kmp|b\+?树|dijkstra|floyd|dist",
        r"边集|序列|页框|页面访问串|资源矩阵|路由表|地址字段|主存地址|指令格式|入度|前驱|后继|先序|中序|后序|频率|权值|窗口|子网|掩码|流水线|信号量|进程|无穷大|最短路径|松弛|距离数组|候选集|顶点集",
    ]
    concrete_hits = sum(1 for pattern in concrete_patterns if re.search(pattern, body, re.IGNORECASE))
    constraint_hits = sum(
        1
        for marker in (
            "必须",
            "允许",
            "要求",
            "初始",
            "完成后",
            "之前",
            "之后",
            "互斥",
            "同步",
            "前缀",
            "有序",
            "连续",
            "不超过",
            "至少",
            "至多",
        )
        if marker in question
    )
    task_verbs = (
        "计算", "判断", "写出", "画出", "构造", "推导", "说明", "比较", "分析", "设计", "给出",
        "填空", "补全", "选出", "选择", "正确", "错误", "最合适", "符合", "不符合",
        "确定", "求", "求出", "填写", "更新", "松弛", "改用",
    )
    verb_hits = sum(1 for verb in task_verbs if verb in question)
    if mode == "choice":
        return concrete_hits >= 1 and len(generated.get("options") or []) >= 4
    if mode == "concept":
        return concrete_hits >= 1 and verb_hits >= 1
    return (
        (concrete_hits >= 1 or constraint_hits >= 2)
        and verb_hits >= 1
        and len(question) >= 45
    )


def looks_like_history_exam_task(generated, mode, point=None):
    if point is not None and not is_history_knowledge_point(point):
        return True
    question = str(generated.get("question") or "")
    options = " ".join(str(item) for item in (generated.get("options") or []))
    body = f"{question} {options}"
    bad_markers = (
        "谈谈你的感想",
        "你认为历史重要吗",
        "只需背诵",
        "围绕某知识点",
        "围绕“",
        "任意举例",
    )
    if any(marker in body for marker in bad_markers):
        return False
    evidence_patterns = (
        r"(?:公元前|公元)?\d{2,4}年",
        r"\d{1,2}世纪",
        r"材料[一二三123]",
        r"夏|商|周|春秋|战国|秦|西汉|东汉|三国|曹魏|蜀汉|孙吴|"
        r"魏晋|西晋|东晋|十六国|南北朝|隋|唐|宋|元|明|清|民国",
        r"党史|中共|中国共产党|新中国|现代化|工业化|改革开放|三线建设",
        r"朝|时期|战争|革命|改革|运动|条约|制度|会议|王国|帝国|共和国",
        r"中国|欧洲|亚洲|非洲|美洲|世界|近代|现代|古代|中世纪|民族|政权|国家|社会",
    )
    evidence_hits = sum(
        1 for pattern in evidence_patterns if re.search(pattern, body, re.IGNORECASE)
    )
    task_verbs = (
        "指出", "概括", "分析", "比较", "评价", "说明", "论述", "解释",
        "排序", "判断", "选出", "选择", "归纳", "结合", "辨析",
    )
    verb_hits = sum(1 for verb in task_verbs if verb in question)
    if mode == "blank":
        return evidence_hits >= 1 and blank_marker_count(question) >= 1
    if mode == "choice":
        return evidence_hits >= 1 and len(generated.get("options") or []) >= 4
    if mode in {"concept", "algorithm"}:
        return evidence_hits >= 1 and verb_hits >= 1
    return evidence_hits >= 2 and verb_hits >= 2


def choice_reference_has_conflict(generated):
    correct = str(generated.get("correct_answer") or "").strip().upper()[:1]
    if correct not in {"A", "B", "C", "D"}:
        return True
    reference = str(generated.get("reference_answer") or "")
    shaky_markers = (
        "与选项不符",
        "可能指另一种",
        "题目描述的",
        "但此过程",
        "无法确定",
        "存在歧义",
        "口径不一致",
    )
    if any(marker in reference for marker in shaky_markers):
        return True
    for label in ("A", "B", "C", "D"):
        if label == correct:
            continue
        option_claims_correct = re.search(
            rf"(?:选项)?{label}[^。；;\n]{{0,45}}(?:正确|可行|符合|成立)",
            reference,
        )
        if option_claims_correct:
            return True
    return False


def reference_has_internal_conflict(generated):
    body = "\n".join(
        str(generated.get(field) or "")
        for field in ("question", "correct_answer", "reference_answer")
    )
    conflict_markers = (
        "但答案给出",
        "答案给出",
        "严格来说",
        "可能是基于",
        "可能假设",
        "存在歧义",
        "无法确定答案",
        "无法确定正确答案",
        "不一致",
        "互相矛盾",
        "这可能是",
        "为了符合题目要求",
    )
    if any(marker in body for marker in conflict_markers):
        return True
    lowered = body.lower()
    if "cache" in lowered or "组相联" in body:
        if re.search(r"已有\s*1\s*个块[^。；\n]{0,80}(?:lru|替换)", body, re.IGNORECASE):
            way_match = re.search(r"(\d+)\s*路组相联", body, re.IGNORECASE)
            if way_match and int(way_match.group(1)) > 1:
                return True
        if re.search(r"替换[^。；\n]{0,50}(?:填入|放入)[^。；\n]{0,20}另一路", body):
            return True
    return False


def cache_reference_has_calculation_conflict(generated):
    question = str(generated.get("question") or "")
    reference = str(generated.get("reference_answer") or "")
    if "cache" not in question.lower():
        return False
    initial_empty = re.search(
        r"初始(?:状态)?(?:为)?空|初始(?:均)?无效|开始时为空|有效位初始(?:均)?为?0",
        question,
    )
    asks_sequence_result = (
        "访问序列" in question
        and any(marker in question for marker in ("命中", "缺失", "失效", "推演"))
    )
    if asks_sequence_result and not initial_empty:
        return True
    if not initial_empty:
        return False

    capacity_match = re.search(
        r"Cache[^。\n]{0,30}?(?:容量|大小|数据区)[^0-9]{0,8}(\d+)\s*(KB|K|B|字节)",
        question,
        re.IGNORECASE,
    )
    block_match = re.search(
        r"(?:块|行)(?:大小|长)[^0-9]{0,8}(\d+)\s*(KB|K|B|字节)",
        question,
        re.IGNORECASE,
    )
    direct_mapped = "直接映射" in question
    way_match = re.search(r"(\d+)\s*路(?:组)?相联", question, re.IGNORECASE)

    def byte_count(match):
        value = int(match.group(1))
        unit = match.group(2).upper()
        return value * 1024 if unit in {"K", "KB"} else value

    addresses = [
        int(value, 16)
        for value in re.findall(r"0x([0-9a-f]+)(?![0-9a-f])", question, re.IGNORECASE)
    ]
    block_sequence_match = re.search(
        r"访问序列(?:[（(]\s*块号\s*[）)])?[^：:\n]{0,10}[：:]\s*"
        r"([0-9][0-9\s,，、]*)",
        question,
    )
    decimal_address_match = re.search(
        r"(?:主存)?地址[（(]\s*十进制\s*[）)][^：:\n]{0,10}[：:]\s*"
        r"([0-9][0-9\s,，、]*)",
        question,
    )
    block_numbers = (
        [address // byte_count(block_match) for address in addresses]
        if addresses and block_match
        else [
            int(value) // byte_count(block_match)
            for value in re.findall(
                r"\d+",
                decimal_address_match.group(1) if decimal_address_match else "",
            )
        ]
        if decimal_address_match and block_match
        else [
            int(value)
            for value in re.findall(
                r"\d+",
                block_sequence_match.group(1) if block_sequence_match else "",
            )
        ]
    )
    if not (
        capacity_match
        and block_match
        and (way_match or direct_mapped)
        and len(block_numbers) >= 2
    ):
        return False

    capacity = byte_count(capacity_match)
    block_size = byte_count(block_match)
    ways = 1 if direct_mapped else int(way_match.group(1))
    if block_size <= 0 or ways <= 0 or capacity % (block_size * ways):
        return False
    set_count = capacity // (block_size * ways)
    if set_count <= 0:
        return False

    sets = [[] for _ in range(set_count)]
    expected_hits = []
    for block_number in block_numbers:
        set_index = block_number % set_count
        tag = block_number // set_count
        lru = sets[set_index]
        hit = tag in lru
        expected_hits.append(hit)
        if hit:
            lru.remove(tag)
        elif len(lru) >= ways:
            lru.pop(0)
        lru.append(tag)

    expected_hit_count = sum(expected_hits)
    expected_miss_count = len(expected_hits) - expected_hit_count
    reference_scope = reference
    if direct_mapped:
        second_mapping = re.search(r"\b2\s*路(?:组)?相联", reference, re.IGNORECASE)
        if second_mapping:
            reference_scope = reference[:second_mapping.start()]
    hit_count_claims = [
        int(value)
        for value in (
            re.findall(
                r"(?:共|总共|合计)?\s*(\d+)\s*次(?:Cache\s*)?命中",
                reference_scope,
                re.IGNORECASE,
            )
            + re.findall(
                r"(?<!不)(?<!未)命中(?:共|总共|合计)?\s*(\d+)\s*次",
                reference_scope,
                re.IGNORECASE,
            )
        )
    ]
    miss_count_claims = [
        int(value)
        for value in (
            re.findall(
                r"(?:共|总共|合计)?\s*(\d+)\s*次(?:Cache\s*)?(?:不命中|未命中|缺失|失效)",
                reference_scope,
                re.IGNORECASE,
            )
            + re.findall(
                r"(?:不命中|未命中|缺失|失效)(?:共|总共|合计)?\s*(\d+)\s*次",
                reference_scope,
                re.IGNORECASE,
            )
        )
    ]
    if any(value != expected_hit_count for value in hit_count_claims):
        return True
    if any(value != expected_miss_count for value in miss_count_claims):
        return True

    for address, expected_hit in zip(addresses, expected_hits):
        address_digits = f"{address:X}"
        address_pattern = (
            r"0x0+(?![0-9a-f])"
            if address == 0
            else rf"0x0*{re.escape(address_digits)}(?![0-9a-f])"
        )
        match = re.search(address_pattern, reference, re.IGNORECASE)
        if not match:
            continue
        segment = reference[match.end():match.end() + 100]
        segment = re.sub(
            r"\d+\s*次(?:Cache\s*)?(?:命中|不命中|未命中|缺失|失效)",
            "",
            segment,
            flags=re.IGNORECASE,
        )
        explicit_miss = re.search(r"(?:不命中|未命中|缺失|失效)", segment)
        explicit_hit = re.search(r"(?<!不)(?<!未)命中", segment)
        if expected_hit and explicit_miss:
            return True
        if not expected_hit and explicit_hit and not explicit_miss:
            return True
    return False


def blank_marker_count(question):
    body = str(question or "")
    patterns = (
        r"_{3,}",
        r"（\s*）",
        r"\(\s*\)",
        r"【\s*】",
        r"\[\s*\]",
        r"空\s*\d+",
    )
    return sum(len(re.findall(pattern, body)) for pattern in patterns)


def split_blank_answers(answer_text):
    text = str(answer_text or "")
    if "；" in text or ";" in text or "\n" in text:
        separators = r"[；;\n]+"
    elif "，" in text:
        separators = r"[，]+"
    elif "," in text and not re.search(r"[\[\]()]|min\s*\(", text, re.IGNORECASE):
        separators = r"[,]+"
    else:
        separators = r"$^"
    return [
        item.strip(" \t\r\n'\"[]()（）")
        for item in re.split(separators, text)
        if item.strip(" \t\r\n'\"[]()（）")
    ]


def normalize_answer_for_match(text):
    return re.sub(r"\s+", "", str(text or "")).lower()


def reference_asserts_blank_answer(reference, answer):
    normalized_reference = normalize_answer_for_match(reference)
    normalized_answer = normalize_answer_for_match(answer)
    if not normalized_answer:
        return False
    if normalized_answer not in normalized_reference:
        formula_markers = ("min(", "max(", "dist[", "d[", "w(")
        if any(marker in normalized_answer for marker in formula_markers):
            formula_overlap = sum(
                1 for marker in formula_markers
                if marker in normalized_answer and marker in normalized_reference
            )
            has_assignment = "=" in normalized_answer and "=" in normalized_reference
            if formula_overlap >= 2 and has_assignment:
                return True
        return False

    is_single_choice_like = bool(re.fullmatch(r"[a-d]", normalized_answer, re.IGNORECASE))
    is_short_number = bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?", normalized_answer))
    is_short_symbol = normalized_answer in {"∞", "无穷大"}
    if not (is_single_choice_like or is_short_number or is_short_symbol):
        return True

    conclusion_markers = (
        "填",
        "填写",
        "应填",
        "故填",
        "空为",
        "答案为",
        "结果为",
        "长度为",
        "距离为",
        "值为",
        "等于",
        "是",
    )
    for marker in conclusion_markers:
        start = 0
        while True:
            index = normalized_reference.find(marker, start)
            if index < 0:
                break
            segment = normalized_reference[index + len(marker):index + len(marker) + 18]
            answer_index = segment.find(normalized_answer)
            if answer_index >= 0:
                prefix = segment[:answer_index]
                if is_short_number and re.search(r"\d", prefix):
                    start = index + len(marker)
                    continue
                return True
            start = index + len(marker)

    if is_single_choice_like:
        return False
    return normalized_reference.count(normalized_answer) >= 2


def blank_answers_are_supported_by_reference(generated):
    answers = split_blank_answers(generated.get("correct_answer"))
    if not answers:
        return False
    question = str(generated.get("question") or "")
    reference = str(generated.get("reference_answer") or "")
    blank_count = blank_marker_count(question)
    if blank_count > 1 and len(answers) < blank_count:
        return False
    for answer in answers:
        if not reference_asserts_blank_answer(reference, answer):
            return False
    return True


def is_valid_professional_question_for_point(generated, mode, point=None):
    question = str(generated.get("question") or "").strip()
    reference_answer = str(generated.get("reference_answer") or "").strip()
    if is_placeholder_question(question) or len(question) < 18 or not reference_answer:
        return False
    if not question_type_matches_mode(generated.get("question_type"), mode):
        return False
    if contains_source_noise(generated):
        return False
    if known_domain_fact_conflict(generated):
        return False
    if cache_reference_has_calculation_conflict(generated):
        return False
    if reference_has_internal_conflict(generated):
        return False
    grading_points = generated.get("grading_points") or []
    if not isinstance(grading_points, list) or len(grading_points) < 2:
        return False
    if mode == "choice":
        options = generated.get("options") or []
        if len(options) < 4 or not str(generated.get("correct_answer") or "").strip():
            return False
        if choice_reference_has_conflict(generated):
            return False
    if mode == "blank":
        if blank_marker_count(question) < 1:
            return False
        if not str(generated.get("correct_answer") or "").strip():
            return False
        if not blank_answers_are_supported_by_reference(generated):
            return False
    if point is not None and is_408_knowledge_point(point):
        if not looks_like_408_exam_task(generated, mode, point=point):
            return False
    if point is not None and is_history_knowledge_point(point):
        if not looks_like_history_exam_task(generated, mode, point=point):
            return False
        if mode == "algorithm" and not history_essay_grading_points_are_valid(grading_points):
            return False
    return True


def is_valid_professional_question(generated, mode):
    return is_valid_professional_question_for_point(generated, mode, None)


def question_type_matches_mode(question_type, mode):
    normalized = re.sub(
        r"[\s_-]+",
        "",
        str(question_type or mode or "").strip().lower(),
    )
    aliases = {
        "choice": {"choice", "singlechoice", "选择题", "单选题"},
        "blank": {"blank", "fillblank", "填空题"},
        "application": {"application", "综合题", "综合应用题", "史料题", "material"},
        "quiz": {"quiz", "application", "综合题", "综合应用题", "史料题", "material"},
        "algorithm": {
            "algorithm",
            "算法题",
            "过程推演题",
            "论述题",
            "essay",
            "historyessay",
        },
        "concept": {"concept", "概念题", "概念辨析题", "名词解释"},
    }
    return normalized in aliases.get(str(mode or ""), {str(mode or "").lower()})


def contains_source_noise(generated):
    body = "\n".join(
        [
            str(generated.get("question") or ""),
            " ".join(str(item) for item in (generated.get("options") or [])),
            str(generated.get("reference_answer") or ""),
        ]
    ).lower()
    markers = (
        "公众号",
        "扫码",
        "二维码",
        "微信",
        "领取资料",
        "免费分享",
        "考研网课",
        "github.com",
        "cskaoyan",
        "研池大叔",
        "弘毅考研",
        "创梦资料",
    )
    return any(marker.lower() in body for marker in markers)


def history_essay_grading_points_are_valid(grading_points):
    parsed = []
    for point in grading_points or []:
        text = str(point or "")
        scores = [int(value) for value in re.findall(r"(\d{1,2})\s*分", text)]
        if not scores:
            return False
        parsed.append((text, sum(scores)))
    if sum(score for _text, score in parsed) != 40:
        return False
    organization_score = sum(
        score
        for text, score in parsed
        if any(marker in text for marker in ("论述组织", "史论结合", "逻辑", "文字表达", "文字流畅"))
    )
    return organization_score == 10


def known_domain_fact_conflict(generated):
    body = "\n".join(
        [
            str(generated.get("question") or ""),
            str(generated.get("correct_answer") or ""),
            str(generated.get("reference_answer") or ""),
        ]
    )
    compact = re.sub(r"\s+", "", body).lower()
    if "快速排序" in body:
        if re.search(r"o\(?n(?:\^?3|³)\)?", compact):
            return True
        if re.search(r"快速排序.{0,20}(?:是|属于)(?:一种)?稳定排序", body):
            return True
    if "cache命中" in compact and re.search(r"仍(?:然)?必须访问主存", compact):
        return True
    if "三省六部制" in body and re.search(r"(?:始建|创立|建立)于明朝", body):
        return True
    if re.search(
        r"夷陵之战[^。；\n]{0,50}(?:正式形成|标志着形成)[^。；\n]{0,20}三国鼎立",
        body,
    ):
        return True
    return False
