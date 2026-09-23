"""Minimal client for the local OpenAI-compatible model gateway."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("btc_cycle_tracker.web.llm")


def _load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE pairs from a local .env into the environment (without
    overriding variables that are already set). Lets each deployment keep its
    gateway location private; the file is gitignored."""
    env_path = Path(path)
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError as exc:
        logger.warning("Could not read .env: %s", exc)


_load_dotenv()

DEFAULT_BASE_URL = os.environ.get("BTC_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
DEFAULT_MODEL = os.environ.get("BTC_LLM_MODEL", "auto")
DEFAULT_API_KEY = os.environ.get("BTC_LLM_API_KEY", "EMPTY")
DEFAULT_TIMEOUT = float(os.environ.get("BTC_LLM_TIMEOUT_SECONDS", "120"))


def extract_json_from_response(text: str, expected_keys: Optional[set[str]] = None) -> Optional[str]:
    """Extract the last valid JSON object from a response that may contain
    reasoning/thinking prose around it.

    If *expected_keys* is given, prefer blocks containing at least one of
    those keys.
    """
    text = text.strip()
    candidates: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "{":
            depth = 0
            for j in range(i, len(text)):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        block = text[i : j + 1]
                        try:
                            json.loads(block)
                            candidates.append(block)
                        except json.JSONDecodeError:
                            pass
                        break
            i += 1
        else:
            i += 1

    if not candidates:
        return None
    if expected_keys:
        for block in reversed(candidates):
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and any(k in data for k in expected_keys):
                return block
    return candidates[-1]


class LLMClient:
    """Chat-completions client for vLLM/Ollama/OpenAI-compatible servers."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str = DEFAULT_API_KEY,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self._resolved_model: str | None = None

    def resolve_model(self) -> str:
        """Return a concrete model id.

        ``model="auto"`` asks the gateway for its model list and uses the
        first id (vLLM exposes whatever single model it serves). The result
        is cached; a gateway without /models falls back to the literal
        "auto" (some servers accept it).
        """
        if self.model != "auto":
            return self.model
        if self._resolved_model:
            return self._resolved_model
        try:
            request = Request(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            with urlopen(request, timeout=min(self.timeout, 10)) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [m.get("id") for m in payload.get("data", []) if m.get("id")]
            if models:
                self._resolved_model = models[0]
                logger.info("LLM auto-resolved model: %s", self._resolved_model)
                return self._resolved_model
        except (HTTPError, URLError, json.JSONDecodeError, OSError) as exc:
            logger.warning("Model auto-resolution failed (%s); using 'auto'", exc)
        return "auto"

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> str:
        body = {
            "model": self.resolve_model(),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"LLM returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"LLM is unreachable at {self.base_url}: {exc}") from exc

        choices = payload.get("choices", [])
        if not choices:
            raise RuntimeError("LLM returned no choices.")
        message = choices[0].get("message", {})
        content = message.get("content", "") or message.get("reasoning", "")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM returned an empty response.")
        return content.strip()

    def generate(self, prompt: str, temperature: float = 0.2, max_tokens: int = 900) -> str:
        return self.chat([{"role": "user", "content": prompt}], temperature, max_tokens)
