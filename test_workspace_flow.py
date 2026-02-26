import os
import asyncio
from server import register_workspaces, check_updates

async def test_workspace_flow():
    print("Step 1: Registering workspaces...")
    reg_result = await register_workspaces(names=["AG-Uplink (nicolaguglielmi/AG-Uplink)"])
    print(reg_result)
    
    print("\nStep 2: Checking for /workspaces command...")
    print("Please send '/workspaces' to the bot in Telegram now.")
    
    # Poll for a bit
    for i in range(10):
        print(f"Polling {i+1}/10...")
        updates = await check_updates(limit=1)
        if any("/workspaces" in msg for msg in updates):
            print("Found /workspaces command and handled it!")
            break
        await asyncio.sleep(3)
    else:
        print("Timeout: No /workspaces command found.")

if __name__ == "__main__":
    if not os.environ.get("TELEGRAM_TOKEN") or not os.environ.get("CHAT_ID"):
        print("Error: Environment variables NOT set.")
    else:
        asyncio.run(test_workspace_flow())
