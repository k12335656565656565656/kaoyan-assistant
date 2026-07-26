from services.llm_gateway import (
    LlmGatewayConfig,
    _apply_provider_options,
    extract_message_text,
    stream_chat_completion,
)


class _FakeResponse:
    def __init__(self, body):
        self.body = body
        self.read_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        if self.read_count:
            return b""
        self.read_count += 1
        return self.body


def test_extract_message_text_ignores_reasoning_content():
    message = {
        "reasoning_content": "先分析用户问题，再规划答案。",
        "content": "直接给用户看的正文。",
    }

    assert extract_message_text(message) == "直接给用户看的正文。"


def test_extract_message_text_does_not_fallback_to_reasoning_only():
    message = {"reasoning_content": "这是模型思考过程。"}

    assert extract_message_text(message) == ""


def test_deepseek_payload_disables_thinking_by_default(monkeypatch):
    monkeypatch.delenv("AI_DISABLE_THINKING", raising=False)
    payload = {"model": "deepseek-v4-flash"}

    _apply_provider_options(payload, "deepseek-v4-flash")

    assert payload["thinking"] == {"type": "disabled"}


def test_stream_chat_completion_ignores_empty_choices_events(monkeypatch):
    response = _FakeResponse(
        b'data: {"choices": []}\n\n'
        b'data: {"choices":[{"delta":{"content":"AOV"}}]}\n\n'
        b"data: [DONE]\n\n"
    )

    monkeypatch.setattr(
        "services.llm_gateway._request_json",
        lambda **_kwargs: response,
    )

    chunks = list(
        stream_chat_completion(
            messages=[{"role": "user", "content": "generate"}],
            config=LlmGatewayConfig(api_key="test-key", api_base="https://example.test/v1"),
        )
    )

    assert chunks == ["AOV"]
