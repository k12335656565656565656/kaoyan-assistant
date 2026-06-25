# CLAUDE.md

## 项目概述

考研学习助手 — Streamlit 多用户 Web 应用。提供考研数学问答、英语专家、打卡督学、学习资料生成、费曼学习法、知识库等功能。API 使用小米 MiMo v2.5。

## 技术栈

- **Python** 3.13 (`C:\Users\H.D.B\AppData\Local\Python\bin\python.exe`)
- **框架**: Streamlit (无前后端分离，纯 `app.py`)
- **数据库**: SQLite `data/memory.db`（多用户隔离，`user_id` 区分）
- **API**: 小米 MiMo v2.5，endpoint `https://api.xiaomimimo.com/v1`，模型 `mimo-v2.5`
- **数学渲染**: KaTeX（本地 `file:///` 绝对路径，3 个文件在 `data/katex/`）
- **文档生成**: Pandoc（`python-docx` + `lxml`，模板 `data/reference/template.docx`）
- **部署**: 腾讯云 Ubuntu 服务器，`pack.py` 打包 ZIP

## 文件职责

| 文件 | 说明 |
|------|------|
| `app.py` | 主程序（~4700 行），包含全部页面、API 调用、CSS、数据库操作 |
| `knowledge_base.py` | 专业知识库模块（独立部署包，含 OCR、向量检索、出题） |
| `admin.py` | 管理员面板（用户管理、数据统计） |
| `recommend.py` | 同事 PR — 学习资料推荐模块 |
| `kaoyan_predict.py` | 高校热度预测引擎（Node.js 子进程） |
| `pack.py` | 打包脚本 → `KaoyanRAG-v4.2.zip`（含 corpus/skills/katex/predict） |
| `copy_to_git.py` | 从 dev 目录同步到 `C:\Users\H.D.B\Desktop\git\`，用于 GitHub 发布 |

## 关键架构

### 页面路由

通过 `st.session_state.page` 控制，各页面用 `if st.session_state.page == "xxx":` 守卫。

```
hub       → 备考看板（默认首页，快速入口卡片）
popularity→ 高校热度查询
english   → 考研英语专家（作文批改/长难句/翻译/单词）
checkin   → 打卡督学（打卡/日记/学习计划/番茄计时/学习画像）
material  → 学习资料（AI 生成习题册、DOCX 导出）
suggest   → 提建议
```

导航模式：Hub 页面的卡片按钮设置 `st.session_state.page` + `st.rerun()`。每页有「← 返回首页」按钮回到 hub。

### MiMo API 调用

- API Key 硬编码在 `app.py:38`
- 模型 `mimo-v2.5`（思维链模型，`content` 常为空，内容在 `reasoning_content` 字段）
- 统一使用 `_extract_content()` helper 读取回复（优先 `content`，空时 fallback `reasoning_content`）
- 流式调用：`stream=True`，yield `textContent`，打字效果每字 20-30ms
- `max_tokens` 默认 1500
- 所有 API 调用走 `call_llm_api(prompt, model="mimo-v2.5")` 或 `run_pipeline()` generator

### UI 设计系统（Indigo 主题）

```css
主色: #4f46e5 → #6366f1 (靛蓝)
背景: #f1f5f9
卡片: 毛玻璃渐变 + backdrop-filter blur + 圆角 20px
学习卡片: #fff7ed (学习中) / #f0fdf4 (已掌握)
参考标签: #eef2ff, 文字 #4f46e5
侧边栏: 毛玻璃渐变背景 + 2 分组标签 + 7 Emoji 按钮 + 流光边框活跃项
Hub: Hero 渐隐标题 + Flow 心流指标 + 4 SVG feature cards + 2 wide cards
Feature Cards: SVG 图标 + 玻璃材质 + 呼吸动画 + <a> 整卡可点
页面过渡: breatheIn 模糊→清晰 + cardReveal 错开浮现 + sidebarSlideIn
```

### 侧边栏

- **导航方式**: Emoji + `st.button`（稳定可靠，不用 `<a>` 或 SVG mask）
- **分组**: `📚 核心功能` (备考看板/数学问答/英语专家/打卡督学) + `🔧 辅助工具` (高校热度/学习资料/提建议)
- **效果**: 毛玻璃背景、活跃项渐变流光边框、按钮弹性按压动画、用户卡片统计真实打卡天数
- **品牌区**: 书本 SVG + 渐变文字标题

### Hub 卡片

- **图标**: 6 张卡片全部 Feather 风格 inline SVG（四宫格/柱状图/书本/聊天气泡/文档/对勾）
- **点击**: `<a href="?p=xxx">` query param 路由，整卡可点
- **效果**: 玻璃材质 + 呼吸动画 cardBreathe + hover 上浮 + 光晕扩散

### 数据库

`data/memory.db` — SQLite，多用户隔离（所有查询带 `WHERE user_id=?`）。

主要表：`users`, `login_tokens`, `knowledge_mastery`, `qa_history`, `checkin_records`, `checkin_plans`, `checkin_diary`, `feynman_history` 等。

### KaTeX 渲染

- CDN fallback + 本地 `file:///` 绝对路径（3 文件：`katex.min.css`, `katex.min.js`, `auto-render.min.js`）
- `_fix_latex()` 预处理 LaTeX 字符串
- `_collapse_math()` 合并相邻 math 块
- `_escape_md()` 转义 Markdown 特殊字符
- `_katex_refresh()` 用 JavaScript 注入触发重新渲染

