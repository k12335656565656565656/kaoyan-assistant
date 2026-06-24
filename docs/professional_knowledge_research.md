# 专业课知识点识别系统调研与架构决策

## 当前决策

暂不使用 Hermes Agent 作为系统内核。

本阶段采用轻量、可移植的模块化架构：

```text
主站入口
→ professional_knowledge.render_professional_knowledge_system
→ Streamlit UI
→ 材料输入路由
→ PDF 文本提取 / PaddleOCR / OCR 回退
→ LLM JSON 抽取 / 本地规则兜底
→ 候选草稿确认
→ SQLite 私有知识库
```

## 为什么暂不使用 Hermes

Hermes Agent 更适合长期运行的 autonomous agent、工具调度、多平台消息入口、技能记忆和后台自动化。它可以作为后续后台代理层研究，但不适合作为当前 Streamlit 功能模块的核心依赖。

主要原因：

- 线上主站是 Streamlit 网站，当前最需要的是一个可直接挂载的页面模块。
- Hermes 需要额外运行时和至少一个 LLM provider；云 provider 通常需要 API key，本地模型则需要额外算力和部署维护。
- 当前系统核心任务是文档识别、结构化抽取、人工确认和入库，不需要 agent OS 级别的调度。
- 引入 Hermes 会增加部署复杂度、状态管理复杂度和线上安全面。

## 参考项目

- MinerU：https://github.com/opendatalab/mineru
  - 复杂 PDF / Office 文档解析，输出 Markdown / JSON，适合作为后续文档解析层增强参考。
- PaddleOCR：https://github.com/PaddlePaddle/PaddleOCR
  - 成熟 OCR 工具，支持中文和文档结构化。当前图片 OCR 已采用 PaddleOCR，不再使用 AI 多模态识别。
- LangExtract：https://github.com/google/langextract
  - 非结构化文本到结构化信息抽取，强调 source grounding、schema 输出和长文档处理。
- Kreuzberg：https://github.com/kreuzberg-dev/kreuzberg
  - 多格式文档智能提取框架，支持 PDF、Office、图片、元数据和结构化信息。
- Hermes Agent：https://hermes-agent.nousresearch.com/docs/
  - 自主代理框架，适合未来研究后台自动化、批量处理、提醒和多 agent 调度。

## 当前本地实现原则

1. 主站无侵入：不直接改线上 `http://111.229.102.178:8501/`。
2. 本地优先：先在本地完成独立验收。
3. 可移植：通过 `professional_knowledge` 包提供统一入口。
4. 可降级：LLM 失败时启用本地规则兜底，保证流程不断。
5. 用户确认：候选知识点必须经过编辑 / 删除 / 确认后再保存。
6. 移动端可用：长表单和候选草稿采用纵向布局与折叠卡片。

## 2026-06-17 本地验收记录

### 验证资料

本地下载公开 408 资料用于链路测试，文件放在 `data/test_materials/408/`，不作为用户上传资料提交：

- `2022-408考试大纲.pdf`
- `2024-408真题解析.pdf`
- `2025-408真题.pdf`

### 已验证链路

- PDF 直接文本抽取可以生成 `=== 第N页 ===` 页码标记。
- 图片 OCR 使用 PaddleOCR，中文和英文模型均可初始化。
- 知识点 JSON 抽取使用 `mimo-v2.5`，真实 408 PDF 样本可生成结构化草稿。
- 每条草稿可以携带 `source_page` 和 `source_text`，用于回到 PDF 原文核对。
- 模型返回半截 JSON 或代码块 JSON 时，解析层可以恢复或正常解析。
- 模型失败或 JSON 不可解析时，本地规则兜底不会让页面崩溃。
- 已确认草稿可以保存到 SQLite 私有知识库。
- 已保存知识点可以生成复习扩展内容。
- `app_kb.py` Streamlit 测试无异常，`localhost:8501` HTTP 健康检查返回 200。
- Streamlit 自动化模拟已验证：粘贴文本、填写章节、开始识别、抽取候选草稿、确认全部、保存入库、删除草稿、清空草稿。
- 测试结束后，已清空用户上传资料、用户知识点、错题、复习记录和掌握状态。

### 当前风险

- 复杂扫描版 PDF 仍依赖 PaddleOCR 的识别质量，后续需要做更多低清晰度样本测试。
- 长 PDF 目前仍是 MVP 分段，后续需要做多段抽取、去重、合并和来源校验。
- LLM 仍可能过度抽取题干或解析句，已经通过 prompt、schema、人工确认区和兜底过滤降低风险，但不能完全消除。
- `source_page/source_text` 由 PDF 页码标记和模型输出共同决定，正式上线前应增加“来源必填或人工补充”的保存校验。
- 当前 UI 以 Streamlit 为主，移动端可纵向使用，但还没有做真实手机浏览器逐项验收。
- PaddleOCR 首次运行会下载模型，服务器部署时应提前预热模型缓存，避免首次用户等待过久。

## 后续演进路线

### 阶段 1：本地可移植模块

- 保留 `app_kb.py` 独立验收入口。
- 主功能通过 `professional_knowledge.render_professional_knowledge_system` 暴露。
- 完成材料上传、文本提取、候选草稿、确认、保存闭环。

### 阶段 2：主站本地接入

- 在本地主站增加一个页面入口。
- 复用主站登录态中的 `user_id` 和 `username`。
- 确认数据隔离、移动端布局和错误兜底。

### 阶段 3：线上部署

- 同步必要文件到服务器。
- 配置 `.env` 和依赖。
- 保留数据库迁移兼容逻辑。
- 做线上人工验收后再开放入口。

### 阶段 4：高级增强

- 继续优化 PaddleOCR 部署体验；后续可评估 MinerU / Kreuzberg 增强复杂 PDF 解析。
- 增加长文档分块合并和 source grounding。
- 生成复习卡片、考法解释、追问、AI 发散内容。
- 再评估 Hermes 是否适合做后台批处理和自动化调度。
