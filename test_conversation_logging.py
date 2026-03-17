import asyncio
import os
import server

async def run_test():
    print("Testing conversation logging...")
    
    # 1. Setup mock workspace
    server.CURRENT_WORKSPACE = "TestWorkspace"
    server.WORKSPACE_CONVERSATIONS["TestWorkspace"] = []
    
    # Ensure log file is gone first to test creation
    if os.path.exists(server.CONVERSATIONS_LOG_FILE):
        os.remove(server.CONVERSATIONS_LOG_FILE)
        print("Removed existing conversations.log")

    # 2. Trigger conversation update
    print("Calling update_conversation...")
    result = await server.update_conversation(
        conv_desc="Test Issue #1",
        status="active",
        log_title="Fixed a minor bug in update function",
        summary="Restored missing indented block and added log call",
        files_edited=["server.py"],
        progress_steps=["Analyzed file", "Found gap", "Applied replacement"]
    )
    print(f"Result: {result}")

    # 3. Test send_message logging
    print("\nCalling send_message...")
    class MockBot:
        async def send_message(self, **kwargs):
            pass
    server.bot = MockBot()
    server.CHAT_ID = "12345"
    
    await server.send_message(text="Hello from Agent testing framework")
    
    # 4. Test check_telegram_updates logging (Simulation)
    print("\nSimulating incoming message is logged...")
    # In the loop: msg_log = f"[{timestamp}] 👤 {sender}: {text}"
    simulated_msg_log = "[17:05:00] 👤 Nicola: Simulation message"
    server.save_conversation_log(simulated_msg_log)

    # 5. Read and Verify All
    print("\n--- conversations.log content ---")
    if os.path.exists(server.CONVERSATIONS_LOG_FILE):
        with open(server.CONVERSATIONS_LOG_FILE, "r") as f:
            content = f.read()
            print(content)
        
        # Verify all streams
        update_ok = "🛰️ [Update]" in content and "Test Issue #1" in content
        agent_ok = "Hello from Agent testing framework" in content
        sim_ok = "Simulation message" in content

        if update_ok and agent_ok and sim_ok:
             print("\n✅ ALL VERIFICATION SUCCESS: All log streams working.")
        else:
             print("\n❌ VERIFICATION FAILED: Missing entries.")
             if not update_ok: print("- Missing Update log")
             if not agent_ok: print("- Missing Agent message log")
             if not sim_ok: print("- Missing Simulation log")
    else:
        print("\n❌ VERIFICATION FAILED: conversations.log was not created.")

if __name__ == "__main__":
    asyncio.run(run_test())
