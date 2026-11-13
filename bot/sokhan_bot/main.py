"""Bot entrypoint: long polling with aiogram 3.

The import is always safe without a token (handy for tests and lint); only
`main()` requires TELEGRAM_BOT_TOKEN to be set.
"""

import logging
import sys

from aiogram import Bot, Dispatcher

from sokhan_bot.client import SokhanClient
from sokhan_bot.config import load_settings
from sokhan_bot.handlers import Handlers
from sokhan_bot.store import TokenStore

logger = logging.getLogger("sokhan-bot")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    settings = load_settings()
    if not settings.telegram_bot_token:
        print(
            "TELEGRAM_BOT_TOKEN is not set. Export it first: export TELEGRAM_BOT_TOKEN=...",
            file=sys.stderr,
        )
        raise SystemExit(1)

    bot = Bot(settings.telegram_bot_token)
    dispatcher = Dispatcher()
    client = SokhanClient(settings)
    store = TokenStore("data/bot-tokens.json")
    dispatcher.include_router(Handlers(client, store).router)

    logger.info(
        "sokhan bot starting (api=%s, web=%s)",
        settings.api_base_url,
        settings.web_base_url,
    )
    try:
        dispatcher.run_polling(bot)
    finally:
        client.close()


if __name__ == "__main__":
    main()
