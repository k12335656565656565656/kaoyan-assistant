# 专业知识库模块 — 外包开发需求文档

## 一、项目概述

### 1.1 项目背景

本项目是一个**考研学习助手**的专业知识库模块，旨在帮助用户建立自己的私有知识库。用户可以上传专业课相关的 PDF/图片资料，系统通过 AI 自动识别内容、提取知识点，并支持复习和 AI 发散性内容生成。

### 1.2 核心价值

- **自动化知识提取**：AI 自动从 PDF/图片中识别和提取知识点
- **私有知识库**：每个用户拥有独立的知识库空间
- **智能复习**：基于遗忘曲线的复习提醒 + AI 生成发散性内容
- **错题管理**：错题自动关联知识点，支持针对性复习

### 1.3 目标用户

考研学生、需要整理专业课资料的学生、需要建立个人知识库的学习者。

---

## 二、功能需求

### 2.1 用户上传与 OCR 识别

#### 功能描述
用户上传专业课相关的 PDF 或图片文件，系统自动识别其中的文字内容。

#### 具体要求

| 要求 | 说明 |
|------|------|
| 支持格式 | PDF、PNG、JPG、JPEG、TXT |
| PDF 处理 | 自动分页识别，最多支持 50 页 |
| 中文 OCR | 支持中文文字识别，包括公式、图表 |
| 识别方式 | 优先使用本地 OCR 服务（umi-ocr），备选云端 OCR |
| 结果预览 | 识别完成后显示预览，用户可编辑修正 |
| 文件大小 | 单文件最大 20MB |

#### 交互流程

```
用户上传文件 → 系统保存文件 → 调用 OCR 识别 → 显示识别结果预览
                                                      ↓
                                              用户编辑修正（可选）
                                                      ↓
                                              确认后提取知识点
```

### 2.2 AI 知识点提取

#### 功能描述
从 OCR 识别的文本中，利用 AI 自动提取结构化的知识点。

#### 具体要求

| 要求 | 说明 |
|------|------|
| 提取方式 | 调用大语言模型（GLM-4 系列）进行知识点提取 |
| 输出格式 | 结构化知识点列表，每个知识点包含名称和核心概念 |
| 手动编辑 | 用户可修正 AI 提取结果 |
| 知识关联 | 自动识别知识点之间的关联关系 |

#### 知识点结构

```json
{
  "knowledge_name": "知识点名称",
  "content": "核心概念描述（1-2句话）",
  "subject": "所属学科",
  "chapter_name": "所属章节",
  "related_knowledge": ["相关知识点1", "相关知识点2"]
}
```

### 2.3 私有知识库

#### 功能描述
用户拥有独立的知识库空间，按学科和章节组织知识点。

#### 具体要求

| 要求 | 说明 |
|------|------|
| 学科分类 | 支持自定义学科（如：数据结构、计算机网络、操作系统等） |
| 章节组织 | 每个学科下按章节组织知识点 |
| 搜索功能 | 支持关键词搜索知识点 |
| 筛选功能 | 按学科、章节、掌握程度筛选 |
| 知识图谱 | 可视化知识点之间的关联关系（可选） |

#### 页面布局

```
┌─────────────────────────────────────────────────────────┐
│  📚 专业知识库                                           │
├─────────────────────────────────────────────────────────┤
│  [学科选择] [搜索框] [筛选按钮]                           │
├─────────────────────────────────────────────────────────┤
│  📖 章节1                                               │
│    ├─ 📌 知识点1 (已掌握 ✓)                              │
│    ├─ 📌 知识点2 (学习中 ⟳)                              │
│    └─ 📌 知识点3 (未学习 ○)                              │
│  📖 章节2                                               │
│    └─ ...                                               │
└─────────────────────────────────────────────────────────┘
```

### 2.4 复习系统

#### 功能描述
基于遗忘曲线的智能复习系统，每个知识点支持复习状态管理和 AI 发散性内容生成。

#### 具体要求

| 要求 | 说明 |
|------|------|
| 复习提醒 | 基于艾宾浩斯遗忘曲线，自动提醒待复习知识点 |
| 掌握程度 | 支持标记：未学习、学习中、已掌握 |
| AI 发散 | 每个知识点支持 AI 生成发散性内容 |
| 复习记录 | 记录每次复习时间和结果 |

#### AI 发散内容类型

1. **相关题目**：基于知识点生成练习题
2. **应用场景**：知识点在实际中的应用
3. **深入解释**：更详细的概念解析
4. **关联知识**：与该知识点相关的其他知识

