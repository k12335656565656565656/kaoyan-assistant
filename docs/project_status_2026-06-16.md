# 项目现状归档（2026-06-16）

## 归档目的

本文件用于记录当前仓库的实际状态，帮助后续开发快速接手，避免重复判断产品方向、技术边界和优先级。

## 项目定位

当前仓库是一个 Streamlit 考研学习助手项目，现阶段准备新增“专业课学科知识识别系统”。

新模块的目标不是单纯 OCR，而是：

1. 接收 PDF、图片或粘贴文本
2. 提取文字
3. 生成可审核的知识点草稿
4. 让用户编辑、删除、确认
5. 将确认后的知识点保存到用户私有知识库
6. 为后续解释、题型生成、复习卡片等能力提供基础数据

## 当前核心代码结构

- `app.py`
  - 主应用入口
  - 包含登录、多页面 UI、主知识问答、打卡、费曼学习法、数据库初始化等
  - 文件较大，仍是明显的单体结构
- `knowledge_base.py`
  - 当前“专业知识库”独立实现
  - 已包含资料上传、PDF/图片文字提取、知识点提取、知识库存储、错题本、复习本、AI 出题
- `app_kb.py`
  - 独立启动知识库页面的轻量入口
- `admin.py`
  - 管理后台
- `docs/`
  - 已开始补充产品、架构、路线图文档
- `agent-skills/`
  - 已新增项目级开发规范与技能说明

## 当前专业知识库实现状态

当前实际可用流程主要在 `knowledge_base.py`：

1. 用户上传 `pdf/png/jpg/jpeg/txt`
2. 文件保存到 `data/user_materials/{user_id}/`
3. 文字提取规则：
   - `txt`：直接读取
   - `pdf`：优先走 umi-ocr（如果服务可用），否则走 PyMuPDF 文本提取
   - `image`：走多模态 API OCR
4. 提取结果会先展示在可编辑文本框中
5. 用户点击确认后，调用 LLM 提取知识点
6. 提取结果按当前旧格式写入 `user_knowledge`

这说明项目已经有“上传 -> 提取文字 -> 用户确认 -> LLM 提取 -> 存储”的基础雏形，但还没有达到新的产品要求。

## 当前与目标方案的主要差距

### 1. 数据结构仍然过旧

当前 `user_knowledge` 只保存：

- `knowledge_name`
- `content`

还没有新的结构化字段，例如：

- `knowledge_type`
- `core_definition`
- `source_text`
- `source_page`
- `source_location`
- `tags`
- `mastery_state`
- AI 扩展/不确定性标记

### 2. LLM 输出仍然是文本，不是稳定 JSON

当前知识点提取逻辑仍使用“知识点1: ...”这种文本格式，后续通过字符串切分写库，稳定性不足，不满足机器可解析要求。

### 3. PDF 路由逻辑不符合新产品规则

当前实现是：

- 如果 umi-ocr 可用，PDF 优先 OCR
- 否则才做 PDF 文本提取

目标规则应当改为：

- PDF 先做直接文本提取
- 若文本过短、乱码、低质量，再回退 OCR

### 4. 业务逻辑存在重复

`app.py` 中还保留了一份与 `knowledge_base.py` 相近的 PDF/OCR/知识点保存辅助函数，后续容易出现漂移。

## 本轮已完成的文档与规范建设

已新增：

- `AGENTS.md`
- `docs/product_spec.md`
- `docs/architecture.md`
- `docs/dev_tasks.md`
- `agent-skills/windows-powershell-skill.md`
- `agent-skills/streamlit-python-skill.md`
- `agent-skills/git-workflow-skill.md`
- `agent-skills/knowledge-extraction-skill.md`
- `agent-skills/llm-json-output-skill.md`
- `agent-skills/sqlite-migration-skill.md`

这些文件的作用：

- 固定产品目标
- 固定 MVP 边界
- 固定架构演进方向
- 固定开发约束和数据库迁移原则
- 固定 LLM JSON 输出和知识点可信度规则

## PR 1 当前状态：已完成代码修改，尚未提交

本轮已完成“secret management and dependency cleanup”的最小变更：

- 去掉 `app.py` 中硬编码 API Key
- 改为从环境变量 `AI_API_KEY` 读取
- 补充 `.env.example`
- 对齐 `requirements.txt` 与实际导入
- 更新 `SETUP.md`、`SETUP_kb.md`、`README_Delivery.md`

涉及文件：

- `app.py`
- `requirements.txt`
- `requirements_kb.txt`
- `README_Delivery.md`
- `SETUP.md`
- `SETUP_kb.md`
- `.env.example`

## 当前工作区状态

截至本归档时间，工作区存在未提交变更：

已修改：

- `README_Delivery.md`
- `SETUP.md`
- `SETUP_kb.md`
- `app.py`
- `requirements.txt`
- `requirements_kb.txt`

未跟踪：

- `.env.example`
- `AGENTS.md`
- `agent-skills/`
- `docs/architecture.md`
- `docs/dev_tasks.md`
- `docs/product_spec.md`

## 当前主要工程风险

### 1. 单体文件过大

`app.py` 体量较大，后续如果直接继续往里加专业课识别逻辑，维护成本会明显上升。

### 2. 配置与实现分散

`app.py` 与 `knowledge_base.py` 现在都各自持有部分配置与辅助函数，后续建议抽一个共享配置层。

### 3. 结构化知识点尚未落库

当前数据库结构还不足以支撑“草稿知识点 -> 用户确认 -> 可信来源追踪”的产品要求。

### 4. 文本提取质量控制还没有统一结果对象

当前缺少统一的 material result schema，后面做多输入路由时容易让页面逻辑继续膨胀。

### 5. 仓库可能存在缺失文件

`app.py` 里引用了 `kaoyan_predict` 和 `recommend`，但当前工作区扫描中未发现对应文件，后续运行主应用时需要再次确认。

## 建议的下一步

按既定路线，建议进入 PR 2：

**统一资料输入路由**

目标：

1. 新增统一 material input 入口
2. 抽离 material router/service 层
3. 统一返回提取结果对象
4. 保留“先展示提取文本，再由用户确认”的交互
5. 先不改知识点存储结构，避免 PR 过大

这样可以先把“输入侧”做稳定，再进入结构化知识点 schema 和 JSON 提取。

## 归档时间

- 日期：2026-06-16
- 时间：21:39:08
