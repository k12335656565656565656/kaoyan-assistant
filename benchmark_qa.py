"""
考研数学问答系统 — 性能基准测试
独立运行，不依赖 Streamlit，直接调用 API 测量各环节耗时。
"""
import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from services.knowledge_match_service import build_knowledge_index, smart_match_knowledge

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

# ==================== 配置 ====================
API_KEY = os.environ.get("AI_API_KEY", "").strip()
API_BASE = os.environ.get("AI_API_BASE", "https://api.xiaomimimo.com/v1")
MODEL_NAME = os.environ.get("AI_MODEL", "mimo-v2.5")
MEMORY_DB = "data/memory.db"
DATA_DIR = Path("data/corpus")

# ==================== 测试用例 ====================
TEST_CASES = [
    {
        "id": 1,
        "name": "简单概念题",
        "query": "什么是导数？",
        "expect_max": 15,
    },
    {
        "id": 2,
        "name": "计算题",
        "query": "求函数 f(x) = x^3 - 3x + 1 的极值点",
        "expect_max": 25,
    },
    {
        "id": 3,
        "name": "证明题",
        "query": "证明：若 f(x) 在 [a,b] 上连续，在 (a,b) 内可导，且 f(a)=f(b)，则存在 c∈(a,b) 使得 f'(c)=0",
        "expect_max": 30,
    },
    {
        "id": 4,
        "name": "综合应用题",
        "query": "设矩阵 A = [[1,2],[3,4]]，求 A 的特征值和特征向量，并判断 A 是否可对角化",
        "expect_max": 35,
    },
    {
        "id": 5,
        "name": "概率统计题",
        "query": "设 X~N(0,1)，Y=X^2，求 Y 的概率密度函数",
        "expect_max": 30,
    },
]

# ==================== 工具函数 ====================

def read_file(p):
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except:
        try:
            return p.read_text(encoding="gbk", errors="ignore")
        except:
            return ""

def load_corpus():
    docs = []
    if DATA_DIR.exists():
        for f in sorted(DATA_DIR.iterdir()):
            if f.is_file() and f.suffix.lower() in [".txt", ".md"]:
                t = read_file(f)
                if t and len(t) > 50:
                    docs.append({"id": f.name, "text": t})
    return docs

def timed(func, *args, **kwargs):
    """执行函数并返回 (结果, 耗时秒数)"""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed

def call_api(model, messages, max_tokens=1500, temperature=0.3, timeout=60):
    """直接调用 API，返回 (响应文本, 耗时秒数)"""
    data = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        API_BASE + "/chat/completions",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            elapsed = time.perf_counter() - start
            return json.loads(body)["choices"][0]["message"]["content"], elapsed
    except Exception as e:
        elapsed = time.perf_counter() - start
        return f"[ERROR] {e}", elapsed

# ==================== 各环节测试 ====================

def test_search_corpus(query, corpus):
    """测试知识库搜索"""
    start = time.perf_counter()
    query_lower = query.lower()
    results = []
    for doc in corpus:
        text = doc["text"].lower()
        score = sum(text.count(w) for w in query_lower.split() if w)
        if score > 0:
            results.append({"id": doc["id"], "score": score, "text": doc["text"][:500]})
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:3]
    elapsed = time.perf_counter() - start
    return results, elapsed

def test_classify_query(query):
    """测试路由分类 LLM 调用"""
    ROUTER_PROMPT = """判断用户问题属于哪个类别，返回JSON: {"type":"english/politics/math"}"""
    messages = [
        {"role": "system", "content": ROUTER_PROMPT},
        {"role": "user", "content": query},
    ]
    return call_api("mimo-v2.5", messages, max_tokens=30, timeout=20)