#### 复习流程

```
系统提醒待复习 → 用户选择知识点 → 显示知识点详情
                                      ↓
                              [标记已掌握] [需复习] [AI发散]
                                      ↓
                              AI 生成发散内容 → 用户学习
```

### 2.5 错题本

#### 功能描述
管理用户在学习过程中遇到的错题，自动关联知识点。

#### 具体要求

| 要求 | 说明 |
|------|------|
| 添加方式 | 手动添加、AI 出题后自动添加 |
| 错题信息 | 题目、用户答案、正确答案、解析 |
| 知识关联 | 自动关联到对应知识点 |
| 错题统计 | 统计错误次数、易错知识点 |
| 状态管理 | 标记已掌握、重新学习 |

### 2.6 AI 出题

#### 功能描述
基于用户知识库中的知识点，AI 自动生成练习题。

#### 具体要求

| 要求 | 说明 |
|------|------|
| 出题方式 | 选择知识点后自动生成 |
| 题型支持 | 选择题、填空题、简答题 |
| 难度控制 | 支持设置难度等级 |
| 答题交互 | 用户答题后显示正确答案和解析 |
| 错题自动添加 | 答错的题目自动添加到错题本 |

---

## 三、技术架构

### 3.1 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 前端框架 | Streamlit | Python Web 框架，快速开发 |
| 数据库 | SQLite | 轻量级，无需额外部署 |
| AI 模型 | GLM-4 系列 | 智谱 AI 提供的大语言模型 |
| OCR 服务 | umi-ocr / PyMuPDF | 本地 OCR 服务 + PDF 解析库 |
| 文件存储 | 本地文件系统 | 上传文件保存在 data/ 目录 |

### 3.2 目录结构

```
knowledge-base-module/
├── README.md                    # 项目介绍
├── SETUP.md                     # 部署指南
├── requirements.txt             # Python 依赖
├── app.py                       # 主程序入口
├── knowledge_base.py            # 核心模块
├── data/
│   ├── corpus/                  # 示例知识库文档
│   ├── user_materials/          # 用户上传的资料
│   └── memory.db                # SQLite 数据库（自动创建）
└── skills/                      # AI 技能定义
```

### 3.3 数据库设计

#### 表结构

```sql
-- 1. 上传资料表
CREATE TABLE user_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    filename TEXT NOT NULL,
    chapter_name TEXT,
    file_path TEXT,
    file_type TEXT,
    processing_status TEXT DEFAULT 'pending',  -- pending/processing/done/error
    knowledge_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 知识点表
CREATE TABLE user_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    material_id INTEGER,
    subject TEXT NOT NULL,
    chapter_name TEXT,
    knowledge_name TEXT NOT NULL,
    content TEXT,
    mastery_level INTEGER DEFAULT 0,  -- 0=未学习, 1=学习中, 2=已掌握
    last_reviewed TIMESTAMP,
    next_review TIMESTAMP,
    review_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 错题表
CREATE TABLE user_wrong_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    knowledge_id INTEGER,
    subject TEXT NOT NULL,
    chapter_name TEXT,
    question TEXT NOT NULL,
    user_answer TEXT,
    correct_answer TEXT,
    explanation TEXT,
    error_count INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',  -- active/mastered
    last_reviewed TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. 复习记录表
CREATE TABLE user_review_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    knowledge_id INTEGER NOT NULL,
    review_date TEXT NOT NULL,
    mastered INTEGER DEFAULT 0,  -- 0=未掌握, 1=已掌握
    review_duration INTEGER,     -- 复习时长（秒）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 索引优化

```sql
CREATE INDEX idx_materials_user ON user_materials(user_id, subject);
CREATE INDEX idx_knowledge_user ON user_knowledge(user_id, subject);
CREATE INDEX idx_knowledge_mastery ON user_knowledge(user_id, mastery_level);
CREATE INDEX idx_wrong_user ON user_wrong_questions(user_id, subject);
CREATE INDEX idx_wrong_status ON user_wrong_questions(user_id, status);
CREATE INDEX idx_review_knowledge ON user_review_records(knowledge_id);
```

### 3.4 API 配置

```python
import os

# AI API 配置
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_API_BASE = os.environ.get("AI_API_BASE", "https://api.z.ai/api/coding/paas/v4")
AI_MODEL = os.environ.get("AI_MODEL", "glm-4.6")

