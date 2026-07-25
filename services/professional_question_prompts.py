import json
import re

from professional_knowledge.builtin_408 import BUILTIN_408_SOURCE_TYPE


CS_408_EXAM_SUBJECTS = ("数据结构", "计算机组成原理", "操作系统", "计算机网络")


def parse_json_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str):
        return []
    text = value.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, list):
        return [str(item).strip() for item in payload if str(item).strip()]
    return [item.strip() for item in re.split(r"[\n,，、;；]+", text) if item.strip()]


def point_exam_subject(point):
    for field in ("exam_subject", "subject", "chapter_name"):
        value = str(point.get(field) or "").strip()
        if value:
            return value
    source_location = str(point.get("source_location") or "")
    for subject in CS_408_EXAM_SUBJECTS:
        if subject in source_location:
            return subject
    return ""


def combined_point_text(point):
    return " ".join(
        str(point.get(field) or "")
        for field in (
            "subject",
            "chapter_name",
            "source_location",
            "knowledge_name",
            "core_definition",
            "content",
            "review_content",
            "example_or_application",
            "exam_question_styles_json",
            "pitfalls_json",
            "keywords_json",
            "related_concepts_json",
            "source_text",
        )
    )


def is_408_knowledge_point(point):
    text = combined_point_text(point)
    if point.get("source_type") == BUILTIN_408_SOURCE_TYPE:
        return True
    if "408" in text or "计算机学科专业基础综合" in text:
        return True
    return any(subject in text for subject in CS_408_EXAM_SUBJECTS)


def detect_408_exam_subject(point):
    explicit = str(point_exam_subject(point) or "")
    for subject in CS_408_EXAM_SUBJECTS:
        if subject in explicit:
            return subject
    text = combined_point_text(point).lower()
    subject_terms = {
        "数据结构": (
            "线性表", "链表", "栈", "队列", "串", "kmp", "树", "二叉树", "森林",
            "图", "aov", "拓扑", "最短路径", "查找", "排序", "哈夫曼", "b树", "b+树",
        ),
        "计算机组成原理": (
            "补码", "浮点", "alu", "cache", "主存", "指令", "寻址", "流水线",
            "总线", "中断", "dma", "i/o", "io", "存储器", "数据通路",
        ),
        "操作系统": (
            "进程", "线程", "调度", "信号量", "pv", "死锁", "银行家", "页面",
            "页表", "tlb", "文件系统", "磁盘", "内存管理", "同步", "互斥",
        ),
        "计算机网络": (
            "tcp", "udp", "ip", "子网", "路由", "cidr", "dns", "http", "crc",
            "以太网", "滑动窗口", "拥塞", "流量控制", "arp", "交换机",
        ),
    }
    scores = {
        subject: sum(1 for term in terms if term.lower() in text)
        for subject, terms in subject_terms.items()
    }
    best_subject, best_score = max(scores.items(), key=lambda item: item[1])
    return best_subject if best_score > 0 else explicit or "408综合"