def test_main_llm_call(query, context):
    """测试主 LLM 调用（最大瓶颈）"""
    system_prompt = f"""你是考研数学辅导专家。请完成以下任务并用标签输出：

任务1：根据参考资料回答用户问题。使用LaTeX公式（$...$），回答简洁准确。

任务2：判断问题涉及的知识点，输出概念名称（如：导数, 定积分, 矩阵）。

输出格式：
[ANSWER]
（回答）

[KNOWLEDGE]
（概念名，逗号分隔）

参考资料：
{context}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"问题：{query}"},
    ]
    return call_api(MODEL_NAME, messages, max_tokens=2500, timeout=180)

def test_smart_match_knowledge(query, corpus):
    """测试知识匹配（LLM 提取概念 + 本地匹配）"""
    match_start = time.perf_counter()
    idx = build_knowledge_index(corpus)
    matched = smart_match_knowledge(query, index=idx, allow_llm=False)
    match_time = time.perf_counter() - match_start
    return matched[:3], 0.0, match_time

def test_update_memory(kid):
    """测试数据库写入"""
    conn = sqlite3.connect(MEMORY_DB)
    c = conn.cursor()
    c.execute("SELECT times_correct, times_wrong, stability FROM knowledge_mastery WHERE knowledge_id=? AND user_id=1", (kid,))
    row = c.fetchone()
    if row:
        times_correct = row[0] + 1
        times_wrong = row[1]
        stability = row[2] * 1.1
    else:
        times_correct = 1
        times_wrong = 0
        stability = 1.0

    c.execute("DELETE FROM knowledge_mastery WHERE knowledge_id=? AND user_id=1", (kid,))
    c.execute("""INSERT INTO knowledge_mastery
        (knowledge_id, user_id, status, times_correct, times_wrong, stability, last_review, error_type)
        VALUES (?, 1, '学习中', ?, ?, ?, ?, '')""",
        (kid, times_correct, times_wrong, stability, datetime.now()))
    conn.commit()
    conn.close()

# ==================== 主测试流程 ====================

def run_single_test(test_case, corpus):
    """运行单个测试用例，返回详细计时"""
    query = test_case["query"]
    result = {"id": test_case["id"], "name": test_case["name"], "query": query, "steps": []}

    # Step 1: 知识库搜索
    search_results, search_time = test_search_corpus(query, corpus)
    result["steps"].append({"name": "search_corpus", "time": search_time, "detail": f"{len(search_results)} 条结果"})

    # Step 2: 路由分类
    classify_result, classify_time = test_classify_query(query)
    qtype = "math"
    if not classify_result.startswith("[ERROR]"):
        try:
            qtype = json.loads(classify_result).get("type", "math")
        except:
            pass
    result["steps"].append({"name": "classify_query", "time": classify_time, "detail": f"→ {qtype}"})

    # Step 3: 主 LLM 调用
    context = "\n\n".join([f"【{d['id']}】\n{d['text'][:800]}" for d in search_results[:3]]) if search_results else ""
    main_result, main_time = test_main_llm_call(query, context)
    knowledge_list = []
    if not main_result.startswith("[ERROR]"):
        if "[KNOWLEDGE]" in main_result:
            kpart = main_result.split("[KNOWLEDGE]", 1)[-1]
            knowledge_raw = kpart.split("[", 1)[0].strip() if "[" in kpart else kpart.strip()
            knowledge_list = [k.strip() for k in knowledge_raw.split(",") if k.strip()]
    result["steps"].append({"name": "main_llm_call", "time": main_time, "detail": f"model={MODEL_NAME}, 知识点={knowledge_list}"})

    # Step 4: 知识匹配（对主LLM返回的每个知识点）
    total_match_time = 0
    total_concept_time = 0
    total_match_algo_time = 0
    matched_all = []
    for kp in knowledge_list[:3]:
        matched, concept_time, match_algo_time = test_smart_match_knowledge(kp, corpus)
        total_concept_time += concept_time
        total_match_algo_time += match_algo_time
        matched_all.extend(matched)
    total_match_time = total_concept_time + total_match_algo_time
    result["steps"].append({
        "name": "smart_match_knowledge",
        "time": total_match_time,
        "detail": f"LLM提取={total_concept_time:.2f}s, 本地匹配={total_match_algo_time:.2f}s, 匹配={len(matched_all)}个"
    })

    # Step 5: 数据库写入
    db_start = time.perf_counter()
    for kid in matched_all[:3]:
        test_update_memory(kid)
    db_time = time.perf_counter() - db_start
    result["steps"].append({"name": "update_memory", "time": db_time, "detail": f"{len(matched_all[:3])} 条记录"})

    # 总计
    result["total_time"] = sum(s["time"] for s in result["steps"])
    result["expect_max"] = test_case["expect_max"]
    result["within_expect"] = result["total_time"] <= test_case["expect_max"]

    return result

def generate_report(results):
    """生成测试报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("考研数学问答系统 — 性能基准测试报告")
    lines.append("=" * 60)
    lines.append(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"API 地址: {API_BASE}")
    lines.append(f"主模型: {MODEL_NAME}")
    lines.append(f"知识库: {len(load_corpus())} 篇文档")
    lines.append(f"测试用例: {len(results)} 道题")
    lines.append("")

    # 逐题详情
    lines.append("-" * 60)
    lines.append("逐题详情")
    lines.append("-" * 60)
    for r in results:
        status = "PASS" if r["within_expect"] else "SLOW"
        lines.append(f"\n[{status}] #{r['id']} {r['name']} — 总耗时 {r['total_time']:.2f}s (期望 <{r['expect_max']}s)")
        lines.append(f"  问题: {r['query']}")
        for s in r["steps"]:
            pct = s["time"] / r["total_time"] * 100 if r["total_time"] > 0 else 0
            lines.append(f"  ├─ {s['name']:25s} {s['time']:7.2f}s ({pct:4.1f}%)  {s['detail']}")

    # 汇总统计
    lines.append("")
    lines.append("=" * 60)
    lines.append("汇总统计")
    lines.append("=" * 60)

    avg_total = sum(r["total_time"] for r in results) / len(results)
    lines.append(f"平均端到端耗时: {avg_total:.2f}s")

    # 各步骤平均
    step_names = [s["name"] for s in results[0]["steps"]]
    lines.append("")
    lines.append(f"{'步骤':25s} {'平均耗时':>10s} {'占比':>8s} {'瓶颈等级':>10s}")
    lines.append("-" * 60)
    for name in step_names:
        avg = sum(next(s for s in r["steps"] if s["name"] == name)["time"] for r in results) / len(results)
        pct = avg / avg_total * 100 if avg_total > 0 else 0
        level = "🔴 严重" if pct > 40 else "🟡 中等" if pct > 15 else "🟢 正常"
        lines.append(f"{name:25s} {avg:8.2f}s {pct:7.1f}% {level:>10s}")

    # 瓶颈排序
    lines.append("")
    lines.append("瓶颈排序 (按平均耗时):")
    step_avgs = []
    for name in step_names:
        avg = sum(next(s for s in r["steps"] if s["name"] == name)["time"] for r in results) / len(results)
        step_avgs.append((name, avg))
    step_avgs.sort(key=lambda x: x[1], reverse=True)
    for i, (name, avg) in enumerate(step_avgs, 1):
        pct = avg / avg_total * 100 if avg_total > 0 else 0
        lines.append(f"  {i}. {name:25s} {avg:7.2f}s ({pct:.1f}%)")

    # 优化建议
    lines.append("")
    lines.append("=" * 60)
    lines.append("优化建议")
    lines.append("=" * 60)

    top_bottleneck = step_avgs[0][0] if step_avgs else ""
    suggestions = {
        "main_llm_call": [
            "主 LLM 调用是最大瓶颈，建议：",
            "  1. 启用流式响应（SSE），边生成边显示，用户感知延迟降低 80%",
            "  2. 降低 max_tokens (2500→1500)，缩短生成时间",
            "  3. 切换更快的模型（glm-4-flash 代替 glm-4.6）用于简单问题",
        ],
        "classify_query": [
            "路由分类耗时高，建议：",
            "  1. 删除此调用（当前仅用于日志，不影响流程）",
            "  2. 改用本地关键词匹配代替 LLM 分类",
        ],
        "smart_match_knowledge": [
            "知识匹配耗时高，建议：",
            "  1. 合并多个知识点的 LLM 调用为一次批量调用",
            "  2. 用本地关键词匹配代替 LLM 概念提取",
            "  3. 缓存已匹配结果，避免重复调用",
        ],
        "search_corpus": [
            "知识库搜索耗时高，建议：",
            "  1. 引入倒排索引或向量检索代替暴力匹配",
            "  2. 减少 corpus 文档数量或缩短文档长度",
        ],
        "update_memory": [
            "数据库写入耗时高，建议：",
            "  1. 合并多次写入为单次事务",
            "  2. 使用连接池代替每次新建连接",
        ],
    }
    for line in suggestions.get(top_bottleneck, ["无建议"]):
        lines.append(line)

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)

