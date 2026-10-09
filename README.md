# Kaoyan Assistant · 考研智能学习助手

Kaoyan Assistant 是一个面向考研备考场景的一站式智能学习工作台，基于 **Streamlit + RAG + LLM** 构建，覆盖政治、英语、数学与专业课复习中的高频需求。项目将知识库检索、智能问答、错题管理、学习计划、真题练习和英语写作训练整合在同一个 Web 应用中，帮助考生把分散的复习资料转成可检索、可练习、可追踪的学习系统。

## 核心功能

- **智能问答与知识库检索**：支持上传专业课资料、讲义和笔记，基于 RAG 进行上下文检索，减少模型幻觉。
- **数学与专业课练习**：提供题目解析、诊断出题、错题本和能力薄弱点分析，便于针对性复盘。
- **英语学习模块**：整合单词记忆、真题语料与写作训练，支持从题目理解、写作练习到批改反馈的完整流程。
- **学习计划与打卡**：内置复习计划、每日打卡、任务进度和学习记录，帮助用户持续跟踪备考状态。
- **游客模式**：无需注册即可快速体验核心界面和常用流程，个性化数据不会被保存。
- **本地优先的数据设计**：用户资料、学习记录和上传文档保存在本地数据库中，API Key 只通过 `.env` 配置，不进入 Git 历史。

## 技术栈

- **前端 / 应用层**：Streamlit、HTML、CSS、KaTeX
- **后端**：Python、SQLite、RAG Pipeline
- **AI 能力**：OpenAI-compatible Chat API，默认可配置为 `mimo-v2.6-flash`
- **文档处理**：PDF / DOCX / Markdown 等资料解析与切分
- **部署**：支持本地运行，也可部署到 Linux 服务器

## 快速开始

```bash
git clone https://github.com/k12335656565656565656/kaoyan-assistant.git
cd kaoyan-assistant

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

在 `.env` 中配置模型服务：

```env
AI_API_KEY=your-api-key
AI_API_BASE=https://api.xiaomimimo.com/v1
AI_MODEL=mimo-v2.6-flash
```

启动应用：

```bash
streamlit run app.py
```

打开浏览器访问：

```text
http://localhost:8501
```

## 项目结构

```text
app.py                 # Streamlit 主应用入口
knowledge_base.py      # 知识库、RAG 检索与题目生成逻辑
services/              # 业务服务与模型网关
data/                  # 语料、真题数据与本地资源
docs/                  # 设计稿与项目文档
tests/                 # 功能测试
```

## 安全说明

项目不会内置任何真实 API Key。`.env` 已被 `.gitignore` 忽略，请勿将个人密钥、数据库文件或用户数据提交到公开仓库。

## 适合的使用场景

- 考研学生希望把散落的讲义、笔记和真题整理成统一知识库。
- 需要一个可本地部署、可自定义模型接口的智能学习系统。
- 开发者想参考 Streamlit、RAG、LLM 应用和错题系统的整合实践。
