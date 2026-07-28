"""Backward-compatible alias for telegram_service.

This module used to contain its own full copy of the bot-token handling,
the /status and /help handlers, and the polling loop -- byte-for-byte
duplicated in telegram_service.py. That duplication is gone; everything now
lives in telegram_service.py and this module just re-exports it so existing
imports such as ``from telegram_manager import notify`` keep working.
"""
from telegram_service import notify, start_listener, status_cmd as status  # noqa: F401

if __name__ == "__main__":
    start_listener()
