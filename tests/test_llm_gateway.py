from services.llm_gateway import _apply_provider_options, extract_message_text


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
