# 专业课知识点识别系统集成说明

## 目标

本模块先在本地完成可移植实现，再挂靠到线上主网站 `http://111.229.102.178:8501/`。当前阶段不直接修改线上主网站。

核心流程：

```text
专业课资料
→ 文本提取 / PaddleOCR
→ 结构化知识点草稿
→ 用户编辑 / 删除 / 确认
→ 保存到私有知识库
→ 后续解释、考法、复习卡片、追问和 AI 发散
```

## 本地入口

独立运行：

```powershell
python -m streamlit run app_kb.py --server.port 8501
```

Windows 可双击：

```text
启动知识库.bat
```

## 主站挂载方式

未来主站只需要引入一个入口函数：

```python
from professional_knowledge import render_professional_knowledge_system

if st.session_state.page == "professional_knowledge":
    render_professional_knowledge_system(
        user_id=st.session_state.get("user_id"),
        username=st.session_state.get("username"),
    )
    st.stop()
```

主站首页或侧边栏增加按钮：

```python
if st.button("专业课知识识别"):
    st.session_state.page = "professional_knowledge"
    st.rerun()
```

## 需要迁移的文件

```text
professional_knowledge/
knowledge_base.py
services/
schemas/
repositories/
app_kb.py              # 仅用于独立验收，可不放入主站入口
requirements_kb.txt
```

## 环境变量

```env
AI_API_KEY=your-api-key
AI_API_BASE=https://api.xiaomimimo.com/v1
UMI_OCR_URL=http://localhost:1224
MEMORY_DB=data/memory.db
```

如果 `AI_API_KEY` 不可用，系统仍可使用本地规则兜底生成候选草稿，但质量低于 LLM 抽取，需要用户人工核对。

## OCR 后端

图片识别使用 PaddleOCR，不使用 AI 多模态识别：

```powershell
python -m pip install paddleocr paddlepaddle
```

Windows CPU 环境如果遇到 oneDNN/PIR 报错，模块会默认设置：

```env
PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=0
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
```

## 移动端 / Web 端要求

- 上传、预览、候选草稿、确认、保存流程在窄屏下可纵向操作。
- 表单按钮使用整行宽度，避免移动端误触。
- 候选知识点使用 expander 折叠展示，降低长文本页面压力。
- 保存入库前必须经过用户确认，不自动写入私有知识库。

## 后续建议

1. 将 `knowledge_base.py` 继续拆成 `ui/upload.py`、`ui/drafts.py`、`ui/repository.py`。
2. 在复杂 PDF 解析上继续评估 MinerU 或 Kreuzberg。
3. 参考 LangExtract 的 source grounding 思路，增强原文定位和高亮。
4. 在主站完成入口接入前，继续保留 `app_kb.py` 作为本地验收入口。
