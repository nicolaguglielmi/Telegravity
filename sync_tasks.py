import asyncio
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def sync():
    server_params = StdioServerParameters(
        command="python3",
        args=["server.py"],
        env=None
    )
    
    tasks_ag_uplink = [
        "Implementing Task Management",
        "Building Telegram-Gateway MCP Server"
    ]
    
    tasks_ai_radar = [
        "Adding Source Links to Description",
        "Restart Pipeline and Publish",
        "Saving Gcloud Command",
        "Retry Publishing to Spreaker",
        "Voice Benchmark & Conversion",
        "Finalizing Podcast Pipeline",
        "Implementing Resumable Audio Generation",
        "Refactoring Main Python File",
        "Updating Audio Generation",
        "Updating Telegram Notifications",
        "Checking Generated Audio",
        "Configuring TTS Voice",
        "AI Radar Podcast Generator"
    ]

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Sync AG-Uplink
            res1 = await session.call_tool("import_conversations", {
                "workspace_name": "AG-Uplink",
                "conversations": tasks_ag_uplink
            })
            print(f"AG-Uplink sync: {res1.content[0].text}")
            
            # Sync AI-Radar
            res2 = await session.call_tool("import_conversations", {
                "workspace_name": "AI-Radar",
                "conversations": tasks_ai_radar
            })
            print(f"AI-Radar sync: {res2.content[0].text}")

if __name__ == "__main__":
    asyncio.run(sync())
