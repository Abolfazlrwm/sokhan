"""Bot settings read from environment variables (no token at import time)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BotSettings:
    telegram_bot_token: str
    api_base_url: str
    web_base_url: str


def load_settings() -> BotSettings:
    return BotSettings(
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        api_base_url=os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/"),
        web_base_url=os.environ.get("WEB_BASE_URL", "http://localhost:3000").rstrip("/"),
    )