# OCR 配置
UMI_OCR_URL = os.environ.get("UMI_OCR_URL", "http://localhost:1224")

# 数据库配置
MEMORY_DB = os.environ.get("MEMORY_DB", "data/memory.db")
```

---

## 四、UI 设计规范

### 4.1 设计风格

- **主色调**：Claude Orange `#D77757`（温暖的橙色）
- **辅助色**：Claude Blue `#5769F7`
- **背景色**：浅灰色 `#f8f9fa`
- **圆角**：12px
- **阴影**：`0 2px 12px rgba(0,0,0,0.06)`

### 4.2 主页面布局

```
┌─────────────────────────────────────────────────────────────┐
│  📚 专业知识库                                               │
│  上传资料 · OCR识别 · 错题本 · 复习本 · AI出题               │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                       │
│  │ 知识点   │ │ 待复习   │ │ 学科数   │                       │
│  │   128   │ │    15   │ │    5    │                       │
│  └─────────┘ └─────────┘ └─────────┘                       │
├─────────────────────────────────────────────────────────────┤
│  [📖 知识库] [📝 错题本] [📚 复习本] [🎲 AI出题]             │
├─────────────────────────────────────────────────────────────┤
│  ... Tab 内容 ...                                           │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 响应式设计要求

| 屏幕尺寸 | 断点 | 布局调整 |
|----------|------|----------|
| 桌面 | >1024px | 正常布局，3列指标卡片 |
| 平板 | 768-1024px | 2列指标卡片，表格响应式 |
| 手机 | <768px | 单列布局，指标卡片堆叠 |
| 小屏手机 | <480px | 紧凑布局，减小内边距 |

### 4.4 CSS 媒体查询示例

```css
@media (max-width: 768px) {
    .main-title { padding: 1rem !important; }
    .main-title h1 { font-size: 1.3rem !important; }
    .metric-value { font-size: 1.1rem !important; }
}

@media (max-width: 480px) {
    .main-title { padding: 0.8rem !important; }
    .main-title h1 { font-size: 1.1rem !important; }
}
```

---

## 五、部署方案

### 5.1 环境要求

- **Python**: 3.10+
- **操作系统**: Windows / Linux / macOS
- **内存**: 2GB+
- **磁盘**: 1GB+（用于存储用户资料）

### 5.2 依赖安装

```txt
# requirements.txt
streamlit>=1.28.0
PyMuPDF>=1.23.0
requests>=2.28.0
```

安装命令：
```bash
pip install -r requirements.txt
```

### 5.3 配置环境变量

**Windows (PowerShell)**:
```powershell
$env:AI_API_KEY="your-api-key-here"
$env:AI_API_BASE="https://api.z.ai/api/coding/paas/v4"
$env:AI_MODEL="glm-4.6"
```

**Linux / macOS**:
```bash
export AI_API_KEY="your-api-key-here"
export AI_API_BASE="https://api.z.ai/api/coding/paas/v4"
export AI_MODEL="glm-4.6"
```

### 5.4 启动服务

```bash
# 开发模式
streamlit run app.py --server.port 8501

# 生产模式（后台运行）
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 > app.log 2>&1 &
```

### 5.5 访问地址

- 本地访问：`http://localhost:8501`
- 局域网访问：`http://<服务器IP>:8501`

---

## 六、交付标准

### 6.1 代码质量

| 标准 | 要求 |
|------|------|
| 代码规范 | 符合 PEP 8 规范，无硬编码 API Key |
| 错误处理 | 完善的异常处理，用户友好的错误提示 |
| 代码注释 | 关键函数有清晰的中文注释 |
| 模块化 | 功能模块职责单一，易于维护 |

### 6.2 功能完整性

- [ ] 用户登录/注册（或与主系统集成）
- [ ] PDF/图片上传功能
- [ ] OCR 识别功能（支持中文）
- [ ] AI 知识点提取功能
- [ ] 知识点列表展示
- [ ] 复习系统（掌握程度标记）
- [ ] AI 发散内容生成
- [ ] 错题本功能
- [ ] AI 出题功能
- [ ] 响应式 UI（桌面/平板/手机）

### 6.3 文档完整性

- [ ] README.md：项目介绍、功能说明
- [ ] SETUP.md：部署指南、配置说明
- [ ] 代码注释：关键函数有中文注释
- [ ] API 文档：接口说明（如有）

### 6.4 测试要求

