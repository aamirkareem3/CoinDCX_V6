"""Canonical Telegram integration: outbound notifications and the inbound command bot.

This is now the single implementation of Telegram messaging for the bot.
`telegram_manager.py` and `notifications.py` are kept only as thin
backward-compatible shims that import from here, so existing code that does
`from telegram_manager import notify` or `import notifications` keeps working
without a second (or third) copy of the bot-token handling and message logic.
"""
import asyncio

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

import journal
import status_manager
from telegram_config import BOT_TOKEN, CHAT_ID
from bot_controller.commands.control import help_cmd


async def _send_message_async(message: str) -> None:
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=CHAT_ID, text=message)


def notify(message: str) -> None:
    """Fire-and-forget outbound Telegram notification.

    Never raises: a failed notification must not interrupt the trading loop.
    A failure is both printed AND written to events.jsonl -- printing alone
    is easy to miss when the process runs as a systemd service with its
    console output rotated/discarded, so this is not allowed to be a silent
    failure.
    """
    try:
        asyncio.run(_send_message_async(message))
    except Exception as exc:  # noqa: BLE001 - notification failures are non-fatal by design
        print(f"[telegram_service] notify failed: {exc!r}")
        try:
            journal.event("v5_telegram_notify_failed", {"error": repr(exc), "message": message})
        except Exception:  # noqa: BLE001 - the journal write itself must never raise here
            pass


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status by rendering the current bot_status.json snapshot."""
    if str(update.effective_chat.id) != CHAT_ID:
        return
    try:
        data = status_manager.read_status()
    except Exception as exc:  # noqa: BLE001 - a bad status file must not crash the bot
        await update.message.reply_text(f"❌ Error reading status\n\n{exc}")
        return

    if data is None:
        text = "❌ No status snapshot available yet."
    else:
        text = (
            "🤖 CoinDCX V6\n\n"
            f"🟢 Status : {data.get('status')}\n"
            f"📈 Mode : {data.get('mode')}\n"
            f"📦 Version : {data.get('version')}\n"
            f"🔍 Current Pair : {data.get('current_pair')}\n"
            f"💼 Open Trade : {data.get('open_trade')}\n"
            f"📊 Scan Count : {data.get('scan_count')}\n"
            f"🕒 Last Update : {data.get('last_update')}"
        )
    await update.message.reply_text(text)


def start_listener() -> None:
    """Run the blocking Telegram command-polling loop."""
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    print("Telegram listener started...")
    app.run_polling()


if __name__ == "__main__":
    start_listener()
