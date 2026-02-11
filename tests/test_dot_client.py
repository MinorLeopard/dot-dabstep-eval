"""Tests for LiveDotClient — all using mocked httpx responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.dot_client import (
    DotHttpError,
    DotResponse,
    DotTimeoutError,
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
        with pytest.raises(ValueError, match="DOT_API_KEY"):
            LiveDotClient()

    def test_requires_base_url(self, monkeypatch):
        monkeypatch.setenv("DOT_API_KEY", "key")
        monkeypatch.delenv("DOT_BASE_URL", raising=False)
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
# query() — mocked HTTP
# ---------------------------------------------------------------------------


class TestQuery:
    def test_successful_query(self, env_vars):
        """Happy path: POST returns chat_id, first poll returns assistant text."""
        post_resp = _mock_response(200, {"chat_id": "chat_abc"})
        get_resp = _mock_response(200, {
            "messages": [{"role": "assistant", "content": "FINAL_ANSWER: 42"}]
        })

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            mock_inst.get.return_value = get_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient(poll_interval=0.01)
            result = client.query("What is 6*7?")

        assert isinstance(result, DotResponse)
        assert "FINAL_ANSWER: 42" in result.text
        assert result.usage is not None
        assert "latency_ms" in result.usage
        assert "chat_id" in result.usage
        assert result.usage["chat_id"] == "chat_abc"
        mock_inst.post.assert_called_once()
        mock_inst.get.assert_called_once()

    def test_post_non_200_raises_http_error(self, env_vars):
        post_resp = _mock_response(500, text="Internal Server Error")

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient(poll_interval=0.01)
            with pytest.raises(DotHttpError, match="500"):
                client.query("test")

    def test_missing_chat_id_raises_http_error(self, env_vars):
        post_resp = _mock_response(200, {"some_other_field": "value"})

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient(poll_interval=0.01)
            with pytest.raises(DotHttpError, match="chat_id"):
                client.query("test")

    def test_poll_timeout_raises(self, env_vars):
        post_resp = _mock_response(200, {"chat_id": "chat_abc"})
        get_resp = _mock_response(200, {"messages": []})

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            mock_inst.get.return_value = get_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient(poll_timeout=0.05, poll_interval=0.01)
            with pytest.raises(DotTimeoutError):
                client.query("test")

    def test_poll_non_200_raises_http_error(self, env_vars):
        post_resp = _mock_response(200, {"chat_id": "chat_abc"})
        get_resp = _mock_response(502, text="Bad Gateway")

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            mock_inst.get.return_value = get_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient(poll_interval=0.01)
            with pytest.raises(DotHttpError, match="502"):
                client.query("test")

    def test_polls_until_response_appears(self, env_vars):
        """Simulate 2 empty polls then a successful response."""
        post_resp = _mock_response(200, {"chat_id": "chat_abc"})
        empty_resp = _mock_response(200, {"messages": []})
        full_resp = _mock_response(200, {
            "messages": [{"role": "assistant", "content": "FINAL_ANSWER: done"}]
        })

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            mock_inst.get.side_effect = [empty_resp, empty_resp, full_resp]
            MockClient.return_value = mock_inst

            client = LiveDotClient(poll_interval=0.01, poll_timeout=5.0)
            result = client.query("test")

        assert "FINAL_ANSWER: done" in result.text
        assert mock_inst.get.call_count == 3
        assert result.usage["retries"] == 2

    def test_uses_agentic_endpoint(self, env_vars):
        post_resp = _mock_response(200, {"chat_id": "c1"})
        get_resp = _mock_response(200, {
            "messages": [{"role": "assistant", "content": "ok"}]
        })

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            mock_inst.get.return_value = get_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient(mode="agentic", poll_interval=0.01)
            client.query("test")

        args, kwargs = mock_inst.post.call_args
        assert args[0] == "/api/agentic"

    def test_uses_ask_endpoint(self, env_vars):
        post_resp = _mock_response(200, {"chat_id": "c1"})
        get_resp = _mock_response(200, {
            "messages": [{"role": "assistant", "content": "ok"}]
        })

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            mock_inst.get.return_value = get_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient(mode="ask", poll_interval=0.01)
            client.query("test")

        args, kwargs = mock_inst.post.call_args
        assert args[0] == "/api/ask"

    def test_prompt_sent_in_payload(self, env_vars):
        post_resp = _mock_response(200, {"chat_id": "c1"})
        get_resp = _mock_response(200, {"response": "ok"})

        with patch("src.dot_client.httpx.Client") as MockClient:
            mock_inst = MagicMock()
            mock_inst.post.return_value = post_resp
            mock_inst.get.return_value = get_resp
            MockClient.return_value = mock_inst

            client = LiveDotClient(poll_interval=0.01)
            client.query("my test prompt")

        _, kwargs = mock_inst.post.call_args
        assert kwargs["json"]["prompt"] == "my test prompt"
