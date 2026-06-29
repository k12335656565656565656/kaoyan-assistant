"""Catalog of subject-level RAG knowledge bases for the professional knowledge workspace."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RagKnowledgeBaseProfile:
    key: str
    title: str
    subject_label: str
    status: str
    stage: str
    summary: str
    capabilities: list[str] = field(default_factory=list)
    source_strategy: str = ""
    notes: str = ""
    enabled: bool = False


RAG_KNOWLEDGE_BASES: list[RagKnowledgeBaseProfile] = [
    RagKnowledgeBaseProfile(
        key="exam_408",
        title="408 计算机联考",
        subject_label="408综合",
        status="已启用",
        stage="MVP",
        summary="支持 PDF/OCR、知识点抽取、原文引用、复习内容与后续 RAG 扩展。",
        capabilities=["知识点抽取", "原文引用", "复习内容", "后续关系图"],
        source_strategy="PaddleOCR + PDF 文本提取 + 结构化知识点确认",
        notes="当前主通道。后续优先接入 source_chunks、混合检索与关系图谱。",
        enabled=True,
    ),
    RagKnowledgeBaseProfile(
        key="edu_311",
        title="311 教育学",
        subject_label="教育学",
        status="预留框架",
        stage="待接入",
        summary="保留教材、真题、教育学理论知识点与复习库接入位。",
        capabilities=["知识点抽取", "教材引用", "题型归纳"],
        source_strategy="待接入 MinerU / OCR / chunk 入库",
        notes="适合作为统一专业课框架的下一批接入对象。",
        enabled=False,
    ),
    RagKnowledgeBaseProfile(
        key="psych_312",
        title="312 心理学",
        subject_label="心理学",
        status="预留框架",
        stage="待接入",
        summary="保留普通心理学、实验心理学、统计测量等专业课资料入口。",
        capabilities=["知识点抽取", "概念关系", "章节复习"],
        source_strategy="待接入 MinerU / OCR / source_chunks",
        notes="后续可重点增强概念图和理论关系图。",
        enabled=False,
    ),
    RagKnowledgeBaseProfile(
        key="med_integrated",
        title="医学考研",
        subject_label="医学考研",
        status="已启用",
        stage="MVP",
        summary="支持 PDF/OCR、知识点抽取、原文引用、复习内容与后续 RAG 扩展。",
        capabilities=["知识点抽取", "原文引用", "复习内容", "后续关系图"],
        source_strategy="PaddleOCR + PDF 文本提取 + 结构化知识点确认",
        notes="复用 408 同款识别与确认链路，本地资料可放在 Medical Postgraduate Entrance Examination 目录。",
        enabled=True,
    ),
    RagKnowledgeBaseProfile(
        key="custom_minor_subject",
        title="小众专业课模板",
        subject_label="其他",
        status="可扩展",
        stage="框架已留",
        summary="面向通信、控制、机械、法学、艺术等小众专业课的通用接入模板。",
        capabilities=["可配置学科", "知识点确认", "后续 RAG 接入"],
        source_strategy="统一使用 source_chunks + knowledge_points + learning_state 三层结构",
        notes="后续新增专业课时，优先补配置和 Prompt，不必重写整套页面。",
        enabled=False,
    ),
]


def list_rag_knowledge_bases() -> list[RagKnowledgeBaseProfile]:
    return list(RAG_KNOWLEDGE_BASES)


def list_enabled_subjects() -> list[str]:
    subjects = [item.subject_label for item in RAG_KNOWLEDGE_BASES if item.enabled]
    subjects.append("其他")
    return list(dict.fromkeys(subjects))
