"""Single source of truth for Telegram bot credentials.

Previously the same bot token was hardcoded in three files
(telegram_manager.py, telegram_service.py, notifications.py) and the same
chat id was hardcoded in four files (those three plus bot_controller/auth.py).
That meant rotating a leaked token required editing multiple files and it was
easy for one copy to drift from the others.

Every value here can be overridden with an environment variable so the
token no longer has to live in source control going forward. The literals
kept as defaults are the values already in use, so existing deployments
that don't set the environment variables keep working exactly as before.
"""
import os

BOT_TOKEN: str = os.environ.get(
    "TELEGRAM_BOT_TOKEN", "BOT_TOKEN"
)
CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "CHAT_ID")
