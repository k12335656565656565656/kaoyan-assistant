"""Extract screenshot-based math exam questions with Mimo, then stage and import them.

Examples:
  python scripts/import_math_true_exam.py --year 2026 --exam-type math1
  python scripts/import_math_true_exam.py --year 2026 --exam-type math1 --execute
"""

import argparse
import base64
import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from personalized_learning.math.true_exam_import import (  # noqa: E402
    discover_screenshot_tasks,
    run_staged_import,
    save_extraction_responses,
)
from personalized_learning.repository import ensure_schema  # noqa: E402
from personalized_learning.math.knowledge_mapping import load_knowledge_catalog  # noqa: E402
from services.llm_gateway import _apply_provider_options  # noqa: E402


def _mimo_extractor(task, prompt):
    api_key = os.environ.get("AI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("AI_API_KEY is missing; extraction was not started")
    image_data = base64.b64encode(task.page_path.read_bytes()).decode("ascii")
    model = os.environ.get("AI_MODEL", "mimo-v2.5").strip() or "mimo-v2.5"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你只负责按用户给定 JSON 格式转录题目，不得输出推理过程。"},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
            ]},
        ],
        "max_tokens": 5000,
        "temperature": 0,
    }
    _apply_provider_options(payload, model)
    api_base = os.environ.get("AI_API_BASE", "https://api.xiaomimimo.com/v1").rstrip("/")
    request = urllib.request.Request(
        f"{api_base}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        message = json.loads(response.read().decode("utf-8"))["choices"][0]["message"]
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"{task.page_name}: model returned no JSON content")
    return content


def main():
    parser = argparse.ArgumentParser(description="Stage screenshot-extracted math exam questions.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--exam-type", choices=("math1", "math2", "math3"), required=True)
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data" / "math_true_exam" / "processed")
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data" / "memory.db")
    parser.add_argument("--limit", type=int, default=0, help="Only extract the first N uncached screenshots when used with --execute.")
    parser.add_argument("--retry-page", action="append", default=[], help="Overwrite and re-extract this screenshot name; may be repeated.")
    parser.add_argument("--retry-unmapped", action="store_true", help="Re-extract cached screenshots whose Mimo response has no valid knowledge tags.")
    parser.add_argument("--execute", action="store_true", help="Call Mimo for screenshots without a cached response.")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    response_dir = args.data_root / str(args.year) / "responses" / args.exam_type
    staging_path = args.data_root / str(args.year) / "staging" / f"{args.exam_type}.json"
    tasks = discover_screenshot_tasks(args.data_root, args.year, args.exam_type)
    if not tasks:
        raise SystemExit(f"No screenshots found for {args.year}/{args.exam_type}.")
    if args.execute:
        if args.limit > 0:
            tasks = tasks[:args.limit]
        catalog = load_knowledge_catalog(PROJECT_ROOT / "data" / "corpus")
        save_extraction_responses(
            tasks,
            response_dir,
            _mimo_extractor,
            force_page_names=args.retry_page,
            retry_unmapped=args.retry_unmapped,
            knowledge_catalog=catalog,
        )
    connection = sqlite3.connect(args.database)
    try:
        ensure_schema(connection)
        catalog = load_knowledge_catalog(PROJECT_ROOT / "data" / "corpus")
        result = run_staged_import(args.data_root, args.year, args.exam_type, response_dir, staging_path, connection, catalog)
    finally:
        connection.close()
    print(json.dumps({**result, "staging_path": str(result["staging_path"])}, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
