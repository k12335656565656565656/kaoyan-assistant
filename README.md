# Kaoyan Assistant

一个基于 `Python + Streamlit + SQLite + OCR + LLM` 的考研学习助手，聚焦专业课问答、资料抽取、专业知识库沉淀、学习计划辅助和基础英语/数学工具能力。

## Overview

这个仓库发布的是一个适合继续开发和二次部署的工程版本，默认排除了本地敏感信息、运行日志、数据库文件、用户上传资料和测试 PDF 等内容。

当前主要能力包括：

- Streamlit Web 应用主站
- 专业知识库独立入口
- PDF 文本提取与 OCR 回退
- LLM 驱动的知识点抽取与问答
- 可配置专业课向导与可恢复的资料确认工作流
- 知识点幂等入库与来源依据质量门禁
- SQLite 本地持久化
- 学习计划、用户画像、英语/数学辅助能力

## Tech Stack

- Python 3.10+
- Streamlit
- SQLite
- PyMuPDF
- PaddleOCR / RapidOCR
- OpenAI-compatible LLM API

## Repository Layout

```text
kaoyan-assistant/
├── app.py                      # 主应用入口
├── app_kb.py                   # 专业知识库独立入口
├── knowledge_base.py           # 知识库主流程
├── professional_knowledge/     # 专业知识库 UI 与专业目录
├── services/                   # 业务服务层
├── repositories/               # SQLite 数据访问层
├── schemas/                    # 数据结构定义
├── data/                       # 语料、模板与本地运行数据目录
├── docs/                       # 产品、架构、设计文档
├── templates/                  # Prompt 模板
└── skills/                     # Skill 配置
```

## Quick Start

### 1. Install

```bash
python -m pip install -r requirements.txt
```

如只运行知识库相关页面，也可使用：

```bash
python -m pip install -r requirements_kb.txt
```

### 2. Configure Environment

复制 `.env.example` 为 `.env`，并填写你自己的配置：

```env
AI_API_KEY=your-api-key
AI_API_BASE=https://api.xiaomimimo.com/v1
UMI_OCR_URL=http://localhost:1224
MEMORY_DB=data/memory.db
```

### 3. Run

主站：

```bash
python -m streamlit run app.py --server.port 8505 --server.fileWatcherType none
```

专业知识库：

```bash
python -m streamlit run app_kb.py --server.port 8501 --server.fileWatcherType none
```

## Data Policy

为避免把本地运行痕迹或受限资料直接发布到公开仓库，以下内容默认不纳入版本管理：

- `.env` 与本地环境变量文件
- SQLite 数据库
- 用户上传资料
- 任务执行产物
- 日志与临时文件
- 测试样本 PDF 与本地语料 PDF

如果你需要补充资料，请放入本地 `data/` 对应目录，并确认版权、隐私和分发权限。

## Upstream Note

该工程基于上游仓库演进而来，并在此基础上加入了知识库、OCR、自适应抽取、学习规划和仓库治理等改动。

为减少对原仓库的耦合，当前发布版本默认以独立项目方式维护；如需对比原始来源，请查看本地 Git 远程中的 `upstream`。

## Engineering Docs

- [README_Delivery.md](README_Delivery.md)
- [SETUP.md](SETUP.md)
- [SETUP_kb.md](SETUP_kb.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/professional_knowledge_quick_workflow.md](docs/professional_knowledge_quick_workflow.md)

## Security

请勿提交真实 API Key、用户数据、数据库文件或受限资料。更多说明见 [SECURITY.md](SECURITY.md)。
