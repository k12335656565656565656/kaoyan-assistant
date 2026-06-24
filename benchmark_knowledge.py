"""知识点归纳基准测试 — 50题"""
import json
import sys
import io
import time
from pathlib import Path
from dotenv import load_dotenv
from services.knowledge_match_service import build_knowledge_index, smart_match_knowledge

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

load_dotenv()

def load_corpus_ids():
    ids = []
    for f in sorted(Path("data/corpus").iterdir()):
        if f.suffix == ".md":
            ids.append(f.name)
    return ids

# 50题 — 覆盖不同用户画像
tests = [
    # 基础概念（新手型用户）
    ("导数到底怎么理解啊", ["004-导数的定义与几何意义.md"]),
    ("极限是啥，大一学的忘了", ["001-数列极限的定义与性质.md", "002-函数极限的概念与计算.md"]),
    ("积分和导数啥关系", ["010-不定积分的概念与性质.md", "012-定积分的定义与性质.md"]),
    ("矩阵是个啥，完全没概念", ["023-矩阵的概念与运算.md"]),
    ("概率里面的随机变量是啥意思", ["045-随机变量及其分布.md", "078-随机变量及其分布.md"]),
    ("连续和可导有区别吗", ["003-函数的连续性与间断点.md", "004-导数的定义与几何意义.md"]),
    ("什么是级数？能通俗讲讲吗", ["067-无穷级数.md"]),
    ("方差的公式是什么", ["098-二次型标准化.md"]),
    ("正态分布有什么特点", ["047-常见连续分布.md"]),
    
    # 刷题型
    ("求极限 lim(x→0)(e^x-1)/x = ?", ["002-函数极限的概念与计算.md"]),
    ("求导数 f(x)=ln(1+x^2) 的导数", ["005-导数的计算法则.md"]),
    ("计算定积分 ∫₀¹ x^2 dx", ["012-定积分的定义与性质.md"]),
    ("求矩阵 A=[[2,1],[1,2]] 的特征值", ["031-特征值与特征向量.md"]),
    ("求解方程组 x+y=3, 2x-y=0", ["030-线性方程组.md"]),
    ("计算二重积分 ∬D xy dxdy", ["065-二重积分与三重积分.md"]),
    ("用洛必达法则求极限", ["007-洛必达法则.md"]),
    ("泰勒展开 sin(x) 到三阶", ["013-泰勒公式.md"]),
    ("求幂级数的收敛半径", ["087-幂级数展开与求和.md"]),
    ("证明函数单调性", ["008-函数的单调性与极值.md"]),
    
    # 考试策略型
    ("特征值和特征向量在考研里考得多吗", ["031-特征值与特征向量.md"]),
    ("线性代数哪些章节最重要", ["070-线性代数综合一.md", "071-线性代数综合二.md"]),
    ("考研数学一需要掌握哪些级数知识", ["067-无穷级数.md", "086-常数项级数审敛.md"]),
    ("概率论有哪些必背公式", ["052-随机变量的数字特征.md", "077-全概率公式与贝叶斯公式.md"]),
    ("多元函数微分考什么", ["064-多元函数微分学.md"]),
    ("常微分方程到底考哪些内容", ["066-常微分方程总结.md"]),
    ("假设检验很难，怎么学", ["108-假设检验详解.md"]),
    
    # 应用联想型
    ("矩阵对角化在实际中有什么用", ["034-矩阵的对角化.md"]),
    ("曲率这个概念在哪里会用到", ["101-曲率与曲率圆.md"]),
    ("傅里叶级数在信号处理中怎么用", ["104-傅里叶级数.md"]),
    ("协方差和相关系数在金融中应用", ["073-协方差与相关系数.md"]),
    ("格林公式和高斯公式什么关系", ["106-格林高斯斯托克斯公式.md"]),
    ("微分方程能描述什么现实问题", ["016-一阶微分方程.md", "066-常微分方程总结.md"]),
    ("参数估计在机器学习里怎么用", ["059-参数估计.md"]),
    
    # 概念对比型
    ("矩阵的秩和行列式有什么区别", ["026-矩阵的秩.md", "021-行列式的定义与性质.md"]),
    ("二次型标准化和正定有什么关系", ["098-二次型标准化.md", "099-二次型的正定性.md"]),
    ("无穷小量和无穷大量怎么区分", ["003-函数的连续性与间断点.md"]),
    ("定积分和不定积分什么关系", ["012-定积分的定义与性质.md", "010-不定积分的概念与性质.md"]),
    ("分布函数和密度函数怎么区分", ["045-随机变量及其分布.md"]),
    ("点估计和区间估计到底有什么区别", ["059-参数估计.md"]),
    ("线性相关和线性无关怎么判断", ["092-向量组的线性相关性.md", "028-向量组的线性相关性.md"]),
    ("极大无关组和秩有啥关系", ["029-向量组的秩.md", "027-向量的概念与运算.md"]),
    
    # 高级难点型
    ("什么是向量组的极大线性无关组", ["029-向量组的秩.md"]),
    ("函数展开成傅里叶级数怎么做", ["104-傅里叶级数.md"]),
    ("空间曲面和空间曲线方程怎么求", ["103-空间曲面与空间曲线.md"]),
    ("方向导数和梯度到底干嘛用的", ["102-方向导数与梯度.md"]),
    ("欧拉方程怎么转化成常系数微分方程", ["105-欧拉方程.md"]),
    ("基变换和过渡矩阵是啥东西", ["109-基变换与过渡矩阵.md"]),
    ("边际和弹性在经济中怎么理解", ["110-边际与弹性.md"]),
    ("差分方程在考研里重要吗", ["107-差分方程基础.md"]),
]

