# 考研 RAG 智能助手 —— 完整部署方案

## 一、系统简介

```
┌──────────────────────────────────────────────────────────────┐
│                     考研 RAG 智能助手 v4.0                      │
├──────────────────────────────────────────────────────────────┤
│  多Agent管线 → Router(3分类) → Math/English/Politics Agent     │
│  幻觉检测 → LLM-as-Judge，50题 100% 准确率                      │
│  6个Skill → 格式/内容型，Toggle自由切换                          │
│  多用户 → SHA256登录，SQLite per-user 数据隔离                  │
│  知识库 → 110篇数学大纲对齐文档                                  │
├──────────────────────────────────────────────────────────────┤
│  前端: Streamlit        依赖: 仅 streamlit>=1.28.0             │
│  LLM: AI_API_KEY 环境变量    数据库: SQLite (自动创建)           │
└──────────────────────────────────────────────────────────────┘
```

---

## 二、对方收到的压缩包结构

```
考研RAG-v4.0.zip ──解压后──›
├── app.py                    # 主程序 (1432 行)
├── requirements.txt          # pip install 这个就够了
├── 启动.bat                  # Windows 双击即开
├── 启动考研RAG_Streamlit.bat  # 备用启动（效果相同）
├── SETUP.md                  # 快速入门
├── DEPLOY.md                 # 你正在看的这份详细方案
├── README_Delivery.md        # 完整交付日志（可选）
│
├── data/
│   └── corpus/               # 110 个考研数学知识点 .md 文件
│       001-数列极限的定义与性质.md
│       002-函数极限的概念与性质.md
│       ...
│       110-边际与弹性.md
│
├── skills/                   # 6 个可切换的 Agent Skill
│   ├── math-solver/SKILL.md      # 📐 数学分步解题
│   ├── concept-teacher/SKILL.md  # 💡 概念循序渐进
│   ├── error-analyzer/SKILL.md   # 🔍 错题逐步骤分析
│   ├── bullet-only/SKILL.md      # 📝 仅输出要点
│   ├── qa-mode/SKILL.md          # 💬 QA问答对格式
│   └── formula-only/SKILL.md     # 📐 仅输出公式
│
└── templates/
    └── system_prompt.md       # Prompt 模板（参考）
```

---

## 三、部署步骤（任何人都能操作）

### 第 1 步：装 Python

```bash
python --version
# 必须 ≥ 3.10。如果没有，去 https://python.org 下载安装
```

### 第 2 步：安装依赖

```bash
cd 考研RAG-v4.0          # 进入解压后的目录
pip install -r requirements.txt
```

只有一个包要装：`streamlit>=1.28.0`。网络慢可以换国内源：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 第 3 步：配置 API Key

**Windows**（在命令行执行，或在「系统环境变量」里永久设置）：

```cmd
set AI_API_KEY=sk-your-actual-key-here
```

**Mac / Linux**：

```bash
export AI_API_KEY="sk-your-actual-key-here"
```

**可选**（通常不需要改）：
```bash
set AI_API_BASE=https://aiberm.com/v1    # 默认 API 地址
set AI_MODEL=gpt-4o                       # 默认模型 (还可选 gpt-4o-mini)
```

### 第 4 步：启动

**Windows**：双击 `启动.bat`

**Mac / Linux**：
```bash
streamlit run app.py --server.port 8501 --server.fileWatcherType none
```

浏览器打开 `http://localhost:8501`

### 第 5 步：首次使用

1. 看到登录页 → 点「注册」→ 输入用户名和密码 → 登录
2. 侧边栏「⚙️ 系统状态」点击「🔄 刷新知识库」
3. 确认显示「📁 110 个文档」

---

## 四、功能导览

### 主界面

| 区域 | 功能 |
|------|------|
| **左侧栏** | 模型选择、Skill 开关、知识库刷新、用户登录/退出 |
| **中间问答** | 输入问题 → 自动路由 Agent → 显示回答 + 参考文档 |
| **底部标签** | 知识库浏览、复习挑战、记忆系统、经验本、幻觉检测、系统信息 |

### 提问流程

```
你问："求极限 lim(x→0) sin(x)/x"
  ↓
① Router Agent (gpt-4o-mini) → 判定: math
  ↓
② Math Agent (gpt-4o) → 检索知识库 → LaTeX 分步解题
  ↓
③ 显示回答 + 参考的文档标签
```

```
你问："考研英语大作文怎么写？"
  ↓
① Router → 判定: english
  ↓
② English Agent → 纯 LLM 回答（不检索知识库）
  ↓
③ 显示回答
```

### 可用 Skill（侧边栏开关）

| 开关 | 效果 |
|------|------|
| 📐 数学解题 | 分步骤 + LaTeX 格式 |
| 💡 概念讲解 | 生活化比喻 → 严格定义 → 常见误区 |
| 🔍 错题分析 | 定位分岔点 → 标注错误类型 → 同类题 |
| 📝 纯要点 | 回答 ≤5 行，每行 ≤20 字 |
| 💬 问答 | QA 对格式，段落清晰分隔 |
| 📐 纯公式 | 只输出 $$ 公式，无解释文字 |

> Skill 可以同时开多个，效果叠加。

### 幻觉检测演示

底部「🔍 幻觉检测」标签 → 10 个预置大众话题 → 看 Critic 如何逐条比对上下文。

---

## 五、常见问题排查

### Q1：启动后一片空白或报错 `ModuleNotFoundError`

```bash
pip install streamlit --upgrade
```

### Q2：提示「⚠️ 未设置 API Key」

设置环境变量后，**关掉命令行重新打开**，再启动。

### Q3：知识库显示 0 个或 100 个文档

点侧边栏「🔄 刷新知识库」按钮。

### Q4：问问题没反应

检查 API Key 是否正确（不要有多余空格或引号）。

### Q5：想换模型

侧边栏「选择模型」下拉切换 gpt-4o / gpt-4o-mini。

### Q6：LaTeX 公式显示为 `$x^2$` 原文本

这是旧版 bug，v4.0 已修复。如果还有问题，检查 Streamlit 版本 ≥ 1.28。

### Q7：多人同时用

每人注册自己的账号，数据自动隔离。数据库文件 `data/memory.db` 首次运行自动创建。

### Q8：想添加新知识

往 `data/corpus/` 丢 `.md` 文件，格式参考已有文件，然后点「🔄 刷新知识库」。

---

## 六、可选：持久化 API Key（Windows）

如果不想每次开命令行手动 `set`：

1. 右键「此电脑」→ 属性 → 高级系统设置 → 环境变量
2. 新建用户变量：`AI_API_KEY` = `sk-your-key`
3. 确定后重启命令行

---

## 七、可选：局域网多人使用

```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

同 WiFi 下的其他人访问 `http://你的IP:8501`（你的 IP 在启动日志里会显示）。

---

## 八、打包给别人

直接 zip 以下内容：

```
app.py
requirements.txt
启动.bat
启动考研RAG_Streamlit.bat
SETUP.md
DEPLOY.md
data/corpus/          # 110 个 .md 文件
skills/               # 6 个子目录
templates/            # 1 个文件
```

> 不要打包 `data/memory.db`、`agent_experience*.md`、`test_data/`、`benchmarks/`、各种 `*_test.py`、`*.py`（除了 app.py）。

---

*版本: v4.0 | 更新: 2026-05-16*
