from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from src.bot import ScreenerBot


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # Telegram library bawaan agak verbose, redam.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    if not os.getenv("TELEGRAM_BOT_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID"):
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID harus di-set di .env"
        )

    ScreenerBot().run()


if __name__ == "__main__":
    main()