corpus_ids = load_corpus_ids()
corpus = []
for f in sorted(Path("data/corpus").iterdir()):
    if f.suffix == ".md":
        corpus.append({"id": f.name, "text": f.read_text(encoding="utf-8", errors="ignore")})
index = build_knowledge_index(corpus)
results = []
print(f"{'ID':<5} {'问题':<32} {'归一化后文档':<42} {'预期关键词':<18} {'结果':>4}")
print("-" * 110)

for i, (query, expected) in enumerate(tests, 1):
    validated = smart_match_knowledge(query, index=index, allow_llm=False)
    
    passed = any(e in " ".join(validated) for e in expected)
    results.append({"id": i, "query": query, "validated": validated, "expected": expected, "passed": passed})
    
    val_s = ",".join([v[:22] for v in validated])[:40]
    exp_s = expected[0][:16] if expected else "?"
    print(f"T{i:<4} {query[:30]:<32} {val_s:<42} {exp_s:<18} {'PASS' if passed else 'FAIL':>4}")
    time.sleep(0.15)

passed = sum(1 for r in results if r["passed"])
pct = passed/len(tests)*100
print(f"\n{'='*60}")
print(f"准确率: {passed}/50 ({pct:.0f}%)")

# 分类统计
cats = {"基础概念": (0,0), "刷题": (0,0), "考试策略": (0,0), "应用联想": (0,0), "概念对比": (0,0), "高级难点": (0,0)}
cat_ranges = [(0,9),(9,19),(19,27),(27,34),(34,42),(42,50)]
cat_names = ["基础概念", "刷题", "考试策略", "应用联想", "概念对比", "高级难点"]
for (s,e), name in zip(cat_ranges, cat_names):
    sub = results[s:e]
    correct = sum(1 for r in sub if r["passed"])
    cats[name] = (correct, len(sub))
    print(f"  {name}: {correct}/{len(sub)} ({correct/len(sub)*100:.0f}%)")

# 保存
report = {"tests": results, "accuracy": f"{passed}/50", "by_category": {k: f"{v[0]}/{v[1]}" for k,v in cats.items()}}
Path("benchmarks/benchmark_knowledge_50.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n报告: benchmarks/benchmark_knowledge_50.json")
