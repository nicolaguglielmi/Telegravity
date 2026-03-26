import os
import asyncio
import logging
import sys
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from mcp.server.fastmcp import FastMCP
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError


# --- LOGGING CONFIGURATION ---
# We must ensure NO library writes to stdout, as it corrupts the MCP JSON-RPC stream.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("telegram-gateway")

# Explicitly redirect common library loggers to stderr
for logger_name in ["httpx", "telegram", "mcp"]:
    lib_logger = logging.getLogger(logger_name)
    lib_logger.propagate = True
    lib_logger.setLevel(logging.INFO)

# --- CONFIGURATION ---
mcp = FastMCP("Telegram-Gateway")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
INITIAL_WORKSPACES = os.environ.get("INITIAL_WORKSPACES", "")

# --- STATE ---
WORKSPACES = []
CURRENT_WORKSPACE = None
WORKSPACE_CONVERSATIONS = {}  # {workspace_name: [conv_obj, ...]}
MESSAGE_BUFFER = []
BUFFER_LIMIT = 50
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "workspaces.txt")
CONVERSATIONS_FILE = os.path.join(SCRIPT_DIR, "conversations.json")
TASKS_FILE = os.path.join(SCRIPT_DIR, "tasks.json") # For migration
LOG_FILE = os.path.join(SCRIPT_DIR, "activity.log")
CONVERSATIONS_LOG_FILE = os.path.join(SCRIPT_DIR, "conversations.log")
CHAT_MODE = False
LAST_AI_MESSAGE_INDEX = 0
STATE_FILE = os.path.join(SCRIPT_DIR, "state.json")
ACTIVE_CONVERSATION_INDEX = None # Track the index of the conversation in focus

# Signaling for Active Listening
NEW_MESSAGE_EVENT = asyncio.Event()




def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            import json
            json.dump({
                "current_workspace": CURRENT_WORKSPACE,
                "chat_mode": CHAT_MODE,
                "last_index": LAST_AI_MESSAGE_INDEX,
                "active_conversation": ACTIVE_CONVERSATION_INDEX
            }, f)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")

def load_state():
    global CURRENT_WORKSPACE, CHAT_MODE, LAST_AI_MESSAGE_INDEX, ACTIVE_CONVERSATION_INDEX
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                import json
                state = json.load(f)
                CURRENT_WORKSPACE = state.get("current_workspace")
                CHAT_MODE = state.get("chat_mode", False)
                LAST_AI_MESSAGE_INDEX = state.get("last_index", 0)
                ACTIVE_CONVERSATION_INDEX = state.get("active_conversation")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")

