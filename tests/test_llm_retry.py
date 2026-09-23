from utils import llm_retry


class FakeRateLimitError(Exception):
    pass


class AlwaysRateLimitedLlm:
    def __init__(self):
        self.calls = 0

    def invoke(self, _messages):
        self.calls += 1
        raise FakeRateLimitError("Try again in 0.01s")


def test_rate_limit_retries_then_returns_a_safe_message(monkeypatch):
    llm = AlwaysRateLimitedLlm()
    monkeypatch.setattr(llm_retry, "RateLimitError", FakeRateLimitError)
    monkeypatch.setattr(llm_retry.time, "sleep", lambda _delay: None)

    result = llm_retry.invoke_with_retry(llm, ["message"], max_retries=2)

    assert llm.calls == 3
    assert result.content == llm_retry.RATE_LIMIT_MESSAGE


def test_rate_limit_delay_uses_provider_hint(monkeypatch):
    monkeypatch.setattr(llm_retry, "RateLimitError", FakeRateLimitError)

    assert llm_retry._rate_limit_delay(
        FakeRateLimitError("Please try again in 1.98s"), 0
    ) == 1.98


def test_chat_service_returns_a_normal_response_when_graph_is_rate_limited(monkeypatch):
    from services import chat_service

    class FakeRateLimitError(Exception):
        pass

    class FakeGraph:
        def invoke(self, _input, config):
            raise FakeRateLimitError("rate limited")

    class User:
        id = 7
        full_name = "Test User"
        email = "test@example.com"

    monkeypatch.setattr(chat_service, "RateLimitError", FakeRateLimitError)
    monkeypatch.setattr(chat_service, "get_app", lambda: FakeGraph())
    monkeypatch.setattr(
        chat_service.conv_crud, "get_or_create_conversation", lambda *_args: object()
    )
    monkeypatch.setattr(chat_service.conv_crud, "set_title_if_empty", lambda *_args: None)
    monkeypatch.setattr(chat_service, "build_memory_context", lambda *_args: "")

    result = chat_service.send_message(object(), User(), "thread-1", "hello")

    assert result["thread_id"] == "thread-1"
    assert result["route"] == ""
    assert result["answer"] == "The assistant is temporarily busy due to an AI provider rate limit. Please try again in a few seconds."