def select_408_question_blueprints(point, mode, variant=1):
    subject = detect_408_exam_subject(point)
    text = combined_point_text(point).lower()
    common = [
        "题干要给出可推演材料，不能只问定义；至少要求判断、计算、画图、写步骤或比较理由中的两项。",
        "选择题的干扰项要来自真实易错点：适用条件、边界情况、复杂度、状态变化、字段含义或过程顺序。",
        "综合题要拆成 2-4 个小问，并让答案能按得分点批改。",
    ]
    blueprints_by_subject = {
        "数据结构": [
            "给出序列、边集、二叉树遍历序列、查找表或排序初态，让考生推导过程和最终结果。",
            "算法设计题要给输入规模和函数目标，要求写核心思路/伪代码、复杂度、边界条件。",
            "树图题优先考遍历还原、线索/哈夫曼/WPL、拓扑/最短路径/MST、查找判定树、排序稳定性和比较次数。",
        ],
        "计算机组成原理": [
            "给出机器字长、地址位数、Cache 容量/块大小/相联度、指令格式或流水线时序，要求划分字段或计算命中/冲突/性能。",
            "数据表示题要给二进制/十六进制机器数，要求判断补码、溢出、标志位、IEEE754 或大小端/对齐。",
            "CPU/I-O 题要给数据通路、控制信号、中断/DMA 场景，要求说明执行顺序和部件作用。",
        ],
        "操作系统": [
            "给出进程到达/服务时间、资源分配矩阵、页面访问串、页框数或磁盘请求序列，要求调度/死锁/置换/寻道计算。",
            "同步互斥题要给共享变量和约束，要求写信号量初值、P/V 顺序，并解释为什么不死锁不饥饿。",
            "内存与文件题要给页表/TLB/地址结构/inode/目录结构，要求地址转换、缺页判断或空间计算。",
        ],
        "计算机网络": [
            "给出 IP/掩码、路由表、TCP 序号/确认号/窗口、CRC 多项式、帧长度或时延参数，要求计算和解释协议行为。",
            "分层协议题要给通信场景，要求区分网络层/传输层/应用层职责和报文封装变化。",
            "TCP/拥塞控制题要给窗口变化和丢包事件，要求判断流量控制、拥塞控制、可靠传输机制的作用边界。",
        ],
    }
    keyword_blueprints = []
    if any(token in text for token in ("哈夫曼", "huffman", "wpl")):
        keyword_blueprints.append("优先给出一组字符频率，要求构造哈夫曼树、计算 WPL、写编码并与等长编码比较。")
    if any(token in text for token in ("二叉树", "遍历", "线索")):
        keyword_blueprints.append("优先给出先序/中序/后序序列，让考生还原二叉树、写另一种遍历或判断线索指向。")
    if any(token in text for token in ("排序", "快排", "冒泡", "归并", "堆排序")):
        keyword_blueprints.append("优先给出一趟排序前后的序列，让考生判断算法、比较次数、稳定性或最好/最坏情况。")
    if any(token in text for token in ("最短路径", "dijkstra", "floyd", "迪杰斯特拉")):
        keyword_blueprints.append("优先给出带权图的边集或邻接矩阵，要求执行 Dijkstra 或 Floyd，填写距离数组、前驱或最短路径长度。")
    if any(token in text for token in ("cache", "高速缓存", "组相联", "直接映射")):
        keyword_blueprints.append("优先给出地址序列和 Cache 参数，要求拆分 tag/index/offset，判断命中与替换。")
    if any(token in text for token in ("页面", "页表", "tlb", "置换")):
        keyword_blueprints.append("优先给出页面访问串和页框数，要求用 FIFO/LRU/Clock 推导缺页次数和置换过程。")
    if any(token in text for token in ("tcp", "滑动窗口", "拥塞", "确认号")):
        keyword_blueprints.append("优先给出 TCP 段序号、ACK、接收窗口和丢包事件，要求计算可发送段数或解释窗口变化。")
    rotated = keyword_blueprints + blueprints_by_subject.get(subject, []) + common
    if not rotated:
        return common
    start = max(0, int(variant or 1) - 1) % len(rotated)
    return rotated[start:] + rotated[:start]


def format_408_blueprints(point, mode, variant=1):
    if not is_408_knowledge_point(point):
        return ""
    blueprints = select_408_question_blueprints(point, mode, variant=variant)[:5]
    lines = [
        f"408科目判定：{detect_408_exam_subject(point)}",
        "408真题化出题蓝图：",
    ]
    lines.extend(f"- {item}" for item in blueprints)
    lines.extend(
        [
            "硬性质量线：题干必须有具体对象或数据，例如序列、边集、页访问串、Cache参数、IP/TCP字段、资源矩阵、指令/地址格式等；没有这些就不要返回。",
            "不要出“背定义即可”“任意公式套用”“某同学混用概念”这种空题；不要复制教辅原题，只借鉴题型骨架。",
        ]
    )
    return "\n".join(lines)