def save_conversations():
    import json
    try:
        with open(CONVERSATIONS_FILE, "w") as f:
            json.dump(WORKSPACE_CONVERSATIONS, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save conversations: {e}")

def load_conversations():
    global WORKSPACE_CONVERSATIONS
    import json
    if os.path.exists(CONVERSATIONS_FILE):
        try:
            with open(CONVERSATIONS_FILE, "r") as f:
                WORKSPACE_CONVERSATIONS = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load conversations: {e}")
    elif os.path.exists(TASKS_FILE):
        # Migration path for legacy Task files
        try:
            with open(TASKS_FILE, "r") as f:
                WORKSPACE_CONVERSATIONS = json.load(f)
                logger.info("Migrated legacy tasks to conversations model.")
                # Force save to new format
                save_conversations()
        except Exception as e:
            logger.error(f"Migration failed: {e}")




HELP_TEXT = """
🤖 *Telegram Gateway Manager*

Available Commands:
• `/workspaces` - List active workspaces.
• `/select <name>` - Set the active workspace.
• `/conversations` - Open the Conversation Hub.
• `/stats` - View Project Statistics.
• `/logs` - See recent activity logs.
• `/chat` - Toggle Remote Chat mode.
• `/newconv <desc>` - Start a New Conversation.
• `/reload` - Sync Config (workspaces.txt).
• `/help` - Show this message.

*Note:* You can also just type "help".
*Status:* Current selection: {current_workspace} | Chat Mode: {chat_mode}
"""




# Global bot instance
bot: Optional[Bot] = None

async def render_dashboard(chat_id: int, edit_query=None):
    """Unified function to show the main dashboard."""
    global CURRENT_WORKSPACE, CHAT_MODE, ACTIVE_CONVERSATION_INDEX
    status = "ON 🟢" if CHAT_MODE else "OFF 🔴"
    
    # 1. Handle No Workspace Selected
    if not CURRENT_WORKSPACE:
        reply = f"🛡️ *AG-Uplink Agent Dashboard* 🛰️\n"
        reply += "--------------------------------\n"
        reply += "📍 *Project:* `Not Selected`\n\n"
        reply += "Please select a workspace to begin:"
        
        keyboard = []
        if not WORKSPACES:
            reply += "\n_No workspaces registered._"
        else:
            for i in range(0, len(WORKSPACES), 2):
                row = [InlineKeyboardButton(ws, callback_data=f"select:{ws}") for ws in WORKSPACES[i:i+2]]
                keyboard.append(row)
        
        # Add a reload button just in case
        keyboard.append([InlineKeyboardButton("🔄 Reload Workspaces", callback_data="ui_sync")])
        markup = InlineKeyboardMarkup(keyboard)
        
    else:
        # 2. Handle Workspace Selected
        conversations = WORKSPACE_CONVERSATIONS.get(CURRENT_WORKSPACE, [])
        active_conv_text = "None"
        if ACTIVE_CONVERSATION_INDEX is not None and 0 <= ACTIVE_CONVERSATION_INDEX < len(conversations):
            active_conv_text = conversations[ACTIVE_CONVERSATION_INDEX]['desc']
            if len(active_conv_text) > 30: active_conv_text = active_conv_text[:27] + "..."

        reply = f"🛡️ *AG-Uplink Dashboard* 🛰️\n"
        reply += "--------------------------------\n"
        reply += f"📍 *Workspace:* `{CURRENT_WORKSPACE}`\n"
        reply += f"💬 *Active Focus:* `{active_conv_text}`\n"
        reply += f"🗣️ *Chat Mode:* {status}\n\n"
        reply += "Choose an action:"
        
        keyboard = [
            [InlineKeyboardButton("💬 Conv Hub", callback_data="ui_conversations"),
             InlineKeyboardButton("🚀 New Conv", callback_data="ui_new_conv")],
            [InlineKeyboardButton("♻️ Sync", callback_data="ui_sync"),
             InlineKeyboardButton("📈 Stats", callback_data="ui_stats")],
            [InlineKeyboardButton(f"🗣️ {'Disable' if CHAT_MODE else 'Enable'} Remote Chat", callback_data="ui_chat_toggle")],
            [InlineKeyboardButton("📂 Switch Workspace", callback_data="ui_workspaces")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
    if edit_query:
        try:
            await edit_query.edit_message_text(text=reply, reply_markup=markup, parse_mode="Markdown")
        except Exception as e:
            # Fallback if message cannot be edited
            await bot.send_message(chat_id=chat_id, text=reply, reply_markup=markup, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id=chat_id, text=reply, reply_markup=markup, parse_mode="Markdown")

# --- COMMAND LOGIC ---
async def handle_command(text: str, chat_id: int) -> bool:
    """Handles commands and returns True if a reply was sent."""
    global CURRENT_WORKSPACE, CHAT_MODE
    original_text = text
    text = text.strip().split('@')[0].lower()
    
    logger.info(f"Command received: '{original_text}' -> processed as: '{text}'")
    save_log(f"DEBUG: Processed command '{text}' from '{original_text}'")
    
    if text.startswith("/menu"):
        await render_dashboard(chat_id)
        return True

    elif text == "/workspaces":
        if not WORKSPACES:
            reply = "No active workspaces registered."
        else:
            ws_list = "\n".join([f"• {ws}" for ws in WORKSPACES])
            reply = f"📂 *Available Workspaces:*\n{ws_list}"
        try:
            await bot.send_message(chat_id=chat_id, text=reply, parse_mode="Markdown")
            return True
        except Exception as e:
            logger.error(f"Failed to send workspace list: {e}")
            return False
            
    elif text.startswith("/select"):
        parts = text.split(None, 1)
        query = parts[1].strip() if len(parts) > 1 else None
        
        # If a query is provided, try exact match or partial match
        if query:
            q_lower = query.lower()
            matches = [ws for ws in WORKSPACES if q_lower in ws.lower()]
            
            if len(matches) == 1:
                CURRENT_WORKSPACE = matches[0]
                save_state()
                reply = f"✅ *Selected Workspace:* {CURRENT_WORKSPACE}"
                await bot.send_message(chat_id=chat_id, text=reply, parse_mode="Markdown")
                return True

            elif len(matches) > 1:
                reply = f"⚠️ Multiple matches for '{query}'. Please use the menu below."
                # Fall through to show buttons
            else:
                reply = f"❌ No workspace found matching '{query}'. Showing menu instead."
                # Fall through to show buttons
        else:
            reply = "🏷️ *Workspace Selection Menu*"

        if not WORKSPACES:
            await bot.send_message(chat_id=chat_id, text="No active workspaces registered.")
            return True
        
        # Create buttons (2 columns)
        keyboard = []
        for i in range(0, len(WORKSPACES), 2):
            row = [InlineKeyboardButton(ws, callback_data=f"select:{ws}") for ws in WORKSPACES[i:i+2]]
            keyboard.append(row)
        
        try:
            await bot.send_message(
                chat_id=chat_id, 
                text=reply, 
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send selection keyboard: {e}")
            return False


    elif text == "/conversations" or text == "/conv":
        if not CURRENT_WORKSPACE:
            await bot.send_message(chat_id=chat_id, text="⚠️ Please select a workspace first.")
            return True
        
        conversations = WORKSPACE_CONVERSATIONS.get(CURRENT_WORKSPACE, [])
        reply = f"💬 *Conversation Hub: {CURRENT_WORKSPACE}*\n"
        reply += "--------------------------------\n"
        
        keyboard = []
        if not conversations:
            reply += "_No conversations started._"
        else:
            for idx, conv in enumerate(conversations):
                status_icon = "✅" if conv['status'] == 'done' else "💬"
                desc = conv['desc']
                if len(desc) > 30: desc = desc[:27] + "..."
                keyboard.append([InlineKeyboardButton(f"{status_icon} {desc}", callback_data=f"conv_view:{idx}")])
        
        keyboard.append([
            InlineKeyboardButton("🚀 New Conversation", callback_data="ui_new_conv"),
            InlineKeyboardButton("🔁 Follow-up", callback_data="ui_followup")
        ])
        keyboard.append([InlineKeyboardButton("📖 Interaction History", callback_data="ui_chat_log")])
        keyboard.append([InlineKeyboardButton("🏠 Main Dashboard", callback_data="ui_menu")])
        
        await bot.send_message(chat_id=chat_id, text=reply, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return True

    elif text.startswith("/newconv "):
        if not CURRENT_WORKSPACE:
            await bot.send_message(chat_id=chat_id, text="⚠️ Select a workspace first.")
            return True
        desc = original_text.split(" ", 1)[1]
        if CURRENT_WORKSPACE not in WORKSPACE_CONVERSATIONS:
            WORKSPACE_CONVERSATIONS[CURRENT_WORKSPACE] = []
        WORKSPACE_CONVERSATIONS[CURRENT_WORKSPACE].append({
            "desc": desc,
            "status": "active",
            "output": "",
            "interactions": [],
            "created_at": timestamp_now()
        })
        save_conversations()
        await bot.send_message(chat_id=chat_id, text=f"🆕 Started: *{desc}*", parse_mode="Markdown")
        return True


    elif text == "/stats":
        total_ws = len(WORKSPACES)
        total_convs = sum(len(c) for c in WORKSPACE_CONVERSATIONS.values())
        
        reply = f"📊 *Global Statistics:*\n\n"
        reply += f"• Workspaces: {total_ws}\n"
        reply += f"• Total Conversations: {total_convs}\n"
        
        # Breakdown by workspace
        for ws in WORKSPACES:
            ws_convs = WORKSPACE_CONVERSATIONS.get(ws, [])
            if ws_convs:
                reply += f"*{ws}:* {len(ws_convs)} active\n"
        
        await bot.send_message(chat_id=chat_id, text=reply, parse_mode="Markdown")
        return True

    elif text == "/logs":
        recent = "\n".join(MESSAGE_BUFFER[-10:])
        if not recent: recent = "No logs recorded yet."
        await bot.send_message(chat_id=chat_id, text=f"📋 *Recent Activity:*\n\n`{recent}`", parse_mode="Markdown")
        return True

    elif text == "/chat":
        CHAT_MODE = not CHAT_MODE
        save_state()
        status = "ENABLED 🟢" if CHAT_MODE else "DISABLED 🔴"

        reply = f"💬 *Remote Chat Mode:* {status}\n\n"
        if CHAT_MODE:
            reply += "Normal messages will now be forwarded to the AI Agent.\nTo exit, type `/chat` again."
        else:
            reply += "Returned to command mode."
        await bot.send_message(chat_id=chat_id, text=reply, parse_mode="Markdown")
        return True

    elif text == "/reload":
        count = load_workspaces()
        await bot.send_message(chat_id=chat_id, text=f"🔄 *Workspaces Reloaded:* {count} found.")
        return True



    elif text == "/help" or text == "/start" or text.lower() == "help":
        try:
            status_text = HELP_TEXT.format(
                current_workspace=CURRENT_WORKSPACE or "None",
                chat_mode="ON" if CHAT_MODE else "OFF"
            )
            keyboard = [[InlineKeyboardButton("🚀 Open Menu", callback_data="ui_menu")]]
            await bot.send_message(chat_id=chat_id, text=status_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return True
        except Exception as e:

            logger.error(f"Failed to send help message: {e}")
            return False
    return False

def timestamp_now():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_workspaces() -> int:
    """Loads workspaces from env and/or workspaces.txt."""
    global WORKSPACES
    new_workspaces = set()
    
    # 1. From Environment
    env_ws = os.environ.get("INITIAL_WORKSPACES", "")
    if env_ws:
        for ws in env_ws.split(","):
            if ws.strip(): new_workspaces.add(ws.strip())
            
    # 2. From File
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                for line in f:
                    if line.strip(): new_workspaces.add(line.strip())
        except Exception as e:
            logger.error(f"Error reading {CONFIG_FILE}: {e}")
            
    WORKSPACES = sorted(list(new_workspaces))
    return len(WORKSPACES)

def save_log(entry: str):
    """Appends an entry to the persistent log file."""
    try:
        with open(LOG_FILE, "a") as f:
            f.write(entry + "\n")
    except Exception as e:
        logger.error(f"Failed to save log: {e}")

def save_conversation_log(entry: str):
    """Appends an entry to the conversations log file."""
    try:
        with open(CONVERSATIONS_LOG_FILE, "a") as f:
            f.write(entry + "\n")
    except Exception as e:
        logger.error(f"Failed to save conversation log: {e}")

def load_logs():
    """Loads recent logs into memory buffer."""
    global MESSAGE_BUFFER
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f:
                lines = f.readlines()
                MESSAGE_BUFFER = [l.strip() for l in lines[-BUFFER_LIMIT:]]
        except Exception as e:
            logger.error(f"Failed to load logs: {e}")


# --- BACKGROUND TASKS ---
async def polling_worker():
    """Background task to poll for updates and handle commands."""
    global LAST_AI_MESSAGE_INDEX, CHAT_MODE
    offset = 0
    logger.info("Background polling worker active.")
    while True:
        try:
            # We fetch both messages and callback_queries
            updates = await bot.get_updates(
                offset=offset, 
                timeout=20, 
                allowed_updates=["message", "callback_query"]
            )
            for update in updates:
                offset = update.update_id + 1
                # Handle button clicks
                if update.callback_query:
                    await handle_callback(update)
                    continue

                if update.message and update.message.text:
                    sender = update.message.from_user.username or update.message.from_user.first_name
                    timestamp = update.message.date.strftime("%H:%M:%S")
                    
                    # Handle commands
                    replied = await handle_command(update.message.text, update.message.chat_id)
                    
                    # If not a command and CHAT_MODE is on, this is AI input
                    if not replied and CHAT_MODE:
                        # Log it
                        msg_log = f"[{timestamp}] 👤 {sender}: {update.message.text}"
                        MESSAGE_BUFFER.append(msg_log)
                        save_log(msg_log)
                        save_conversation_log(msg_log)
                        
                        # Add immediate acknowledgment back to Telegram
                        try:
                            await bot.send_message(
                                chat_id=update.message.chat_id,
                                text=f"✅ *Received:* `{update.message.text}`\n_Forwarding to agent..._",
                                parse_mode="Markdown"
                            )
                        except Exception as e:
                            logger.error(f"Failed to send ack message: {e}")
                        
                        # Add buffer limit check
                        if len(MESSAGE_BUFFER) > BUFFER_LIMIT:
                            MESSAGE_BUFFER.pop(0)
                            if LAST_AI_MESSAGE_INDEX > 0:
                                LAST_AI_MESSAGE_INDEX -= 1
                                
                        # Signal Active Listening waiters
                        NEW_MESSAGE_EVENT.set()
                        # The AI Agent will read this from the resource or check_updates tool
                        continue

                    # Log regular messages
                    icon = "⚡️" if replied else "👤"
                    msg_log = f"[{timestamp}] {icon} {sender}: {update.message.text}"
                    if replied:
                        msg_log += " (Command)"
                    
                    MESSAGE_BUFFER.append(msg_log)
                    NEW_MESSAGE_EVENT.set()
                    save_log(msg_log)
                    save_conversation_log(msg_log)
                    if len(MESSAGE_BUFFER) > BUFFER_LIMIT:
                        MESSAGE_BUFFER.pop(0)
                        if LAST_AI_MESSAGE_INDEX > 0:
                            LAST_AI_MESSAGE_INDEX -= 1
                        
        except Exception as e:
            logger.error(f"Polling error: {e}")
            await asyncio.sleep(5)

async def handle_callback(update: Update):
    """Handles button clicks for workspace selection."""
    global CURRENT_WORKSPACE, CHAT_MODE, ACTIVE_CONVERSATION_INDEX
    query = update.callback_query
    data = query.data

    if data.startswith("select:"):
        workspace_name = data.replace("select:", "")
        CURRENT_WORKSPACE = workspace_name
        save_state()
        await query.answer(f"📍 {workspace_name}")
        # Clear the old selection menu and show dashboard
        await render_dashboard(query.message.chat_id, edit_query=query)
        logger.info(f"Workspace set to: {workspace_name}")
        return

    elif data.startswith("confirm:"):
        # Deprecated: Selecting now happens instantly via "select:"
        await query.answer("Instant selection enabled.")
        update.callback_query.data = "ui_menu"
        await handle_callback(update)

    elif data == "ui_conversations":
        if not CURRENT_WORKSPACE:
            await query.answer("⚠️ Please select a workspace first.")
            update.callback_query.data = "ui_workspaces"
            await handle_callback(update)
            return

        conversations = WORKSPACE_CONVERSATIONS.get(CURRENT_WORKSPACE, [])
        reply = f"💬 *Conversation Hub: {CURRENT_WORKSPACE}*\n"
        reply += "--------------------------------\n"
        
        keyboard = []
        if not conversations:
            reply += "_No conversations started._"
        else:
            for idx, conv in enumerate(conversations):
                status_icon = "✅" if conv['status'] == 'done' else "💬"
                desc = conv['desc']
                if len(desc) > 30: desc = desc[:27] + "..."
                keyboard.append([InlineKeyboardButton(f"{status_icon} {desc}", callback_data=f"conv_view:{idx}")])
        
        keyboard.append([
            InlineKeyboardButton("🚀 New Conversation", callback_data="ui_new_conv")
        ])
        keyboard.append([InlineKeyboardButton("📖 Interaction History", callback_data="ui_chat_log")])
        keyboard.append([InlineKeyboardButton("🏠 Main Dashboard", callback_data="ui_menu")])
        
        await query.edit_message_text(text=reply, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        await query.answer()


    elif data == "ui_workspaces" or data == "menu":
        # Simplified: Just clear selection to trigger workspace picker on dashboard
        CURRENT_WORKSPACE = None
        ACTIVE_CONVERSATION_INDEX = None # Clear active conv on switch
        save_state()
        await render_dashboard(query.message.chat_id, edit_query=query)
        await query.answer()

    elif data == "ui_menu":
        await render_dashboard(query.message.chat_id, edit_query=query)
        await query.answer()


    elif data.startswith("conv_view:"):
        idx = int(data.split(":")[1])
        conversations = WORKSPACE_CONVERSATIONS.get(CURRENT_WORKSPACE, [])
        if idx < len(conversations):
            conv = conversations[idx]
            status_icon = "✅" if conv['status'] == 'done' else "💬"
            reply = f"🔎 *Conversation Details*\n"
            reply += "--------------------------------\n"
            reply += f"*Focus:* {conv['desc']}\n"
            reply += f"*Status:* {status_icon} {conv['status']}\n"
            reply += f"*Started:* {conv['created_at']}\n"
            
            # Interaction Logs
            logs = conv.get('interactions', [])
            if not logs and conv.get('output'):
                # Migration: Convert old string output to first log
                logs = [{"title": "Initial Response", "content": conv['output'], "time": conv['created_at']}]
                conv['interactions'] = logs
            
            keyboard = []
            if logs:
                reply += f"\n📂 *Request/Response Logs ({len(logs)}):*\n"
                reply += "_Select an interaction to view details:_\n"
                for l_idx, log in enumerate(logs):
                    title = log.get('title', f"Exchange {l_idx+1}")
                    if len(title) > 25: title = title[:22] + "..."
                    keyboard.append([InlineKeyboardButton(f"📜 {title}", callback_data=f"int_view:{idx}:{l_idx}")])
            else:
                reply += "\n*Insight:*\n_No interactions recorded yet._\n"
            
            keyboard.append([InlineKeyboardButton("💬 Enter Chat (Follow-up)", callback_data=f"ui_enter_chat:{idx}")])
            keyboard.append([InlineKeyboardButton("📖 Conversation Log", callback_data="ui_chat_log")])
            keyboard.append([InlineKeyboardButton("🔙 Back to Hub", callback_data="ui_conversations")])
            keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="ui_menu")])
            await query.edit_message_text(text=reply, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        await query.answer()

    elif data.startswith("int_view:"):
        _, conv_idx, int_idx = data.split(":")
        conv_idx, int_idx = int(conv_idx), int(int_idx)
        conversations = WORKSPACE_CONVERSATIONS.get(CURRENT_WORKSPACE, [])
        if conv_idx < len(conversations):
            conv = conversations[conv_idx]
            logs = conv.get('interactions', [])
            if int_idx < len(logs):
                log = logs[int_idx]
                reply = f"📜 *Interaction Details*\n"
                reply += "--------------------------------\n"
                reply += f"*Topic:* {conv['desc']}\n"
                reply += f"*Interaction:* {log.get('title')}\n"
                reply += f"*Time:* {log.get('time', 'N/A')}\n\n"
                
                content = log.get('content', 'No content.')
                if len(content) > 3000:
                    content = content[:3000] + "... (Truncated)"
                
                reply += f"```\n{content}\n```"
                
                nav_row = []
                if int_idx > 0:
                    nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"int_view:{conv_idx}:{int_idx-1}"))
                if int_idx < len(logs) - 1:
                    nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"int_view:{conv_idx}:{int_idx+1}"))
                
                keyboard = []
                if nav_row:
                    keyboard.append(nav_row)
                
                keyboard.append([
                    InlineKeyboardButton("💬 Conv Hub", callback_data="ui_conversations"),
                    InlineKeyboardButton("🔎 Details", callback_data=f"conv_view:{conv_idx}")
                ])
                keyboard.append([InlineKeyboardButton("🏠 Main Dashboard", callback_data="ui_menu")])
                
                await query.edit_message_text(text=reply, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        await query.answer()

    elif data == "ui_sync":
        # Trigger standard message to notify AI to sync
        msg = "--- FORCE SYNC REQUESTED ---"
        MESSAGE_BUFFER.append(f"[{timestamp_now()}] AG-Uplink: {msg}")
        save_log(f"[{timestamp_now()}] AG-Uplink: {msg}")
        NEW_MESSAGE_EVENT.set()
        await query.answer("Sync triggered. Agent notified.")
        
        # Optionally reload workspaces file too
        count = load_workspaces()
        await render_dashboard(query.message.chat_id, edit_query=query)

    elif data.startswith("ui_enter_chat:"):
        idx = int(data.split(":")[1])
        ACTIVE_CONVERSATION_INDEX = idx
        CHAT_MODE = True
        save_state()
        
        conversations = WORKSPACE_CONVERSATIONS.get(CURRENT_WORKSPACE, [])
        conv_desc = conversations[idx]['desc'] if idx < len(conversations) else "Unknown"
        
        await query.answer("Chat Active")
        await bot.send_message(
            chat_id=query.message.chat_id,
            text=f"💬 *Chatting in:* `{conv_desc}`\nType your message below. Type `/exit` or use Menu to leave.",
            parse_mode="Markdown"
        )
        await render_dashboard(query.message.chat_id, edit_query=None) # Refresh

    elif data == "ui_chat_toggle":
        CHAT_MODE = not CHAT_MODE
        save_state()
        status = "ON 🟢" if CHAT_MODE else "OFF 🔴"
        await query.answer(f"Remote Chat is now {status}")
        # Refresh the SAME view to update button labels
        update.callback_query.data = "ui_menu"
        await handle_callback(update)

    elif data == "ui_chat_log":
        history = "\n".join(MESSAGE_BUFFER[-15:])
        if not history: history = "_No message history available._"
        
        reply = f"📖 *Interaction History*\n"
        reply += "--------------------------------\n\n"
        reply += history
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Hub", callback_data="ui_conversations")]]
        keyboard.append([InlineKeyboardButton("🏠 Main Dashboard", callback_data="ui_menu")])
        
        await query.edit_message_text(text=reply, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        await query.answer()

    elif data == "ui_new_conv":
        # Simulate a command from the UI
        msg = f"--- INITIATING NEW CONVERSATION ---"
        MESSAGE_BUFFER.append(f"[{timestamp_now()}] AG-Uplink: {msg}")
        save_log(f"[{timestamp_now()}] AG-Uplink: {msg}")
        await query.answer("Creating fresh interaction context...")

        keyboard = [
            [InlineKeyboardButton("🛡️ Dashboard", callback_data="ui_menu"),
             InlineKeyboardButton("💬 Conv Hub", callback_data="ui_conversations")]
        ]
        await bot.send_message(
            chat_id=query.message.chat_id, 
            text="🚀 *Ready for a new conversation!* What would you like to build or discuss?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "ui_followup" or data.startswith("ui_followup_conv:"):
        conv_idx = data.split(":")[1] if ":" in data else "GLOBAL"
        # Simulate a command from the UI
        msg = f"--- CONTEXT FOLLOW-UP REQUESTED (Target: {conv_idx}) ---"
        MESSAGE_BUFFER.append(f"[{timestamp_now()}] AG-Uplink: {msg}")
        save_log(f"[{timestamp_now()}] AG-Uplink: {msg}")
        NEW_MESSAGE_EVENT.set()
        await query.answer(f"Context captured for {conv_idx}!")
        
        keyboard = [
            [InlineKeyboardButton("🛡️ Dashboard", callback_data="ui_menu"),
             InlineKeyboardButton("💬 Conv Hub", callback_data="ui_conversations")]
        ]
        await bot.send_message(
            chat_id=query.message.chat_id, 
            text=f"🔁 *Context captured!* I've notified the Agent to resume work on conversation `{conv_idx}`.\n\nPlease provide your next instruction below.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )




# --- MCP TOOLS & RESOURCES ---
@mcp.tool()
async def send_message(text: str) -> str:
    """Sends a message to the configured Telegram Chat ID."""
    if not bot:
        return "Error: Bot not initialized."
    if not CHAT_ID:
        return "Error: CHAT_ID not set."
    try:
        keyboard = [
            [InlineKeyboardButton("🛡️ Dashboard", callback_data="ui_menu"),
             InlineKeyboardButton("💬 Conversation Hub", callback_data="ui_conversations")]
        ]
        await bot.send_message(
            chat_id=CHAT_ID, 
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        # Log AI response for visibility in Telegram logs
        msg_log = f"[{timestamp_now()}] 🧠 Agent: {text}"
        MESSAGE_BUFFER.append(msg_log)
        save_log(msg_log)
        save_conversation_log(msg_log)
        return f"SUCCESS: Message sent."
    except TelegramError as e:
        return f"ERROR: {str(e)}"

@mcp.tool()
async def check_telegram_updates() -> List[str]:
    """
    Returns new messages from Telegram since the last check.
    If no new messages, returns an empty list.
    """
    global LAST_AI_MESSAGE_INDEX
    
    if LAST_AI_MESSAGE_INDEX >= len(MESSAGE_BUFFER):
        return []
    
    new_messages = MESSAGE_BUFFER[LAST_AI_MESSAGE_INDEX:]
    LAST_AI_MESSAGE_INDEX = len(MESSAGE_BUFFER)
    save_state()
    return new_messages


@mcp.tool()
async def wait_for_remote_instruction(timeout_sec: int = 300) -> List[str]:
    """
    Long-polling: Blocks the Agent until a new instruction arrives from Telegram.
    This enables 'Active Mode' where the Agent pick up commands automatically.
    """
    global LAST_AI_MESSAGE_INDEX
    
    # 1. Immediate check: anything we missed?
    if LAST_AI_MESSAGE_INDEX < len(MESSAGE_BUFFER):
        new_messages = MESSAGE_BUFFER[LAST_AI_MESSAGE_INDEX:]
        LAST_AI_MESSAGE_INDEX = len(MESSAGE_BUFFER)
        save_state()
        return new_messages

    # 2. Wait for the server-side event
    try:
        # Reset the event before waiting to ensure we don't catch a stale signal
        NEW_MESSAGE_EVENT.clear()
        await asyncio.wait_for(NEW_MESSAGE_EVENT.wait(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        return [] # Return empty if nothing arrived, Agent can decide to loop
    
    # 3. Message arrived!
    new_messages = MESSAGE_BUFFER[LAST_AI_MESSAGE_INDEX:]
    LAST_AI_MESSAGE_INDEX = len(MESSAGE_BUFFER)
    save_state()
    return new_messages


@mcp.tool()
async def get_state() -> str:
    """Returns current selection, conversations, and recent history."""
    global ACTIVE_CONVERSATION_INDEX
    history = "\n".join(MESSAGE_BUFFER[-10:])
    conversations = WORKSPACE_CONVERSATIONS.get(CURRENT_WORKSPACE, [])
    conv_str = "No conversations."
    if conversations:
        # Avoid breaking older parsing if any, but adding status is good
        conv_str = "\n".join([f"- [{c['status']}] {c['desc']}" for c in conversations])
        
    active_conv = "None"
    if ACTIVE_CONVERSATION_INDEX is not None and 0 <= ACTIVE_CONVERSATION_INDEX < len(conversations):
        active_conv = conversations[ACTIVE_CONVERSATION_INDEX]['desc']
        
    return f"CURRENT WORKSPACE: {CURRENT_WORKSPACE or 'None'}\nACTIVE CONVERSATION: {active_conv}\n\nCONVERSATIONS:\n{conv_str}\n\nHISTORY:\n{history}"

@mcp.tool()
async def update_conversation(
    conv_desc: str, 
    status: str, 
    conv_index: Optional[int] = None,
    log_title: Optional[str] = None, 
    summary: Optional[str] = None,
    files_edited: Optional[List[str]] = None,
    progress_steps: Optional[List[str]] = None,
    log_content: Optional[str] = None
) -> str:
    """Updates a conversation with a rich interaction log. Matches by description or index."""
    if not CURRENT_WORKSPACE:
        return "Error: No workspace selected."
    
    conversations = WORKSPACE_CONVERSATIONS.get(CURRENT_WORKSPACE, [])
    conv = None
    
    # Matching logic
    if conv_index is not None and 0 <= conv_index < len(conversations):
        conv = conversations[conv_index]
    else:
        # Search by description
        for c in conversations:
            if c['desc'].lower() == conv_desc.lower():
                conv = c
                break
        
        # If not found, create new one
        if not conv:
            conv = {
                "desc": conv_desc,
                "status": "active",
                "interactions": [],
                "created_at": timestamp_now()
            }
            conversations.append(conv)
            WORKSPACE_CONVERSATIONS[CURRENT_WORKSPACE] = conversations

    conv['status'] = status
    
    if log_title:
        if 'interactions' not in conv:
            conv['interactions'] = []
        
        report = {
            "title": log_title,
            "summary": summary,
            "files": files_edited,
            "steps": progress_steps,
            "content": log_content,
            "time": timestamp_now()
        }
        conv['interactions'].append(report)
        conv['output'] = f"Latest Interaction: {log_title}"
    
    save_conversation_log(f"[{timestamp_now()}] 🛰️ [Update] Conversation '{conv_desc}' -> Status: {status} | {log_title or 'No Title'}")
    save_conversations()
    
    # Add automatic Telegram notification
    try:
        from telegram.constants import ParseMode
        msg = f"🛰️ *Task Update*: `{conv_desc}`\n*Status*: `{status}`"
        if log_title:
            msg += f"\n*Action*: {log_title}"
        if summary:
            msg += f"\n_Summary_: {summary}"
            
        await bot.send_message(
            chat_id=CHAT_ID, 
            text=msg, 
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to send Telegram task update: {e}")
        
    return f"SUCCESS: Conversation '{conv_desc}' updated. Log '{log_title}' added."


# Removed duplicate check_updates tool as it is superseded by check_telegram_updates




@mcp.tool()
async def import_conversations(workspace_name: str, conversations: List[str]) -> str:
    """Import missing conversation descriptors (smart merge)."""
    if workspace_name not in WORKSPACES:
        if workspace_name == CURRENT_WORKSPACE: pass # Allow if it's the active one
        else: return f"Error: Workspace '{workspace_name}' not recognized."
    
    if workspace_name not in WORKSPACE_CONVERSATIONS:
        WORKSPACE_CONVERSATIONS[workspace_name] = []
        
    existing_descs = {c['desc'].lower() for c in WORKSPACE_CONVERSATIONS[workspace_name]}
    added_count = 0
    
    for desc in conversations:
        if desc.lower() not in existing_descs:
            WORKSPACE_CONVERSATIONS[workspace_name].append({
                "desc": desc,
                "status": "active",
                "output": "",
                "interactions": [],
                "created_at": timestamp_now()
            })
            added_count += 1
            
    save_conversations()
    return f"SUCCESS: Synced {added_count} new conversations into {workspace_name}."




@mcp.resource("telegram://inbox")
async def telegram_inbox() -> str:
    """Read-only view of the latest Telegram messages."""
    return "\n".join(MESSAGE_BUFFER[-10:])

# --- MAIN ENTRY POINT ---
async def main():
    global bot
    logger.info("Starting Telegram MCP Gateway...")
    
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not found.")
        return

    # Initial load
    load_workspaces()
    load_conversations()
    load_logs()
    load_state()

    
    with open(os.path.join(SCRIPT_DIR, "startup.log"), "w") as f:
        f.write(f"CHAT_ID: {CHAT_ID}\n")
        f.write(f"TOKEN: {TELEGRAM_TOKEN[:10]}...\n")

    # Initialize Bot in the same loop


    bot = Bot(token=TELEGRAM_TOKEN)
    
    # Register bot commands
    from telegram import BotCommand
    commands = [
        BotCommand("menu", "Show the main navigation menu"),
        BotCommand("workspaces", "List all active workspaces"),
        BotCommand("select", "Select a workspace"),
        BotCommand("conversations", "Manage conversations for current workspace"),
        BotCommand("stats", "View global statistics"),
        BotCommand("logs", "View recent activity logs"),
        BotCommand("chat", "Toggle Remote Chat Mode"),
        BotCommand("help", "Show help message")
    ]
    try:
        await bot.set_my_commands(commands)
        logger.info("Bot commands registered successfully.")
    except Exception as e:
        logger.error(f"Failed to register bot commands: {e}")

    # Send startup notification
    if CHAT_ID:
        try:
            startup_msg = "🤖 *Telegram Gateway ONLINE*\n" + HELP_TEXT.format(
                current_workspace=CURRENT_WORKSPACE or "None",
                chat_mode="OFF"
            )
            keyboard = [[InlineKeyboardButton("🚀 Open Menu", callback_data="ui_menu")]]
            await bot.send_message(chat_id=CHAT_ID, text=startup_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            logger.info("Startup message sent.")
        except Exception as e:
            logger.error(f"Startup notification failed: {e}")

    # Start background tasks
    asyncio.create_task(polling_worker())
    
    # Optional: Start a file watcher task for workspaces.txt
    async def config_watcher():
        last_mtime = 0
        while True:
            if os.path.exists(CONFIG_FILE):
                mtime = os.path.getmtime(CONFIG_FILE)
                if mtime > last_mtime:
                    load_workspaces()
                    last_mtime = mtime
                    logger.info("Workspaces auto-reloaded from file.")
            await asyncio.sleep(5)
            
    asyncio.create_task(config_watcher())
    
    # Run the MCP server
    # We use mcp.run_stdio_async() directly to avoid AnyIO loop conflicts
    try:
        await mcp.run_stdio_async()
    except Exception as e:
        logger.error(f"MCP Server crashed: {e}")

if __name__ == "__main__":
    # Use a basic run to avoid complicated signal handling issues in interactive shells
    asyncio.run(main())

