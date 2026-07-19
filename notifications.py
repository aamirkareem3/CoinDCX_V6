import asyncio
from telegram import Bot

BOT_TOKEN = "8740970132:AAEHz8Q4VRV_y-VXxthcYSbPcBL_16i6Rxs"
CHAT_ID = "851250514"


async def send_message(message: str):
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=CHAT_ID, text=message)


def notify(message: str):
    asyncio.run(send_message(message))


if __name__ == "__main__":
    notify(
        "🤖 CoinDCX V6\n\n"
        "✅ Telegram integration successful.\n"
        "Bot is ready."
    )
