# 🛰️ AG-Uplink: Antigravity Remote Command Center

AG-Uplink is a high-performance **Model Context Protocol (MCP)** server that transforms Telegram into a professional command center for AI Agents (like Antigravity). It provides a seamless, stateful bridge for remote project management, real-time logging, and interactive instructions.

## 🚀 Premium Features

### 📡 Remote Interaction Hub
*   **Chat Mode**: Toggle "Remote Chat" with a single click to forward standard Telegram messages directly to your AI Agent as prioritized instructions.
*   **Context-Aware Follow-ups**: Targeted "Continue Conversation" interactions that preserve context without requiring you to re-explain the workspace or objective.
*   **Real-time Activity Stream**: Monitor command processing and agent "thoughts" via the integrated activity log.

### 💬 Conversation-Centric Model
*   **Hierarchical Organization**: Manage complex work via **Workspaces -> Conversations -> Interactions**.
*   **Real-time Agent Feedback**: Get instant notifications when the Agent "Takes Charge" of a command and when a task is completed.
*   **Rich Technical Logs**: Deep-dive into specific request/response pairs with structured summaries, file lists, and progress milestones—mimicking the full Antigravity experience.
*   **Interactive Navigation**: A high-density dashboard with instant transitions and hot-loaded workspace configurations.

### 🛡️ Built for Reliability
*   **Automatic Data Migration**: Seamlessly upgrades legacy models to the new conversation-centric structure.
*   **Persistent State**: Your active workspace, chat mode, and message history are preserved across server restarts via encrypted-ready JSON storage.
*   **Non-Blocking Architecture**: High-volume Telegram polling designed to never interfere with IDE performance.

## 🛠️ Quick Start

### Prerequisites
*   Python 3.11+
*   A Telegram Bot Token (from [@BotFather](https://t.me/botfather))

### Setup
1.  **Clone & Configure**:
    Create a `.env` file in the project root:
    ```env
    TELEGRAM_TOKEN=your_bot_token
    CHAT_ID=your_telegram_id
    INITIAL_WORKSPACES=AG-Uplink,AI-Radar
    ```
2.  **Add to MCP Configuration**:
    Add the gateway to your Antigravity `mcp_config.json`:
    ```json
    "AG-Uplink": {
      "command": "podman",
      "args": [
        "run", "-i", "--rm",
        "-v", ":/app:Z",
        "--env-file", ".env",
        "telegram-mcp-gateway"
      ]
    }
    ```
3.  **Install requirements**: `pip install -r requirements.txt` (for local development)
4.  **Launch your IDE** and start interacting via Telegram!

## 🔄 Typical Workflow

1.  **Select Workspace**: Use `/menu` -> **📂 Select Workspace** to set your project context.
2.  **Start Work**: In your IDE (Antigravity), the agent will see your active workspace and can begin work.
3.  **Monitor Progress**: Check **💬 Conversation Hub** to see live technical reports and interaction logs.
4.  **Remote Follow-up**: 
    *   Click **🔁 Continue this Conversation** on any interaction.
    *   Type your next instruction (e.g., *"Now add a login page"*).
    *   The Agent will pull this message and execute the next step automatically.

### 🌳 Dashboard Navigation
The interface is structured for speed:
`Main Dashboard` ➔ `Workspace Select` ➔ `Dashboard` ➔ `Conversation Hub` ➔ `Interaction Logs`.

> [!NOTE]
> **Sidebar vs. Hub**: The native IDE sidebar tracks current "Active Work". The **AG-Uplink Hub** is your permanent, searchable archive of all remote interactions. I pull your Telegram messages from the **Inbox** to start new work!

*For a full visual map, see [ARCHITECTURE.md:L81-120]

> [!TIP]
> **Pro-Tip: Active Mode**
> To avoid needing a local "nudge", ask me to **"Enter Active Mode"**. I will then use long-polling (`wait_for_remote_instruction`) to stay awake and process your Telegram messages the *instant* they arrive.

## ⌨️ Command Reference
*   `/menu` - Open the **AG-Uplink Agent Dashboard**.
*   `/conversations` - Browse the **Conversation Hub** for the active project.
*   `/workspaces` - Switch your focus between different project areas.
*   `/chat` - Toggle Remote Chat mode for direct AI instructions.

---