def compact_question_context(point, mode=None, variant=1):
    name = point.get("knowledge_name") or "当前知识点"
    subject = point.get("subject") or point.get("chapter_name") or ""
    definition = str(point.get("core_definition") or "").strip()
    review_content = str(point.get("review_content") or point.get("content") or "").strip()
    example = str(point.get("example_or_application") or "").strip()
    source_text = str(point.get("source_text") or "").strip()
    keywords = "、".join(parse_json_list(point.get("keywords_json"))[:6])
    exam_styles = "；".join(parse_json_list(point.get("exam_question_styles_json"))[:5])
    pitfalls = "；".join(parse_json_list(point.get("pitfalls_json"))[:5])
    related = "、".join(parse_json_list(point.get("related_concepts_json"))[:8])
    parts = [f"知识点：{name}"]
    if subject:
        parts.append(f"科目：{subject}")
    if keywords:
        parts.append(f"关键词：{keywords}")
    if definition:
        parts.append(f"核心定义：{definition[:360]}")
    if review_content:
        parts.append(f"复习内容：{review_content[:520]}")
    if example:
        parts.append(f"例子/应用：{example[:260]}")
    if exam_styles:
        parts.append(f"常见考法：{exam_styles[:420]}")
    if pitfalls:
        parts.append(f"易错点：{pitfalls[:360]}")
    if related:
        parts.append(f"关联知识点：{related[:260]}")
    if source_text:
        parts.append(f"资料摘录：{source_text[:360]}")
    blueprint_text = format_408_blueprints(point, mode or "quiz", variant=variant)
    if blueprint_text:
        parts.append(blueprint_text)
    return "\n".join(parts)


def build_repair_professional_question_prompt(raw, point, mode, variant):
    return f"""你是考研专业课命题老师。下面这段 AI 输出没有整理成系统需要的题目 JSON，请基于“当前知识点”和原输出，补全为一题可作答、可评分的考研专业课题。

要求：
1. 不要解释，不要展示思考过程，只输出一行 JSON。
2. 字段固定为：{{"question_type":"choice|blank|application|algorithm|concept","question":"题干","options":["A. ...","B. ...","C. ...","D. ..."],"correct_answer":"B","reference_answer":"参考答案","grading_points":["评分点1","评分点2"],"similar_question":"相似题题干"}}
3. 题干必须包含具体条件或明确任务，不能写“围绕某知识点作答”。
4. 如果原输出不足或题目、选项、解析、correct_answer 互相矛盾，就重新核算并纠正答案；不要照抄错误选项。
5. 如果是填空题，correct_answer 必须按空的顺序给出答案，reference_answer 必须逐空解释，每个结论必须与 correct_answer 对应且不得矛盾；如果是综合/算法/概念题，options 可为空数组，correct_answer 可为空字符串。
6. 第 {variant} 次换题，换场景、换数据或换问法。
7. reference_answer 控制在 120-220 字，grading_points 只写 3-5 条短句。
8. 不得在题目或解析中出现“可能”“严格来说”“但答案给出”“存在歧义”“为了符合题目要求”等自我否定语句。

题型：{mode}
当前知识点：
{compact_question_context(point, mode=mode, variant=variant)}

原输出：
{str(raw or '')[:2500]}
"""


def build_minimal_professional_question_prompt(point, mode, variant):
    name = point.get("knowledge_name") or "当前知识点"
    keywords = "、".join(parse_json_list(point.get("keywords_json"))[:4])
    mode_hint = {
        "choice": "单选题，必须有A/B/C/D四个选项和唯一正确答案",
        "blank": "填空题，空格挖在关键条件或步骤上，必须提供 correct_answer",
        "algorithm": "算法题或过程推演题，要给具体输入或条件",
        "concept": "概念辨析题，要比较易混概念",
        "application": "综合应用题，要给具体数据或场景",
        "quiz": "综合应用题，要给具体数据或场景",
    }.get(mode, "综合应用题，要给具体数据或场景")
    return (
        f"你是408命题老师。围绕{name}出一道{mode_hint}。"
        f"关键词：{keywords or name}。第{variant}次换题，请换数据或问法。"
        f"{format_408_blueprints(point, mode, variant=variant)}"
        "只输出一行紧凑JSON，包含question, reference_answer, grading_points。"
        "如果是选择题，再包含options和correct_answer。"
        "如果是填空题，再包含correct_answer，且reference_answer必须逐空解释，每个结论必须与correct_answer对应且不得矛盾。"
        "不要写可能、严格来说、但答案给出、存在歧义等自我否定语句。"
        "reference_answer控制在120-220字，grading_points只写3-5条短句。"
    )


