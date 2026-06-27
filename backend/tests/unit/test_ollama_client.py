"""Unit tests for OllamaClient service.

Tests retry logic, timeout handling, health check, and error propagation.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.artifacts import OllamaConfig
from app.services.ollama_client import OllamaClient, OllamaUnavailableError


@pytest.fixture
def config():
    """Create a test config with short delays for fast tests."""
    return OllamaConfig(
        base_url="http://localhost:11434",
        model="llama3",
        timeout_seconds=5.0,
        max_retries=3,
        retry_delay_seconds=0.01,  # Very short delay for tests
        temperature=0.7,
    )


@pytest.fixture
def client(config):
    return OllamaClient(config=config)


class TestOllamaClientInit:
    def test_default_config(self):
        client = OllamaClient()
        assert client.base_url == "http://localhost:11434"
        assert client.model == "llama3"
        assert client.timeout == 120.0
        assert client.max_retries == 3
        assert client.retry_delay == 2.0

    def test_custom_config(self, config):
        client = OllamaClient(config=config)
        assert client.timeout == 5.0
        assert client.retry_delay == 0.01

    def test_trailing_slash_stripped(self):
        config = OllamaConfig(base_url="http://localhost:11434/")
        client = OllamaClient(config=config)
        assert client.base_url == "http://localhost:11434"


class TestGenerate:
    @pytest.mark.asyncio
    async def test_generate_success(self, client):
        mock_response = httpx.Response(
            200,
            json={"response": "Hello, world!"},
            request=httpx.Request("POST", "http://localhost:11434/api/generate"),
        )
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response):
            result = await client.generate("Say hello")
            assert result == "Hello, world!"

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self, client):
        mock_response = httpx.Response(
            200,
            json={"response": "I am helpful."},
            request=httpx.Request("POST", "http://localhost:11434/api/generate"),
        )
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response) as mock_req:
            result = await client.generate("Who are you?", system="You are helpful.")
            assert result == "I am helpful."
            # Verify system was passed in the payload
            call_kwargs = mock_req.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["system"] == "You are helpful."

    @pytest.mark.asyncio
    async def test_generate_empty_response(self, client):
        mock_response = httpx.Response(
            200,
            json={},
            request=httpx.Request("POST", "http://localhost:11434/api/generate"),
        )
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response):
            result = await client.generate("test")
            assert result == ""


class TestChat:
    @pytest.mark.asyncio
    async def test_chat_success(self, client):
        mock_response = httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "Hi there!"}},
            request=httpx.Request("POST", "http://localhost:11434/api/chat"),
        )
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response):
            messages = [{"role": "user", "content": "Hello"}]
            result = await client.chat(messages)
            assert result == "Hi there!"

    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self, client):
        mock_response = httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "response"}},
            request=httpx.Request("POST", "http://localhost:11434/api/chat"),
        )
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response) as mock_req:
            messages = [{"role": "user", "content": "test"}]
            await client.chat(messages, system="Be concise")
            call_kwargs = mock_req.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            # System message should be first in messages list
            assert payload["messages"][0] == {"role": "system", "content": "Be concise"}
            assert payload["messages"][1] == {"role": "user", "content": "test"}

    @pytest.mark.asyncio
    async def test_chat_empty_response(self, client):
        mock_response = httpx.Response(
            200,
            json={"message": {}},
            request=httpx.Request("POST", "http://localhost:11434/api/chat"),
        )
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response):
            result = await client.chat([{"role": "user", "content": "test"}])
            assert result == ""


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retries_on_timeout(self, client):
        """Should retry on timeout and eventually raise OllamaUnavailableError."""
        with patch(
            "httpx.AsyncClient.request",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("timed out"),
        ):
            with pytest.raises(OllamaUnavailableError, match="failed after 3 attempts"):
                await client.generate("test")

    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self, client):
        """Should retry on connection error and eventually raise."""
        with patch(
            "httpx.AsyncClient.request",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("connection refused"),
        ):
            with pytest.raises(OllamaUnavailableError, match="failed after 3 attempts"):
                await client.generate("test")

    @pytest.mark.asyncio
    async def test_succeeds_after_retries(self, client):
        """Should succeed if a retry eventually works."""
        mock_response = httpx.Response(
            200,
            json={"response": "success"},
            request=httpx.Request("POST", "http://localhost:11434/api/generate"),
        )
        mock_request = AsyncMock(
            side_effect=[
                httpx.ConnectError("fail 1"),
                httpx.TimeoutException("fail 2"),
                mock_response,
            ]
        )
        with patch("httpx.AsyncClient.request", mock_request):
            result = await client.generate("test")
            assert result == "success"
            assert mock_request.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_http_error(self, client):
        """Should not retry on HTTP status errors (4xx/5xx)."""
        mock_response = httpx.Response(
            500,
            text="Internal Server Error",
            request=httpx.Request("POST", "http://localhost:11434/api/generate"),
        )
        with patch(
            "httpx.AsyncClient.request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            with pytest.raises(OllamaUnavailableError, match="HTTP 500"):
                await client.generate("test")
            # Should only be called once - no retries for HTTP errors
            assert mock_req.call_count == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self, client):
        """Verify exponential backoff timing: delay * 2^attempt."""
        sleep_calls = []
        original_sleep = asyncio.sleep

        async def mock_sleep(delay):
            sleep_calls.append(delay)

        with patch(
            "httpx.AsyncClient.request",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("fail"),
        ):
            with patch("asyncio.sleep", side_effect=mock_sleep):
                with pytest.raises(OllamaUnavailableError):
                    await client.generate("test")

        # With retry_delay=0.01: delays should be 0.01*2^0=0.01, 0.01*2^1=0.02
        assert len(sleep_calls) == 2  # 3 attempts, 2 sleeps between them
        assert sleep_calls[0] == pytest.approx(0.01)
        assert sleep_calls[1] == pytest.approx(0.02)


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_success(self, client):
        mock_response = httpx.Response(
            200,
            json={"models": []},
            request=httpx.Request("GET", "http://localhost:11434/api/tags"),
        )
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_server_down(self, client):
        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("connection refused"),
        ):
            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_health_check_timeout(self, client):
        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("timed out"),
        ):
            result = await client.health_check()
            assert result is False
