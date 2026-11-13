"""LLM-backed summarization behind a feature flag.

Any OpenAI-compatible chat-completions endpoint works. When no key is
configured, `NullSummarizer` keeps the rest of the pipeline running; jobs
simply complete without a summary instead of failing.
"""

import logging
from typing import Protocol

import httpx

from sokhan.config import get_settings

logger = logging.getLogger(__name__)

_MAX_SUMMARY_INPUT_CHARS = 8000
_SYSTEM_PROMPT = (
    "You are a Persian-speaking assistant. Summarize the following transcript "
    "in exactly three short sentences, in fluent Persian. Do not use lists or "
    "headings. Reply with the summary only."
)


class Summarizer(Protocol):
    def summarize(self, text: str) -> str | None: ...


class NullSummarizer:
    def summarize(self, text: str) -> str | None:
        return None


class OpenAICompatibleSummarizer:
    def __init__(
        self, api_base: str, api_key: str, model: str, timeout_seconds: float = 60.0
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def summarize(self, text: str) -> str | None:
        if not text.strip():
            return None
        payload = {
            "model": self.model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text[:_MAX_SUMMARY_INPUT_CHARS]},
            ],
        }
        try:
            response = httpx.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            logger.warning("summary request failed: %s", exc)
            return None
        if not isinstance(content, str):
            return None
        return content.strip() or None


def get_summarizer() -> Summarizer:
    settings = get_settings()
    if (
        settings.summary_enabled
        and settings.llm_api_key
        and settings.llm_api_base
        and settings.llm_model
    ):
        return OpenAICompatibleSummarizer(
            settings.llm_api_base, settings.llm_api_key, settings.llm_model
        )
    return NullSummarizer()
