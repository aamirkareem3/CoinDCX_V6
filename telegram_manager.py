import asyncio
import json
from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = "8740970132:AAEHz8Q4VRV_y-VXxthcYSbPcBL_16i6Rxs"
CHAT_ID = "851250514"

STATUS_FILE = "bot_status.json"


# -----------------------
# Send Notification
# -----------------------

async def send_message_async(message):
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=CHAT_ID, text=message)


def notify(message):
    try:
        asyncio.run(send_message_async(message))
    except Exception as e:
        print(e)


# -----------------------
# /status
# -----------------------

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # Only allow your chat ID
    if str(update.effective_chat.id) != CHAT_ID:
        return

    try:

        with open(STATUS_FILE, "r") as f:
            data = json.load(f)

        text = (
            "🤖 CoinDCX V6\n\n"
            f"🟢 Status : {data['status']}\n"
            f"📈 Mode : {data['mode']}\n"
            f"📦 Version : {data['version']}\n"
            f"🔍 Current Pair : {data['current_pair']}\n"
            f"💼 Open Trade : {data['open_trade']}\n"
            f"📊 Scan Count : {data['scan_count']}\n"
            f"🕒 Last Update : {data['last_update']}"
        )

    except Exception as e:

        text = f"❌ Error reading status\n\n{e}"

    await update.message.reply_text(text)


# -----------------------
# /help
# -----------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if str(update.effective_chat.id) != CHAT_ID:
        return

    await update.message.reply_text(
        "Available Commands\n\n"
        "/status\n"
        "/help"
    )


# -----------------------
# Main
# -----------------------

def start_listener():

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_command))

    print("Telegram listener started...")

    app.run_polling()


if __name__ == "__main__":
    start_listener()
