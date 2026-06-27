"""Ollama API client with retry logic and timeout handling.

Wraps the local Ollama HTTP API, providing exponential backoff retry,
per-call timeout, and health check verification.
"""

import asyncio
import logging

import httpx

from app.models.artifacts import OllamaConfig

logger = logging.getLogger(__name__)


class OllamaUnavailableError(Exception):
    """Raised when Ollama server is unreachable after all retry attempts."""

    pass


class OllamaClient:
    """Wrapper for Ollama's local API with retry and fallback logic."""

    def __init__(self, config: OllamaConfig | None = None) -> None:
        self.config = config or OllamaConfig()
        self.base_url = self.config.base_url.rstrip("/")
        self.model = self.config.model
        self.timeout = self.config.timeout_seconds
        self.max_retries = self.config.max_retries
        self.retry_delay = self.config.retry_delay_seconds
        self.temperature = self.config.temperature

    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Generate text completion with exponential backoff retry logic.

        Args:
            prompt: The user prompt for text generation.
            system: Optional system prompt to guide model behavior.

        Returns:
            The generated text response from Ollama.

        Raises:
            OllamaUnavailableError: If all retry attempts are exhausted.
        """
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
            },
        }
        if system:
            payload["system"] = system

        response_data = await self._call_with_retry(
            method="POST",
            endpoint="/api/generate",
            payload=payload,
        )
        return response_data.get("response", "")

    async def chat(self, messages: list[dict], system: str | None = None) -> str:
        """Chat completion with exponential backoff retry logic.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            system: Optional system prompt prepended to the conversation.

        Returns:
            The assistant's response content.

        Raises:
            OllamaUnavailableError: If all retry attempts are exhausted.
        """
        chat_messages = list(messages)
        if system:
            chat_messages.insert(0, {"role": "system", "content": system})

        payload: dict = {
            "model": self.model,
            "messages": chat_messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
            },
        }

        response_data = await self._call_with_retry(
            method="POST",
            endpoint="/api/chat",
            payload=payload,
        )
        return response_data.get("message", {}).get("content", "")

    async def health_check(self) -> bool:
        """Check if Ollama server is responsive by hitting the /api/tags endpoint.

        Returns:
            True if the server responds successfully, False otherwise.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            return False

    async def _call_with_retry(
        self,
        method: str,
        endpoint: str,
        payload: dict,
    ) -> dict:
        """Execute an HTTP request with exponential backoff retry.

        Args:
            method: HTTP method (POST, GET, etc.).
            endpoint: API endpoint path (e.g., /api/generate).
            payload: JSON payload for the request body.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            OllamaUnavailableError: After all retries are exhausted.
        """
        url = f"{self.base_url}{endpoint}"
        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        json=payload,
                    )
                    response.raise_for_status()
                    return response.json()

            except (asyncio.TimeoutError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)
                    logger.warning(
                        "Ollama request timed out (attempt %d/%d). "
                        "Retrying in %.1fs...",
                        attempt + 1,
                        self.max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)

            except (httpx.ConnectError, ConnectionError, OSError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)
                    logger.warning(
                        "Ollama connection failed (attempt %d/%d): %s. "
                        "Retrying in %.1fs...",
                        attempt + 1,
                        self.max_retries,
                        str(e),
                        delay,
                    )
                    await asyncio.sleep(delay)

            except httpx.HTTPStatusError as e:
                # Don't retry on HTTP errors (4xx, 5xx) - these are not transient
                raise OllamaUnavailableError(
                    f"Ollama returned HTTP {e.response.status_code}: {e.response.text}"
                ) from e

        raise OllamaUnavailableError(
            f"Ollama failed after {self.max_retries} attempts: {last_exception}"
        )
