import os
import asyncio
from server import send_message, check_updates, bot

async def test_tools():
    print("Testing send_message tool...")
    result = await send_message(text="🛠️ Testing tool integration...")
    print(f"Result: {result}")
    
    print("\nTesting check_updates tool...")
    updates = await check_updates(limit=3)
    print("Recent updates:")
    for msg in updates:
        print(f" - {msg}")

if __name__ == "__main__":
    if not os.environ.get("TELEGRAM_TOKEN") or not os.environ.get("CHAT_ID"):
        print("Error: Environment variables NOT set.")
    else:
        asyncio.run(test_tools())
