import os
import asyncio
from server import telegram_inbox

async def test_resource():
    print("Testing telegram://inbox resource...")
    content = await telegram_inbox()
    print("Resource Content:")
    print(content)

if __name__ == "__main__":
    if not os.environ.get("TELEGRAM_TOKEN") or not os.environ.get("CHAT_ID"):
        print("Error: Environment variables NOT set.")
    else:
        asyncio.run(test_resource())