def build_complete_professional_reference_prompt(point, question):
    return (
        "你是408考研阅卷老师。请给下面题目写参考答案和评分点。"
        "只输出JSON，包含reference_answer和grading_points。"
        "参考答案要能用于批改，控制在120-220字；评分点写成3-5条数组。\n"
        f"知识点：{point.get('knowledge_name') or '当前知识点'}\n"
        f"题目：{question}"
    )


def build_professional_question_prompt(point, mode="quiz", variant=1):
    exam_label = "408统考" if is_408_knowledge_point(point) else "该专业课"
    teacher_label = "408考研专业课命题老师" if is_408_knowledge_point(point) else "考研专业课命题老师"
    mode_guidance = {
        "choice": f"生成一道{exam_label}风格单选题，必须有 A/B/C/D 四个选项、唯一正确答案和解析。",
        "blank": "生成一道填空题，空格必须挖在关键条件、算法步骤、字段含义或易混点上；题干用 ______ 标空，correct_answer 按空的顺序给出答案，reference_answer 必须逐空解释，每个结论必须与 correct_answer 对应且不得矛盾；不要考口径不唯一的交换次数。",
        "algorithm": "生成一道算法题或过程推演题，必须给出输入/条件、要求写思路或伪代码，并能评分。",
        "application": "生成一道综合应用题，题干必须有具体条件、任务和可评分步骤。",
        "quiz": "生成一道综合应用题，题干必须有具体条件、任务和可评分步骤。",
        "concept": "生成一道概念辨析题，要求解释核心含义、适用条件和易混点。",
    }.get(mode, "生成一道综合应用题，题干必须具体可作答。")
    return f"""你是{teacher_label}。根据下面知识点出一题，难度中等偏上，目标是接近真实考研专业课试题的考查方式，而不是只改参数的普通练习。
题型要求：{mode_guidance}
先在心里选择一个“真题化出题蓝图”，再输出题目；不要把选择过程写出来。
只输出JSON，包含 question_type、exam_subject、task_archetype、question、options、correct_answer、reference_answer、grading_points、similar_question。
非选择题 options 用空数组；填空题 correct_answer 必填，综合/算法/概念题 correct_answer 可为空。第{variant}次换题，请更换数据或问法。
输出必须是一行紧凑合法 JSON，不要 Markdown，不要解释，不要写思考过程。
question 控制在 100-260 字，必须给出可作答材料和明确任务；reference_answer 控制在 160-320 字，必须包含关键步骤；grading_points 只写 4-6 条短句；similar_question 不超过 100 字。
如果是选择题，四个选项都要具体，不能出现“只背定义即可”“不需要说明过程”这类低质量干扰项。
如果是选择题，必须保证只有一个选项正确；解析中要逐项说明其余三个选项为什么错，不能承认非答案选项也正确。
如果是综合/算法题，要给出序列、边集、表、地址、访问串、资源/进程条件、协议字段等材料之一，并要求计算、判断或推演。
如果是填空题，优先挖稳定性、复杂度、关键条件、字段含义、算法步骤或结论，不要挖依赖具体实现口径且容易歧义的交换次数；解析中不得出现“可能”“严格来说”“但答案给出”“存在歧义”等自我否定语句。
不要照抄教辅或真题原文，只借鉴题型结构和考查层次。

{compact_question_context(point, mode=mode, variant=variant)}
"""
