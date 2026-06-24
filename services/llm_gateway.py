from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class LlmGatewayConfig:
    api_key: str
    api_base: str
    default_model: str = "mimo-v2.5"


def load_gateway_config() -> LlmGatewayConfig:
    return LlmGatewayConfig(
        api_key=os.environ.get("AI_API_KEY", "").strip(),
        api_base=os.environ.get("AI_API_BASE", "https://api.xiaomimimo.com/v1").strip(),
        default_model=os.environ.get("AI_MODEL", "mimo-v2.5").strip() or "mimo-v2.5",
    )


def extract_message_text(message: dict) -> str:
    if not isinstance(message, dict):
        return ""
    return (
        message.get("content")
        or message.get("reasoning_content")
        or message.get("text")
        or ""
    )


def _build_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _should_retry_http(error: urllib.error.HTTPError) -> bool:
    return error.code in {408, 409, 429, 500, 502, 503, 504, 529}


def _retry_delay(attempt: int, retry_after: float | None = None) -> float:
    if retry_after is not None:
        return retry_after
    base = min(0.5 * (2 ** attempt), 8.0)
    return base + random.uniform(0, base * 0.25)


def _request_json(
    *,
    payload: dict,
    timeout: int,
    stream: bool,
    config: LlmGatewayConfig,
    retries: int,
):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{config.api_base}/chat/completions",
        data=body,
        headers=_build_headers(config.api_key),
        method="POST",
    )

    last_error = None
    for attempt in range(retries + 1):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if attempt >= retries or not _should_retry_http(exc):
                raise
            retry_after = None
            if exc.headers:
                try:
                    retry_after = float(exc.headers.get("Retry-After"))
                except (TypeError, ValueError):
                    retry_after = None
            time.sleep(_retry_delay(attempt, retry_after))
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt >= retries:
                raise
            time.sleep(_retry_delay(attempt))
    if last_error:
        raise last_error
    raise RuntimeError("LLM request failed unexpectedly")


def chat_completion_text(
    *,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.3,
    timeout: int = 60,
    config: LlmGatewayConfig | None = None,
    retries: int = 2,
) -> str:
    message = chat_completion_message(
        messages=messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        config=config,
        retries=retries,
    )
    return extract_message_text(message)


def chat_completion_message(
    *,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.3,
    timeout: int = 60,
    config: LlmGatewayConfig | None = None,
    retries: int = 2,
) -> dict:
    config = config or load_gateway_config()
    payload = {
        "model": model or config.default_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    with _request_json(payload=payload, timeout=timeout, stream=False, config=config, retries=retries) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]


def simple_prompt_completion(
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.3,
    timeout: int = 60,
    config: LlmGatewayConfig | None = None,
    retries: int = 2,
) -> str:
    return chat_completion_text(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        config=config,
        retries=retries,
    )


def stream_chat_completion(
    *,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.3,
    timeout: int = 180,
    config: LlmGatewayConfig | None = None,
    retries: int = 1,
) -> Iterable[str]:
    config = config or load_gateway_config()
    payload = {
        "model": model or config.default_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }

    with _request_json(payload=payload, timeout=timeout, stream=True, config=config, retries=retries) as resp:
        buffer = ""
        while True:
            chunk = resp.read(1024)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="ignore")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                raw_payload = line[6:]
                if raw_payload == "[DONE]":
                    return
                try:
                    obj = json.loads(raw_payload)
                except json.JSONDecodeError:
                    continue
                delta_obj = obj.get("choices", [{}])[0].get("delta", {})
                delta = (
                    delta_obj.get("content")
                    or delta_obj.get("reasoning_content")
                    or ""
                )
                if delta:
                    yield delta