# ==================== 主程序 ====================

if __name__ == "__main__":
    print("考研数学问答系统 — 性能基准测试")
    print("=" * 60)

    # 检查 API Key
    if not API_KEY:
        print("ERROR: 未设置 AI_API_KEY 环境变量")
        exit(1)

    # 加载知识库
    print("加载知识库...")
    corpus = load_corpus()
    print(f"  已加载 {len(corpus)} 篇文档")

    # 初始化数据库
    print("初始化数据库...")
    os.makedirs(os.path.dirname(MEMORY_DB) or "data", exist_ok=True)
    conn = sqlite3.connect(MEMORY_DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS knowledge_mastery (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        knowledge_id TEXT,
        user_id INTEGER,
        status TEXT DEFAULT '学习中',
        times_correct INTEGER DEFAULT 0,
        times_wrong INTEGER DEFAULT 0,
        stability REAL DEFAULT 1.0,
        last_review TIMESTAMP,
        error_type TEXT
    )""")
    conn.commit()
    conn.close()

    # 运行测试
    results = []
    for tc in TEST_CASES:
        print(f"\n测试 #{tc['id']}: {tc['name']} — {tc['query'][:30]}...")
        try:
            result = run_single_test(tc, corpus)
            results.append(result)
            status = "PASS" if result["within_expect"] else "SLOW"
            print(f"  [{status}] 总耗时 {result['total_time']:.2f}s (期望 <{tc['expect_max']}s)")
            for s in result["steps"]:
                print(f"    {s['name']:25s} {s['time']:7.2f}s")
        except Exception as e:
            print(f"  [ERROR] {e}")
            results.append({
                "id": tc["id"], "name": tc["name"], "query": tc["query"],
                "steps": [], "total_time": 0, "expect_max": tc["expect_max"], "within_expect": False,
            })

    # 生成报告
    report = generate_report(results)
    print("\n" + report)

    # 保存报告
    report_file = f"benchmark_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    Path(report_file).write_text(report, encoding="utf-8")
    print(f"\n报告已保存: {report_file}")
