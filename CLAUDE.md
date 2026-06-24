# CLAUDE.md

## 项目概述

考研学习助手 — Streamlit 多用户 Web 应用。提供考研数学问答、英语专家、打卡督学、学习资料生成、费曼学习法、知识库等功能。API 使用小米 MiMo v2.5。

## 技术栈

- **Python** 3.13（使用本机可用的 Python 3.13 解释器）
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
| `copy_to_git.py` | 从开发目录同步到另一个 Git 工作目录，用于发布 |

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
API_KEY = os.environ.get("AI_API_KEY", "")
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
scp KaoyanRAG-v4.2.zip ubuntu@your-server:/home/ubuntu/
ssh ubuntu@your-server
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
- 使用环境变量或 `.env` 管理 API Key，不在代码仓库内硬编码
- 不 mock 纯函数模块，不引入 `as any` 到生产代码
- 打包时需确认 `data/katex/`、`data/reference/template.docx`、`templates/` 均被包含

## 最近改动

- **2026-06-15 UI 全面重设计**:
  - CSS 切换到 Indigo 主题 (#4f46e5/#6366f1)，Design Tokens 体系
  - Hub 改为 Dashboard 布局：Hero 渐隐标题 + Flow 心流指标 + 4 SVG feature cards + 2 wide cards
  - 卡片全部 Feather 风格 SVG 图标（四宫格/柱状图/书本/聊天气泡/文档/对勾）
  - 卡片 `<a href="?p=xxx">` query param 路由，整卡任意位置可点
  - 侧边栏全局常驻：毛玻璃背景、2 分组标签、Emoji + st.button 导航、流光边框、弹性按钮
  - 侧边栏用户卡片升级：头像渐变流光 + 打卡天数统计
  - 6 层呼吸过渡动画系统（breatheIn / cardReveal / sidebarSlideIn / bannerReveal / qaRise / navItemFade）
  - 页面切换模糊→清晰过渡 + 卡片错开浮现
- 学习计划 prompt 去「老师」化（朴素理性风格）
- MiMo API 全量切换（`_extract_content()` 全局修复）
- pack.py 添加 recommend.py，.gitignore 更新
- 新建 `启动.bat` / `管理进程.bat`（纯 ASCII，端口轮询，自动开浏览器）
- Memory 记忆系统配置 + CLAUDE.md 当前任务章节

## 当前任务

> **每次会话结束时更新此章节，下次新会话自动加载。**

- **进行中**: 无
- **待办**: 无
- **上次会话**: 2026-06-15 — Indigo UI 全面重设计、呼吸过渡动画、侧边栏毛玻璃升级
- **下次启动提示**: 直接说"继续之前的工作"，Claude 从本文件和 memory/ 恢复上下文
