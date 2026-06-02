# 考研学习助手

基于 Streamlit 的考研数学智能问答系统，内置 110 个核心知识点，支持 AI 流式问答、复习出题、知识库管理、打卡督学等功能。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env 填入真实的 API Key

# 3. 启动
streamlit run app.py
```

浏览器打开 `http://localhost:8501`

## 功能模块

| 模块 | 说明 |
|------|------|
| 📐 数学问答 | 110 个知识点，流式 AI 回答，自动归纳复习 |
| 🔥 高校热度查询 | 院校数据分析，预测热度趋势 |
| 📖 英语专家 | 作文批改、长难句解析、翻译练习 |
| 📅 打卡督学 | 每日打卡、学习日记、番茄计时、学习画像 |
| 📚 专业知识库 | 上传资料、OCR 识别、错题本、AI 出题 |

## 管理后台

```bash
streamlit run admin.py --server.port 8502
```

访问 `http://localhost:8502`，密码自动生成在 `~/.kaoyan_admin_pass`

## 目录结构

```
├── app.py                  # 主程序
├── admin.py                # 管理后台
├── knowledge_base.py       # 知识库模块
├── requirements.txt        # Python 依赖
├── pack.py                 # 打包脚本
├── data/
│   ├── corpus/             # 110 个考研数学知识点
│   └── corpus_demo/        # 示例文档
├── skills/                 # AI 技能定义
├── docs/                   # 文档
└── templates/              # Prompt 模板
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AI_API_KEY` | API Key | 必填 |
| `AI_API_BASE` | API 地址 | `https://api.xiaomimimo.com/v1` |
| `AI_MODEL` | 模型名称 | `mimo-v2.5` |

## 部署

参见 `SETUP.md` 和 `DEPLOY.md`
