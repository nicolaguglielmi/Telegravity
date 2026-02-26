import os
import asyncio
from telegram import Bot
from telegram.error import TelegramError

async def test_connection():
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    
    if not token or not chat_id:
        print("Error: TELEGRAM_TOKEN or CHAT_ID not set in environment.")
        return

    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        print(f"Success! Bot info: @{me.username} ({me.first_name})")
        
        # Test basic message sending
        print(f"Testing message sending to chat {chat_id}...")
        await bot.send_message(chat_id=chat_id, text="🚀 Test connection script starting...")
        print("Success! Message sent.")
        
    except TelegramError as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