## API 配置

```python
API_KEY = "sk-c4f69ncnuomnc8pprclmhlasndea7tdjvxeo49jno3bzxpa6"
API_BASE = "https://api.xiaomimimo.com/v1"
MODEL = "mimo-v2.5"
MAX_TOKENS = 1500
```

## 登录系统

- Cookie 持久化（`extra-streamlit-components` CookieManager）
- `@st.cache_resource` + monkey-patch `check_cache_replay_rules` 避免 cookie 重复读写
- 登录/注册表单在文件开头，未登录时 `st.stop()`
- Token 有效期 30 天

## 部署

```bash
# 本地打包
python pack.py  # → KaoyanRAG-v4.2.zip (~200 文件, ~4MB)

# 服务器部署
scp KaoyanRAG-v4.2.zip ubuntu@111.229.102.178:/home/ubuntu/
ssh ubuntu@111.229.102.178
cd /home/ubuntu && python3 -c "import zipfile; zipfile.ZipFile('KaoyanRAG-v4.2.zip').extractall('kaoyan/')"
source /home/ubuntu/kaoyan/venv/bin/activate
pip install python-docx lxml -q
# 确保 Pandoc 已安装：apt install pandoc -y
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true > streamlit.log 2>&1 &
```

## 已知约束

- **页面标题保持「考研学习助手」不改**
- **不引入新的 pip 依赖**，保持最小依赖集
- MiMo 思维链模型：`content` 为空时用 `reasoning_content`，全局用 `_extract_content()` 处理
- `python-dotenv` 已移除，API Key 直接硬编码（避免服务器环境变量问题）
- 不 mock 纯函数模块，不引入 `as any` 到生产代码
- 打包时需确认 `data/katex/`、`data/reference/template.docx`、`templates/` 均被包含

## 最近改动

- **2026-06-19 出题按钮增加 AI 思考状态提示**:
  - 数学问答知识库出题按钮点击后，原位显示灰蓝色旋转提示"AI 正在出题思考中..."
  - 经历 4 次迭代：st.spinner（页面顶部不可见）→ st.info（太重）→ st.progress（太蓝）→ 自定义 HTML spinner（#94a3b8）
  - 仅改数学问答知识库 Tab 一处（4374行），独立知识库页两处保持 st.progress

- **2026-06-19 同步橘色原版缺失的 Skills**:
  - 从 `kaoyan-assistant-橘色原版` 复制了 3 个缺失的 skill 到新版 `skills/`:
    - `latex-formatter` (LaTeX规范) — **关键修复**：新版代码引用此 skill 但文件缺失，导致资料生成 prompt 中 LaTeX 规则从 76 行完整规范降级为 4 行兜底
    - `feynman-concept` (费曼概念) 和 `feynman-problem` (费曼解题) — 保持两版 skill 目录一致（当前两版均用内联 prompt，skill 文件备用）
  - 新版 skills 从 6 个恢复到 9 个，与橘色原版对齐

