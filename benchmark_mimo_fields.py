"""MiMo API 字段检测 — 验证 content vs reasoning_content"""
import json, urllib.request, time
import os

API_KEY = os.environ.get("AI_API_KEY", "").strip()
API_BASE = os.environ.get("AI_API_BASE", "https://api.xiaomimimo.com/v1").strip()

def test_api(prompt, stream=False):
    data = {
        "model": "mimo-v2.5",
        "messages": [
            {"role": "system", "content": "你是考研数学辅导专家。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 500,
        "temperature": 0.3,
        "stream": stream,
    }
    req = urllib.request.Request(
        API_BASE + "/chat/completions",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
        method="POST"
    )
    start = time.time()
    with urllib.request.urlopen(req, timeout=60) as resp:
        elapsed = time.time() - start
        if stream:
            # Collect all SSE chunks
            content_full = ""
            reasoning_full = ""
            buffer = ""
            while True:
                chunk = resp.read(512)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    try:
                        obj = json.loads(payload)
                        choices = obj.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        c = delta.get("content")
                        r = delta.get("reasoning_content")
                        if c:
                            content_full += c
                        if r:
                            reasoning_full += r
                    except json.JSONDecodeError:
                        pass
            return {
                "time": elapsed,
                "content": content_full[:200],
                "content_len": len(content_full),
                "reasoning_content": reasoning_full[:200],
                "reasoning_len": len(reasoning_full),
            }
        else:
            result = json.loads(resp.read().decode("utf-8"))
            msg = result["choices"][0]["message"]
            return {
                "time": elapsed,
                "content": (msg.get("content") or "")[:200],
                "content_len": len(msg.get("content") or ""),
                "reasoning_content": (msg.get("reasoning_content") or "")[:200],
                "reasoning_len": len(msg.get("reasoning_content") or ""),
            }

if __name__ == "__main__":
    if not API_KEY:
        raise SystemExit("请先设置 AI_API_KEY 环境变量。")

    print("=" * 60)
    print("MiMo API Response Field Analysis")
    print("=" * 60)

    # Test 1: Simple math question (non-stream)
    print("\n[Test 1] Simple question (non-stream):")
    r = test_api("什么是导数？简要回答。", stream=False)
    print(f"  Time: {r['time']:.2f}s")
    print(f"  content ({r['content_len']} chars): {r['content']}")
    print(f"  reasoning_content ({r['reasoning_len']} chars): {r['reasoning_content']}")

    # Test 2: Simple math question (stream)
    print("\n[Test 2] Simple question (stream):")
    r = test_api("什么是极限？简要回答。", stream=True)
    print(f"  Time: {r['time']:.2f}s")
    print(f"  content ({r['content_len']} chars): {r['content']}")
    print(f"  reasoning_content ({r['reasoning_len']} chars): {r['reasoning_content']}")

    # Test 3: Quiz generation (non-stream)
    print("\n[Test 3] Quiz generation (non-stream):")
    r = test_api("为知识点'导数的计算法则'出1道选择题，格式：Q: 题目 A) ... B) ... C) ... D) ... ANSWER: ... EXPLAIN: ...", stream=False)
    print(f"  Time: {r['time']:.2f}s")
    print(f"  content ({r['content_len']} chars): {r['content']}")
    print(f"  reasoning_content ({r['reasoning_len']} chars): {r['reasoning_content']}")

    # Test 4: Quiz generation (stream)
    print("\n[Test 4] Quiz generation (stream):")
    r = test_api("为知识点'极限存在准则'出1道选择题，格式：Q: 题目 A) ... B) ... C) ... D) ... ANSWER: ... EXPLAIN: ...", stream=True)
    print(f"  Time: {r['time']:.2f}s")
    print(f"  content ({r['content_len']} chars): {r['content']}")
    print(f"  reasoning_content ({r['reasoning_len']} chars): {r['reasoning_content']}")

    print("\n" + "=" * 60)
    print("Summary:")
    print("  If content is always empty -> MiMo puts everything in reasoning_content")
    print("  If content has quiz text -> MiMo separates thinking from output")
    print("  _extract_content should prefer content, fallback to reasoning_content")
    print("=" * 60)
