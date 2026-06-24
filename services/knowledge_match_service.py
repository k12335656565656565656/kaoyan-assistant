from __future__ import annotations

import re
from pathlib import Path


NOISE_TERMS = {
    "函数",
    "公式",
    "定理",
    "法则",
    "方法",
    "计算",
    "概念",
    "性质",
    "定义",
    "应用",
    "意义",
    "问题",
    "知识点",
    "相关",
}

SYNONYM_MAP = {
    "求导": "导数",
    "特征根": "特征值",
    "分布律": "分布",
    "收敛域": "收敛半径",
    "方差": "数字特征",
    "标准差": "数字特征",
}


def _normalize_title(title: str) -> str:
    text = str(title or "").strip()
    text = re.sub(r"^\d+\s*[-_、.．]?\s*", "", text)
    text = re.sub(r"\.md$", "", text, flags=re.IGNORECASE)
    return text.strip()


def _to_bigrams(text: str) -> set[str]:
    text = str(text or "").strip().lower()
    if not text:
        return set()
    if len(text) < 2:
        return {text}
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _jaccard(set_a: set[str], set_b: set[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def build_knowledge_index(corpus: list[dict]) -> dict:
    idx = {
        "doc_names": [],
        "title_map": {},
        "normalized_title_map": {},
        "title_kw": {},
        "content_terms": {},
    }
    for doc in corpus:
        fname = doc["id"]
        text = doc["text"]
        idx["doc_names"].append(fname)
        title_line = ""
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# "):
                title_line = stripped.lstrip("# ").strip()
                break
        title = title_line or Path(fname).stem
        normalized_title = _normalize_title(title)
        idx["title_map"][fname] = title
        idx["normalized_title_map"][fname] = normalized_title
        idx["title_kw"][fname] = _to_bigrams(normalized_title or fname)
        idx["content_terms"][fname] = _to_bigrams(text[:2500])
    return idx


def _concept_variants(concept: str) -> list[str]:
    concept = str(concept or "").strip()
    if not concept:
        return []
    variants = {concept}
    for noise in NOISE_TERMS:
        if noise in concept:
            trimmed = concept.replace(noise, "").strip()
            if len(trimmed) >= 2:
                variants.add(trimmed)
    for src, dst in SYNONYM_MAP.items():
        if src in concept:
            variants.add(concept.replace(src, dst))
        if dst in concept:
            variants.add(concept.replace(dst, src))
    return [variant for variant in variants if variant]


def match_knowledge_concepts(concepts: list[str], index: dict, top_k_per_concept: int = 2) -> list[str]:
    if not concepts or not index:
        return []

    results = []
    for concept_raw in concepts:
        variants = _concept_variants(concept_raw)[:4]
        if not variants:
            continue
        scores = {}
        for fname in index["doc_names"]:
            normalized_title = index["normalized_title_map"].get(fname, "").lower()
            best_variant_score = 0.0
            for variant in variants:
                variant_lower = variant.lower()
                variant_bigrams = _to_bigrams(variant_lower)
                score = 0.0
                pos = normalized_title.find(variant_lower)
                if pos >= 0:
                    score += 0.72 * max(0.1, 1 - pos / max(len(normalized_title), 1))
                score += _jaccard(variant_bigrams, index["title_kw"].get(fname, set())) * 0.45
                score += _jaccard(variant_bigrams, index["content_terms"].get(fname, set())) * 0.18
                if score > best_variant_score:
                    best_variant_score = score
            if best_variant_score >= 0.12:
                scores[fname] = best_variant_score
        best = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k_per_concept]
        for fname, _ in best:
            results.append(fname)
    return list(dict.fromkeys(results))


def extract_local_concepts(query: str, index: dict, max_concepts: int = 3) -> list[str]:
    query = str(query or "").strip()
    if not query or not index:
        return []

    query_bigrams = _to_bigrams(query)
    candidates = []
    for fname in index["doc_names"]:
        normalized_title = index["normalized_title_map"].get(fname, "")
        score = 0.0
        if normalized_title and normalized_title in query:
            score += 1.2
        for fragment in re.split(r"[的与及和、\s]+", normalized_title):
            if len(fragment) >= 2 and fragment in query:
                score += 0.9
                break
        score += _jaccard(query_bigrams, index["title_kw"].get(fname, set())) * 0.8
        score += _jaccard(query_bigrams, index["content_terms"].get(fname, set())) * 0.2
        if score >= 0.16:
            candidates.append((normalized_title, score))
    candidates.sort(key=lambda item: item[1], reverse=True)
    return [title for title, _ in candidates[:max_concepts] if title]


def parse_concepts_from_llm_output(raw_text: str) -> list[str]:
    concepts = []
    for line in str(raw_text or "").splitlines():
        text = line.strip().strip("-•*").strip()
        if not text:
            continue
        if len(text) <= 1:
            continue
        concepts.append(text)
    return concepts


def smart_match_knowledge(
    query: str,
    *,
    corpus: list[dict] | None = None,
    index: dict | None = None,
    llm_extract_fn=None,
    allow_llm: bool = True,
    top_k_per_concept: int = 2,
) -> list[str]:
    if not index:
        index = build_knowledge_index(corpus or [])

    concepts = []
    if allow_llm and llm_extract_fn:
        try:
            concepts = parse_concepts_from_llm_output(llm_extract_fn(query))
        except Exception:
            concepts = []

    if not concepts:
        concepts = extract_local_concepts(query, index)

    matched = match_knowledge_concepts(concepts, index, top_k_per_concept=top_k_per_concept)
    if matched:
        return matched

    fallback_concepts = extract_local_concepts(query, index)
    return match_knowledge_concepts(fallback_concepts, index, top_k_per_concept=top_k_per_concept)
