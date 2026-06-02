# 专业知识库 — 部署指南

## 环境要求

- Python 3.10+
- pip

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 配置 API Key

**必须设置** AI API Key，否则无法使用 AI 功能。

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

可选配置（有默认值）：
```bash
export AI_API_BASE="https://api.z.ai/api/coding/paas/v4"  # API地址
export MEMORY_DB="data/memory.db"                          # 数据库路径
export UMI_OCR_URL="http://localhost:1224"                 # 本地OCR服务
```

## 3. 启动

```bash
streamlit run app.py --server.port 8501
```

浏览器打开 `http://localhost:8501`

## 4. 目录结构

```
├── app.py                  # 主程序入口
├── knowledge_base.py       # 核心模块
├── requirements.txt        # 依赖
└── data/
    └── memory.db           # SQLite数据库（首次启动自动创建）
```

## 5. 功能说明

| 功能 | 说明 |
|------|------|
| 📖 知识库 | 上传 PDF/图片/TXT，AI 自动识别并提取知识点 |
| 📝 错题本 | 记录错题，支持标记已掌握 |
| 📚 复习本 | 待复习知识点列表 |
| 🎲 AI出题 | 基于知识点生成练习题 |

## 6. OCR 识别方式

系统按优先级使用以下方式识别 PDF：

1. **umi-ocr**（推荐）：本地 OCR 服务，中文识别效果最好
   - 需要单独安装 [umi-ocr](https://github.com/hiroi-sora/Umi-OCR)
   - 启动后默认在 `http://localhost:1224`
2. **PyMuPDF**：直接提取 PDF 中的文本（仅对文字型 PDF 有效）
3. **AI 多模态**：用 GLM-4v 模型识别图片（最慢，但支持手写）

## 7. 常见问题

**Q: 提示"未设置 API Key"**
A: 按第2步设置环境变量后重启

**Q: OCR 识别失败**
A: 检查 umi-ocr 是否启动，或尝试直接上传图片（走 AI 多模态识别）

**Q: 数据库报错**
A: 删除 `data/memory.db`，重启后自动重建