- [ ] 单元测试：核心函数测试
- [ ] 集成测试：端到端流程测试
- [ ] 兼容性测试：不同浏览器测试
- [ ] 性能测试：大文件处理测试

---

## 七、现有代码参考

### 7.1 现有模块位置

```
C:\Users\H.D.B\Desktop\claude-code-main\knowledge_base.py
```

### 7.2 现有功能清单

| 功能 | 状态 | 说明 |
|------|------|------|
| 数据库初始化 | ✅ 已完成 | 4张表结构 |
| LLM API 调用 | ✅ 已完成 | 支持 GLM-4 系列 |
| PDF 文本提取 | ✅ 已完成 | PyMuPDF |
| OCR 识别 | ✅ 已完成 | umi-ocr + 多模态 AI |
| 知识点提取 | ✅ 已完成 | AI 自动提取 |
| 知识点存储 | ✅ 已完成 | SQLite |
| 错题本 | ✅ 已完成 | 增删改查 |
| 复习本 | ⚠️ 部分完成 | 缺少遗忘曲线 |
| AI 出题 | ⚠️ 部分完成 | 缺少答题交互 |
| 响应式 UI | ⚠️ 部分完成 | 需要优化 |

### 7.3 需要改进的地方

1. **API Key 管理**：移除硬编码，改用环境变量
2. **数据库连接**：使用连接池或上下文管理器
3. **错误处理**：完善异常处理，添加日志记录
4. **复习算法**：实现基于遗忘曲线的复习提醒
5. **AI 发散**：每个知识点支持 AI 生成发散内容
6. **答题交互**：AI 出题后支持答题和自动批改
7. **响应式 UI**：优化移动端显示效果

---

## 八、验收流程

### 8.1 验收节点

| 阶段 | 时间 | 交付物 |
|------|------|--------|
| 需求确认 | 第 1 天 | 需求文档确认签字 |
| 设计评审 | 第 3 天 | 技术方案、UI 设计稿 |
| 开发完成 | 第 10 天 | 功能代码、单元测试 |
| 测试完成 | 第 12 天 | 测试报告、bug 修复 |
| 最终交付 | 第 14 天 | 完整代码、文档、部署包 |

### 8.2 验收标准

1. **功能验收**：所有功能需求点通过测试
2. **性能验收**：页面加载 <3s，OCR 识别 <30s
3. **兼容验收**：Chrome、Firefox、Safari 浏览器正常运行
4. **文档验收**：文档齐全，可按文档完成部署

### 8.3 验收测试用例

```
测试用例 1：上传 PDF 并提取知识点
- 步骤：上传一个 10 页的 PDF 文件
- 预期：成功识别文字，提取 10+ 个知识点

测试用例 2：复习系统
- 步骤：标记一个知识点为"需复习"，查看复习提醒
- 预期：该知识点出现在待复习列表

测试用例 3：AI 出题
- 步骤：选择一个知识点，点击"生成练习题"
- 预期：生成 1 道选择题，包含选项和解析

测试用例 4：响应式布局
- 步骤：在手机浏览器中访问系统
- 预期：页面正常显示，无横向滚动条
```

---

## 九、联系方式

如有疑问，请联系：

- **项目负责人**：[待填写]
- **技术对接人**：[待填写]
- **联系方式**：[待填写]

---

## 附录 A：API 接口参考

### 智谱 AI API

**接口地址**：`https://api.z.ai/api/coding/paas/v4/chat/completions`

**请求示例**：
```json
{
    "model": "glm-4-flash",
    "messages": [
        {"role": "user", "content": "请从以下内容中提取知识点..."}
    ],
    "max_tokens": 1500,
    "temperature": 0.3
}
```

**响应示例**：
```json
{
    "choices": [
        {
            "message": {
                "content": "知识点1: 栈的定义 - 栈是一种后进先出..."
            }
        }
    ]
}
```

### umi-ocr API

**接口地址**：`http://localhost:1224/api/ocr`

**请求示例**：
```json
{
    "base64": "iVBORw0KGgo..."
}
```

**响应示例**：
```json
{
    "text": "识别出的文字内容..."
}
```

---

## 附录 B：参考资源

- [Streamlit 官方文档](https://docs.streamlit.io/)
- [PyMuPDF 文档](https://pymupdf.readthedocs.io/)
- [智谱 AI 开放平台](https://open.bigmodel.cn/)
- [umi-ocr 项目](https://github.com/hiroi-sora/Umi-OCR)
