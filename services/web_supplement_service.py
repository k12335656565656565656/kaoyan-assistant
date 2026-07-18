from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable


SearchFetcher = Callable[[str], str]


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str = ""

    def to_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


def _default_fetch(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; kaoyan-assistant/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", errors="replace")


def _clean_html(value: str) -> str:
    value = re.sub(r"<.*?>", "", value or "", flags=re.DOTALL)
    return " ".join(html.unescape(value).split())


def _decode_duckduckgo_url(value: str) -> str:
    value = html.unescape(value or "")
    parsed = urllib.parse.urlparse(value)
    query = urllib.parse.parse_qs(parsed.query)
    if query.get("uddg"):
        return query["uddg"][0]
    return value


def parse_duckduckgo_results(page_html: str, limit: int = 5) -> list[WebSearchResult]:
    results: list[WebSearchResult] = []
    title_pattern = re.compile(
        r'<a(?=[^>]*class="result__a")(?=[^>]*href="([^"]+)")[^>]*>(.*?)</a>',
        flags=re.DOTALL,
    )
    title_matches = list(title_pattern.finditer(page_html or ""))
    for index, title_match in enumerate(title_matches):
        next_start = title_matches[index + 1].start() if index + 1 < len(title_matches) else len(page_html or "")
        block = (page_html or "")[title_match.end():next_start]
        snippet_match = re.search(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|<div[^>]*class="result__snippet"[^>]*>(.*?)</div>',
            block,
            flags=re.DOTALL,
        )
        snippet_raw = ""
        if snippet_match:
            snippet_raw = snippet_match.group(1) or snippet_match.group(2) or ""
        result = WebSearchResult(
            title=_clean_html(title_match.group(2)),
            url=_decode_duckduckgo_url(title_match.group(1)),
            snippet=_clean_html(snippet_raw),
        )
        if result.title and result.url and result.url.startswith(("http://", "https://")):
            results.append(result)
        if len(results) >= limit:
            break
    if results:
        return results
    lite_title_pattern = re.compile(
        r"<a(?=[^>]*class=['\"]result-link['\"])(?=[^>]*href=\"([^\"]+)\")[^>]*>(.*?)</a>",
        flags=re.DOTALL,
    )
    lite_matches = list(lite_title_pattern.finditer(page_html or ""))
    for index, match in enumerate(lite_matches):
        next_start = lite_matches[index + 1].start() if index + 1 < len(lite_matches) else len(page_html or "")
        block = (page_html or "")[match.end():next_start]
        snippet_match = re.search(
            r"<td[^>]*class=['\"]result-snippet['\"][^>]*>(.*?)</td>",
            block,
            flags=re.DOTALL,
        )
        result = WebSearchResult(
            title=_clean_html(match.group(2)),
            url=_decode_duckduckgo_url(match.group(1)),
            snippet=_clean_html(snippet_match.group(1) if snippet_match else ""),
        )
        if result.title and result.url.startswith(("http://", "https://")):
            results.append(result)
        if len(results) >= limit:
            break
    return results


def parse_bing_results(page_html: str, limit: int = 5) -> list[WebSearchResult]:
    results: list[WebSearchResult] = []
    blocks = re.split(r'<li class="b_algo"', page_html or "")
    for block in blocks[1:]:
        title_match = re.search(r"<h2[^>]*>\s*<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, flags=re.DOTALL)
        if not title_match:
            continue
        snippet_match = re.search(r"<p[^>]*>(.*?)</p>", block, flags=re.DOTALL)
        result = WebSearchResult(
            title=_clean_html(title_match.group(2)),
            url=html.unescape(title_match.group(1)),
            snippet=_clean_html(snippet_match.group(1) if snippet_match else ""),
        )
        if result.title and result.url.startswith(("http://", "https://")):
            results.append(result)
        if len(results) >= limit:
            break
    return results


def _query_terms(query: str) -> list[str]:
    return [
        item.lower()
        for item in re.split(r"[\s，。；、,.!?！？:：()（）/\\\\-]+", query or "")
        if len(item.strip()) >= 2
    ][:8]


def _is_relevant_result(result: dict, terms: list[str]) -> bool:
    if not terms:
        return True
    haystack = " ".join(
        str(result.get(field) or "").lower()
        for field in ("title", "snippet", "url")
    )
    return any(term in haystack for term in terms)


def search_web(query: str, *, limit: int = 5, fetch: SearchFetcher | None = None) -> list[dict]:
    query = " ".join(str(query or "").split())
    if not query:
        return []
    terms = _query_terms(query)
    fetch = fetch or _default_fetch
    attempts = [
        (
            "https://lite.duckduckgo.com/lite/?",
            parse_duckduckgo_results,
        ),
        (
            "https://duckduckgo.com/html/?",
            parse_duckduckgo_results,
        ),
        (
            "https://www.bing.com/search?",
            parse_bing_results,
        ),
    ]
    last_error = None
    for base_url, parser in attempts:
        url = base_url + urllib.parse.urlencode({"q": query})
        try:
            page = fetch(url)
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last_error = exc
            continue
        results = [
            item.to_dict()
            for item in parser(page, limit=limit * 2)
        ]
        results = [item for item in results if _is_relevant_result(item, terms)][:limit]
        if results:
            return results
    if last_error:
        raise RuntimeError("搜索暂时超时，请稍后重试或换一个关键词。")
    return []


def build_web_supplement_prompt(point: dict, results: list[dict]) -> str:
    return f"""你是考研专业课资料助手。下面是用户手动触发联网搜索得到的网页结果，请基于这些结果给当前知识点做补充。

要求：
1. 直接输出补充内容，不要写“好的”“收到”“下面是”等开场。
2. 不编造网页结果没有的信息。
3. 优先补：易混点、常见考法、学习提示。
4. 每条关键补充后用 [网页1] 这种标注来源。
5. 结尾提醒用户回到教材/学校考纲核对。

当前知识点：
{json.dumps(point, ensure_ascii=False, indent=2)}

网页结果：
{json.dumps(results, ensure_ascii=False, indent=2)}
"""