- **2026-06-19 费曼评价清洗误伤修复**:
  - `_clean_mimo_output()` 行级过滤误删评价中的改进建议（如"首先，你需要..."、"这道题的核心是..."、"根据定理..."）
  - 修复：检测到评价格式标记（`[总分]`/`[概念理解]`/`[解题正确性]`等）时跳过行级过滤
  - 同时将评价格式标记加入 `_answer_markers`，确保 AI 思考前缀被截断但评价内容完整保留

- **2026-06-22 CSS 断裂修复 — 数学问答 upload 重叠**:
  - **根因**: `.feature-card .card-title` 规则缺少闭合 `}`（第 467 行后），导致 CSS 解析器在 ~9700 字符处断裂
  - **影响范围**: 该规则之后所有 CSS 全部被丢弃（92/484 条规则被解析），包括 `stFileUploader` icon 隐藏规则、按钮样式、radio 样式等
  - **具体表现**: 数学问答 upload 按钮的 icon 文字 "upload" 和 label "Upload" 视觉重叠（`stIconMaterial` 的 `display: flex` 未被覆盖为 `font-size: 0`）
  - **修复**: 第 468 行补上 `}`

- **2026-06-20 资料生成文档修复**:
  - `_ai_output_to_docx_via_pandoc` 回退橘色原版：纯 pandoc + MathML，删掉三级 fallback 和粗体 strip
  - 模板字体宋体→等线，解决 Word 中文渲染偏黑（WPS/手机端无此问题）
  - 按钮 `🚀 生成资料` → `生成资料`（去 emoji）
  - 本地安装 Pandoc 3.6.4 (`C:\Users\zy\pandoc\pandoc-3.6.4\`)
  - 英语专家模块对照确认无缺失（仅 emoji 差异）
  - Pandoc 依赖 PATH，启动 Streamlit 需确保 pandoc 在 PATH 中

- **2026-06-18~19 对照橘色原版全面修复** (commit a2a9e34):
  - **复习窗口**: HTML 固定卡片 → `st.expander` 折叠 + `get_review_candidates()` 遗忘曲线 + `update_memory()` 写 DB + demo 假数据移除
  - **智能问答核心**: `call_llm_api` 阻塞 → `run_pipeline` 流式 SSE + `_typing_display` 打字效果 + `[ANSWER]/[KNOWLEDGE]` 结构化解析
  - **Q&A 交互按钮**: 回答下方增加「掌握了」「加入复习库」「生成复习题」三个按钮 + 知识点自动归纳入库
  - **费曼学习法**: 评分 prompt 切换为结构化 `CONCEPT_EVAL_PROMPT`/`PROBLEM_EVAL_PROMPT` + 正则提取分数 + `save_feynman_record` 持久化 + 历史记录展示 + 图片 OCR 上传
  - **出题/概念自测**: 知识库卡片按钮 → `session_state` 闭环（出题→生成题目卡→答题→AI评分→保存）；概念自测参考旧版直接用知识点名
  - 新增 `_record_qa_knowledge()` 函数：问答后自动入库知识点
  - Expander CSS 修复：去掉 `span:first-child` 的 `font-size:0` 
  - 全局 emoji 清理（出题/复习/费曼等标签和按钮）
  - 橘色原版路径: `C:\Users\zy\kaoyan-assistant-橘色原版\app.py`

## 当前任务

> **每次会话结束时更新此章节，下次新会话自动加载。**

- **进行中**: 无
- **待办**: 老板 review PR #7；错题库功能找回；备考看板图标等高问题
- **上次会话**: 2026-06-20 — 资料生成文档修复完成：回退 pandoc 函数、模板换等线、本地装 pandoc、去 emoji
- **下次启动提示**: "资料生成已修复，模板字体为等线。Pandoc 3.6.4 已安装在 C:\Users\zy\pandoc\pandoc-3.6.4\，启动 Streamlit 前确保 PATH 包含该目录。待办：错题库、看板图标。"
- **备份**: `C:\Users\zy\kaoyan-assistant-照搬版本`
