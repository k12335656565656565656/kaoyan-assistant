# 专业知识库 — 部署指南

## 环境要求

- Python 3.10+
- pip

## 1. 安装依赖

```bash
python -m pip install -r requirements_kb.txt
```

## 2. 配置 API Key（推荐）

配置 AI API Key 后可获得更好的结构化知识点抽取效果。没有 Key 时，系统会使用本地规则生成候选草稿，流程仍可运行，但必须加强人工核对。

**Windows (CMD)**:
```cmd
set AI_API_KEY=your-api-key-here
```

**Windows (PowerShell)**:
```powershell
$env:AI_API_KEY="your-api-key-here"
```

**Linux / Mac**:
```bash
export AI_API_KEY="your-api-key-here"
```

也可以复制 `.env.example` 为 `.env` 后直接填写。

可选配置（有默认值）：
```bash
export AI_API_BASE="https://api.xiaomimimo.com/v1"        # API地址
export MEMORY_DB="data/memory.db"                          # 数据库路径
export PADDLE_OCR_LANG="ch"                                # OCR语言
```

## 3. 启动

```bash
python -m streamlit run app_kb.py --server.port 8501
```

浏览器打开 `http://localhost:8501`

Windows 也可以直接双击 `启动知识库.bat`。

第一次补专业课资料，请继续阅读 [`docs/professional_knowledge_quick_workflow.md`](docs/professional_knowledge_quick_workflow.md)。

本模块也可以被主站直接挂载，入口函数为：

```python
from professional_knowledge import render_professional_knowledge_system
```

## 4. 目录结构

```
├── app_kb.py                       # 专业知识库独立入口
├── knowledge_base.py               # Streamlit 工作流编排
├── professional_knowledge/         # UI 与专业课配置注册表
├── repositories/                   # SQLite 数据访问
├── schemas/                        # 稳定数据结构
├── services/                       # OCR、清洗与抽取服务
├── requirements_kb.txt             # 独立入口依赖
└── data/
    ├── memory.db                   # SQLite 数据库（首次启动自动创建）
    ├── config/custom_subjects.json # 页面向导创建的专业课配置
    └── user_materials/             # 用户上传资料
```

## 5. 功能说明

| 功能 | 说明 |
|------|------|
| 导入并核对文本 | 上传 PDF/图片/TXT 或粘贴文本，人工修正后再抽取 |
| 确认知识点 | 编辑、删除、确认候选知识点，保留原文依据 |
| 我的知识库 | 检索知识点、维护掌握状态、生成复习内容 |
| 恢复继续 | 页面刷新或进程重启后恢复确认文本和草稿队列 |
| 错题本 | 批量导入并管理错题 |

## 6. OCR 识别方式

系统按以下顺序处理资料：

1. 文字型 PDF 优先使用 **PyMuPDF** 直接提取。
2. PDF 文字层质量不足时，自动回退 **RapidOCR / PaddleOCR**。
3. 图片使用 **RapidOCR / PaddleOCR**，不把 AI 多模态识别作为主链。
4. TXT、MD 和粘贴文本直接进入清洗与人工确认。

## 7. 常见问题

**Q: 提示"未设置 API Key"**
A: 按第2步设置环境变量后重启

**Q: OCR 识别失败**
A: 确认已安装 `rapidocr-onnxruntime`；需要 PaddleOCR 回退时，再确认 `paddleocr` 与 `paddlepaddle` 安装正常。文字型 PDF 和粘贴文本不依赖 OCR。

**Q: 数据库报错**
A: 不要直接删除 `data/memory.db`。先复制一份备份，再保存完整报错信息。当前迁移只会新增表、列和索引，不会主动删除旧数据。
