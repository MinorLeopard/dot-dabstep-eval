"""Tests for LiveDotClient — all using mocked httpx responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.dot_client import (
    DotEmptyResponseError,
    DotHttpError,
    DotResponse,
    LiveDotClient,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def env_vars(monkeypatch):
    """Set required env vars for LiveDotClient construction."""
    monkeypatch.setenv("DOT_API_KEY", "test-key-123")
    monkeypatch.setenv("DOT_BASE_URL", "https://test.getdot.ai")


def _mock_response(status_code: int = 200, json_data: dict | None = None, text: str = ""):
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text or str(json_data)
    return resp


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestLiveDotClientInit:
    def test_requires_api_key(self, monkeypatch):
        monkeypatch.delenv("DOT_API_KEY", raising=False)
        monkeypatch.delenv("DOT_BASE_URL", raising=False)
        # Stub load_dotenv so a real .env file doesn't inject vars back
        _fake_dotenv = type("M", (), {"load_dotenv": staticmethod(lambda: None)})()
        with patch.dict("sys.modules", {"dotenv": _fake_dotenv}):
            with pytest.raises(ValueError, match="DOT_API_KEY"):
                LiveDotClient()

    def test_requires_base_url(self, monkeypatch):
        monkeypatch.setenv("DOT_API_KEY", "key")
        monkeypatch.delenv("DOT_BASE_URL", raising=False)
        _fake_dotenv = type("M", (), {"load_dotenv": staticmethod(lambda: None)})()
        with patch.dict("sys.modules", {"dotenv": _fake_dotenv}):
            with pytest.raises(ValueError, match="DOT_BASE_URL"):
                LiveDotClient()

    def test_accepts_explicit_params(self, monkeypatch):
        monkeypatch.delenv("DOT_API_KEY", raising=False)
        monkeypatch.delenv("DOT_BASE_URL", raising=False)
        with patch("src.dot_client.httpx.Client"):
            client = LiveDotClient(api_key="explicit-key", base_url="https://example.com")
        assert client.api_key == "explicit-key"
        assert client.base_url == "https://example.com"

    def test_reads_env_vars(self, env_vars):
        with patch("src.dot_client.httpx.Client"):
            client = LiveDotClient()
        assert client.api_key == "test-key-123"
        assert client.base_url == "https://test.getdot.ai"

    def test_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("DOT_API_KEY", "key")
        monkeypatch.setenv("DOT_BASE_URL", "https://example.com/")
        with patch("src.dot_client.httpx.Client"):
            client = LiveDotClient()
        assert client.base_url == "https://example.com"

    def test_invalid_mode_raises(self, env_vars):
        with pytest.raises(ValueError, match="mode"):
            with patch("src.dot_client.httpx.Client"):
                LiveDotClient(mode="invalid")

    def test_mode_ask(self, env_vars):
        with patch("src.dot_client.httpx.Client"):
            client = LiveDotClient(mode="ask")
        assert client.mode == "ask"

    def test_mode_agentic_default(self, env_vars):
        with patch("src.dot_client.httpx.Client"):
            client = LiveDotClient()
        assert client.mode == "agentic"


# ---------------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------------


class TestHeaders:
    def test_both_api_key_headers(self, env_vars):
        with patch("src.dot_client.httpx.Client"):
            client = LiveDotClient()
        headers = client._build_headers()
        assert headers["X-API-KEY"] == "test-key-123"
        assert headers["API-KEY"] == "test-key-123"
        assert headers["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# _extract_assistant_text
# ---------------------------------------------------------------------------


class TestExtractAssistantText:
    def test_messages_array(self):
        data = {
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "FINAL_ANSWER: 42"},
            ]
        }
        assert LiveDotClient._extract_assistant_text(data) == "FINAL_ANSWER: 42"

    def test_response_field(self):
        assert LiveDotClient._extract_assistant_text({"response": "ok"}) == "ok"

    def test_text_field(self):
        assert LiveDotClient._extract_assistant_text({"text": "ok"}) == "ok"

    def test_explanation_field(self):
        """The /api/ask endpoint returns the answer in 'explanation'."""
        data = {"explanation": "The answer is NL", "role": "assistant"}
        assert LiveDotClient._extract_assistant_text(data) == "The answer is NL"

    def test_answer_field(self):
        assert LiveDotClient._extract_assistant_text({"answer": "ok"}) == "ok"

    def test_empty_messages(self):
        assert LiveDotClient._extract_assistant_text({"messages": []}) == ""

    def test_only_user_messages(self):
        data = {"messages": [{"role": "user", "content": "hello"}]}
        assert LiveDotClient._extract_assistant_text(data) == ""

    def test_empty_dict(self):
        assert LiveDotClient._extract_assistant_text({}) == ""

    def test_prefers_messages_over_response(self):
        data = {
            "messages": [{"role": "assistant", "content": "from messages"}],
            "response": "from response field",
        }
        assert LiveDotClient._extract_assistant_text(data) == "from messages"

    def test_whitespace_only_skipped(self):
        data = {"messages": [{"role": "assistant", "content": "   "}]}
        assert LiveDotClient._extract_assistant_text(data) == ""

    def test_last_assistant_message_used(self):
        data = {
            "messages": [
                {"role": "assistant", "content": "first"},
                {"role": "user", "content": "follow up"},
                {"role": "assistant", "content": "second"},
            ]
        }
        assert LiveDotClient._extract_assistant_text(data) == "second"


# ---------------------------------------------------------------------------
# query() — mocked HTTP, immediate response (no polling)
# ---------------------------------------------------------------------------


class TestQuery:
    def test_successful_query(self, env_vars):
        """Happy path: POST returns immediate assistant response."""
        post_resp = _mock_response(200, {
            "messages": [{"role": "assistant", "content": "FINAL_ANSWER: 42"}]
        })

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient()
            result = client.query("What is 6*7?", chat_id="test_chat")

        assert isinstance(result, DotResponse)
        assert "FINAL_ANSWER: 42" in result.text
        assert result.usage is not None
        assert "latency_ms" in result.usage
        assert result.usage["chat_id"] == "test_chat"
        mock_inst.post.assert_called_once()

    def test_payload_contains_chat_id_and_messages(self, env_vars):
        """The outgoing JSON must include chat_id and messages array."""
        post_resp = _mock_response(200, {"response": "ok"})

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient()
            client.query("my test prompt", chat_id="run1_q42")

        _, kwargs = mock_inst.post.call_args
        payload = kwargs["json"]
        assert payload["chat_id"] == "run1_q42"
        assert payload["messages"] == [{"role": "user", "content": "my test prompt"}]

    def test_auto_generates_chat_id_when_none(self, env_vars):
        """If no chat_id is passed, one is auto-generated."""
        post_resp = _mock_response(200, {"response": "ok"})

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient()
            result = client.query("test")

        _, kwargs = mock_inst.post.call_args
        payload = kwargs["json"]
        assert "chat_id" in payload
        assert len(payload["chat_id"]) > 0
        assert result.usage["chat_id"] == payload["chat_id"]

    def test_post_non_200_raises_http_error(self, env_vars):
        post_resp = _mock_response(422, text="Unprocessable Entity")

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient()
            with pytest.raises(DotHttpError, match="422"):
                client.query("test", chat_id="c1")

    def test_empty_response_raises(self, env_vars):
        """If the response has no assistant text, raise DotEmptyResponseError."""
        post_resp = _mock_response(200, {"messages": []})

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient()
            with pytest.raises(DotEmptyResponseError):
                client.query("test", chat_id="c1")

    def test_uses_agentic_endpoint(self, env_vars):
        post_resp = _mock_response(200, {
            "messages": [{"role": "assistant", "content": "ok"}]
        })

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient(mode="agentic")
            client.query("test", chat_id="c1")

        args, _ = mock_inst.post.call_args
        assert args[0] == "/api/agentic"

    def test_uses_ask_endpoint(self, env_vars):
        post_resp = _mock_response(200, {
            "messages": [{"role": "assistant", "content": "ok"}]
        })

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient(mode="ask")
            client.query("test", chat_id="c1")

        args, _ = mock_inst.post.call_args
        assert args[0] == "/api/ask"

    def test_agentic_list_response_extracted(self, env_vars):
        """The /api/agentic endpoint returns a list; assistant content is extracted."""
        api_response = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "x"}}]},
            {"role": "tool", "content": "tool result"},
            {"role": "assistant", "content": "FINAL_ANSWER: NL"},
        ]
        post_resp = _mock_response(200, json_data=api_response)
        # Override .json() to return the list directly
        post_resp.json.return_value = api_response

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient()
            result = client.query("test", chat_id="c1")

        assert result.text == "FINAL_ANSWER: NL"

    def test_ask_dict_response_extracted(self, env_vars):
        """The /api/ask endpoint returns a dict with 'explanation'."""
        api_response = {
            "explanation": "The answer is 42.",
            "role": "assistant",
            "logs": "some logs",
        }
        post_resp = _mock_response(200, json_data=api_response)

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient(mode="ask")
            result = client.query("test", chat_id="c1")

        assert result.text == "The answer is 42."

    def test_no_get_calls_made(self, env_vars):
        """Verify no polling — only a single POST, no GET."""
        post_resp = _mock_response(200, {
            "messages": [{"role": "assistant", "content": "done"}]
        })

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient()
            client.query("test", chat_id="c1")

        mock_inst.post.assert_called_once()
        mock_inst.get.assert_not_called()

    def test_latency_in_usage(self, env_vars):
        post_resp = _mock_response(200, {"response": "FINAL_ANSWER: 7"})

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient()
            result = client.query("test", chat_id="c1")

        assert isinstance(result.usage["latency_ms"], int)
        assert result.usage["latency_ms"] >= 0
