"""Screen renderers.

Each ``render_*`` function returns ``(text, InlineKeyboardMarkup)``. The text
is MarkdownV2-formatted and the markup is the inline keyboard. Keeping the
two together (instead of in separate keyboards/views modules) means screens
stay self-contained — easy to read, easy to tweak.
"""

from __future__ import annotations

from typing import Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..__version__ import __version__
from ..config import Config
from ..formatting import badge, inline_code, md2, short
from ..state import StateManager

DIVIDER = "─" * 24


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------
def render_welcome(state: StateManager, first_name: str = "") -> Tuple[str, InlineKeyboardMarkup]:
    greeting = f"Hi {md2(first_name)} — " if first_name else ""
    lines = [
        "🛰️ *Telegravity is online*",
        DIVIDER,
        "",
        f"{greeting}your Telegram is now wired to your AI agent\\.",
        "",
        "From here you can:",
        "   💼  Pick a workspace",
        "   💬  Watch live agent conversations",
        "   📡  Send remote instructions",
        "   ⚡  Toggle *Active Mode* for instant pickup",
        "",
        "_Take the 30\\-second tour, or jump straight in\\._",
    ]
    keyboard = [
        [
            InlineKeyboardButton("🎬 Quick tour", callback_data="tour:1"),
            InlineKeyboardButton("⏭ Open dashboard", callback_data="ui_menu"),
        ]
    ]
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


_TOUR_STEPS = [
    {
        "title": "1 / 4 · Workspaces",
        "body": (
            "💼 *Workspaces* are your project folders\\.\n\n"
            "Each one has its own *conversations*, *active focus*, and *inbox*\\. "
            "Switch between them from the dashboard top\\-right\\.\n\n"
            "Add new ones from your `.env` \\(`INITIAL_WORKSPACES`\\) or by editing "
            "`data/workspaces.txt` while the bot is running — it hot\\-reloads\\."
        ),
    },
    {
        "title": "2 / 4 · Conversations",
        "body": (
            "💬 Each workspace holds *conversations* — long\\-running threads "
            "of work\\.\n\n"
            "Tap one to read the full request/response history, including files "
            "touched and progress steps the agent reported\\."
        ),
    },
    {
        "title": "3 / 4 · Remote instructions",
        "body": (
            "📡 Enable *Chat Mode* and anything you type is queued for the agent\\.\n\n"
            "When your agent calls `check_telegram_updates` \\(or sits in "
            "`wait_for_remote_instruction`\\) it picks up your message and acts "
            "on it\\."
        ),
    },
    {
        "title": "4 / 4 · Active Mode",
        "body": (
            "⚡ Ask the agent *“enter Active Mode”* in your IDE\\.\n\n"
            "It will block on `wait_for_remote_instruction` and wake up the "
            "*instant* you send a Telegram message — no IDE nudge needed\\.\n\n"
            "_You're all set — open the dashboard\\._"
        ),
    },
]


def render_tour(step: int) -> Tuple[str, InlineKeyboardMarkup]:
    idx = max(1, min(step, len(_TOUR_STEPS)))
    data = _TOUR_STEPS[idx - 1]
    text = f"*{md2(data['title'])}*\n{DIVIDER}\n\n{data['body']}"
    nav = []
    if idx > 1:
        nav.append(InlineKeyboardButton("◀ Back", callback_data=f"tour:{idx-1}"))
    if idx < len(_TOUR_STEPS):
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"tour:{idx+1}"))
    else:
        nav.append(InlineKeyboardButton("🚀 Open dashboard", callback_data="ui_menu"))
    return text, InlineKeyboardMarkup([nav])


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def _agent_line(state: StateManager) -> str:
    status = state.agent.status
    icon = badge(status if status != "offline" else "offline")
    label = status.capitalize() if status else "Offline"
    detail = state.agent.detail
    fresh = state.agent.freshness() if status != "offline" else "—"
    line = f"{icon} *Agent* · {md2(label)}"
    if detail:
        line += f" · _{md2(short(detail, 40))}_"
    line += f"\n          ⏱ {md2(fresh)}"
    return line


def _inbox_count(state: StateManager) -> int:
    return max(0, len(state.message_buffer) - state.last_ai_index)


def render_dashboard(state: StateManager, config: Config) -> Tuple[str, InlineKeyboardMarkup]:
    if not state.current_workspace:
        return _render_dashboard_no_workspace(state)

    conversations = state.conversations_for(state.current_workspace)
    focus = "—"
    if (
        state.active_conversation_index is not None
        and 0 <= state.active_conversation_index < len(conversations)
    ):
        focus = short(conversations[state.active_conversation_index]["desc"], 32)

    chat_label = "ON" if state.chat_mode else "OFF"
    chat_icon = "🟢" if state.chat_mode else "⚪"
    inbox = _inbox_count(state)

    lines = [
        f"🛰️ *Telegravity* · _v{md2(__version__)}_",
        DIVIDER,
        _agent_line(state),
        "",
        f"💼 *Workspace* `{md2(state.current_workspace)}`",
        f"🎯 *Focus*     `{md2(focus)}`",
        f"{chat_icon} *Chat mode* `{chat_label}`",
        f"📥 *Inbox*     `{inbox} new`" if inbox else f"📥 *Inbox*     _empty_",
    ]

    rows = [
        [
            InlineKeyboardButton(
                f"💬 Conversations ({len(conversations)})",
                callback_data="ui_conversations",
            ),
            InlineKeyboardButton("🚀 New thread", callback_data="ui_new_conv"),
        ],
        [InlineKeyboardButton("🤖 Ask agent", callback_data="ui_prompt_agent")],
    ]

    if config.enable_shell_exec or config.enable_file_view:
        tool_row = []
        if config.enable_shell_exec:
            tool_row.append(InlineKeyboardButton("⚙ Shell", callback_data="ui_prompt_command"))
        if config.enable_file_view:
            tool_row.append(InlineKeyboardButton("📜 View file", callback_data="ui_prompt_file"))
        rows.append(tool_row)

    rows.append(
        [
            InlineKeyboardButton(
                f"🗣 Chat: {chat_label}",
                callback_data="ui_chat_toggle",
            ),
            InlineKeyboardButton("📂 Switch workspace", callback_data="ui_workspaces"),
        ]
    )
    rows.append([InlineKeyboardButton("📖 Activity feed", callback_data="ui_chat_log")])

    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _render_dashboard_no_workspace(
    state: StateManager,
) -> Tuple[str, InlineKeyboardMarkup]:
    lines = [
        "🛰️ *Telegravity Dashboard*",
        DIVIDER,
        _agent_line(state),
        "",
        "📍 *Workspace* _not selected_",
        "",
        "Choose a project to focus on:",
    ]
    keyboard = []
    if state.workspaces:
        for i in range(0, len(state.workspaces), 2):
            row = [
                InlineKeyboardButton(ws, callback_data=f"select:{ws}")
                for ws in state.workspaces[i:i + 2]
            ]
            keyboard.append(row)
    else:
        lines.append("\n_No workspaces registered yet\\. Edit `data/workspaces.txt` or set `INITIAL_WORKSPACES`\\._")

    keyboard.append([InlineKeyboardButton("🔄 Reload list", callback_data="ui_sync")])
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


def render_workspace_picker(state: StateManager) -> Tuple[str, InlineKeyboardMarkup]:
    lines = [
        "📂 *Pick a workspace*",
        DIVIDER,
    ]
    if not state.workspaces:
        lines.append("_No workspaces yet — edit `data/workspaces.txt`\\._")
        keyboard = [[InlineKeyboardButton("🏠 Dashboard", callback_data="ui_menu")]]
        return "\n".join(lines), InlineKeyboardMarkup(keyboard)

    keyboard = []
    for i in range(0, len(state.workspaces), 2):
        row = [
            InlineKeyboardButton(ws, callback_data=f"select:{ws}")
            for ws in state.workspaces[i:i + 2]
        ]
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🏠 Dashboard", callback_data="ui_menu")])
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# Conversation hub
# ---------------------------------------------------------------------------
def _conv_status_badge(conv: dict) -> str:
    status = (conv.get("status") or "").lower()
    if status == "done":
        return "✅"
    if status in {"executing", "active"}:
        return "💬"
    if status == "error":
        return "❌"
    return "•"


def render_conversation_hub(state: StateManager) -> Tuple[str, InlineKeyboardMarkup]:
    workspace = state.current_workspace or "—"
    conversations = state.conversations_for(state.current_workspace)
    lines = [
        f"💬 *Conversation Hub* · `{md2(workspace)}`",
        DIVIDER,
    ]
    keyboard = []
    if not conversations:
        lines.append("_No conversations yet\\. Start one below\\._")
    else:
        for idx, conv in enumerate(conversations):
            icon = _conv_status_badge(conv)
            desc = short(conv.get("desc", "?"), 28)
            n_steps = len(conv.get("interactions", []))
            label = f"{icon} {desc}  ·  {n_steps}🪜"
            keyboard.append(
                [InlineKeyboardButton(label, callback_data=f"conv_view:{idx}")]
            )

    keyboard.append(
        [
            InlineKeyboardButton("🚀 New", callback_data="ui_new_conv"),
            InlineKeyboardButton("📖 Activity", callback_data="ui_chat_log"),
        ]
    )
    keyboard.append([InlineKeyboardButton("🏠 Dashboard", callback_data="ui_menu")])
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


def render_conversation_detail(
    state: StateManager, conv_idx: int
) -> Tuple[str, InlineKeyboardMarkup]:
    conversations = state.conversations_for(state.current_workspace)
    if conv_idx < 0 or conv_idx >= len(conversations):
        return "_Conversation not found\\._", InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Hub", callback_data="ui_conversations")]]
        )
    conv = conversations[conv_idx]
    interactions = conv.get("interactions", [])
    icon = _conv_status_badge(conv)
    lines = [
        f"🔎 *Conversation* · `{md2(conv.get('desc', '?'))}`",
        DIVIDER,
        f"{icon} *Status*  `{md2(conv.get('status', 'unknown'))}`",
        f"🗓 *Started* `{md2(conv.get('created_at', '—'))}`",
        f"🪜 *Steps*  `{len(interactions)}`",
    ]
    keyboard = []
    if interactions:
        lines.append("")
        lines.append("_Latest interactions_ ⤵")
        for l_idx, log in enumerate(interactions[-8:]):
            absolute_idx = len(interactions) - min(8, len(interactions)) + l_idx
            title = short(log.get("title") or f"Step {absolute_idx+1}", 26)
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"📜 {title}",
                        callback_data=f"int_view:{conv_idx}:{absolute_idx}",
                    )
                ]
            )
    else:
        lines.append("")
        lines.append("_No interactions logged yet\\._")

    keyboard.append(
        [
            InlineKeyboardButton(
                "💬 Follow up here", callback_data=f"ui_enter_chat:{conv_idx}"
            )
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton("🔙 Hub", callback_data="ui_conversations"),
            InlineKeyboardButton("🏠 Dashboard", callback_data="ui_menu"),
        ]
    )
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


def render_interaction_detail(
    state: StateManager, conv_idx: int, int_idx: int
) -> Tuple[str, InlineKeyboardMarkup]:
    conversations = state.conversations_for(state.current_workspace)
    if conv_idx < 0 or conv_idx >= len(conversations):
        return "_Conversation not found\\._", InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Hub", callback_data="ui_conversations")]]
        )
    conv = conversations[conv_idx]
    interactions = conv.get("interactions", [])
    if int_idx < 0 or int_idx >= len(interactions):
        return "_Step not found\\._", InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔙 Conversation",
                        callback_data=f"conv_view:{conv_idx}",
                    )
                ]
            ]
        )
    log = interactions[int_idx]
    body_lines = [
        f"📜 *Step {int_idx + 1} / {len(interactions)}*",
        DIVIDER,
        f"*Topic* `{md2(conv.get('desc', '?'))}`",
        f"*Title* {md2(log.get('title') or '—')}",
        f"*Time*  `{md2(log.get('time', '—'))}`",
    ]
    if log.get("summary"):
        body_lines.append("")
        body_lines.append(f"_{md2(log['summary'])}_")
    if log.get("files"):
        body_lines.append("")
        body_lines.append("*Files*")
        for f in log["files"][:8]:
            body_lines.append(f"  • `{md2(str(f))}`")
    if log.get("content"):
        from ..formatting import code_block, truncate_block

        body_lines.append("")
        body_lines.append(code_block(truncate_block(str(log["content"]), 1800)))

    nav_row = []
    if int_idx > 0:
        nav_row.append(
            InlineKeyboardButton("◀", callback_data=f"int_view:{conv_idx}:{int_idx-1}")
        )
    if int_idx < len(interactions) - 1:
        nav_row.append(
            InlineKeyboardButton("▶", callback_data=f"int_view:{conv_idx}:{int_idx+1}")
        )
    keyboard = []
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append(
        [
            InlineKeyboardButton("🔎 Overview", callback_data=f"conv_view:{conv_idx}"),
            InlineKeyboardButton("💬 Hub", callback_data="ui_conversations"),
        ]
    )
    keyboard.append([InlineKeyboardButton("🏠 Dashboard", callback_data="ui_menu")])
    return "\n".join(body_lines), InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# Activity feed
# ---------------------------------------------------------------------------
def render_activity_feed(state: StateManager) -> Tuple[str, InlineKeyboardMarkup]:
    messages = state.recent_messages(20)
    lines = ["📖 *Activity Feed*", DIVIDER]
    if not messages:
        lines.append("_No activity yet\\._")
    else:
        for m in messages:
            lines.append(md2(m))
    keyboard = [
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="ui_chat_log"),
            InlineKeyboardButton("🏠 Dashboard", callback_data="ui_menu"),
        ]
    ]
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# Prompts (waiting for next message from user)
# ---------------------------------------------------------------------------
def render_prompt(kind: str) -> Tuple[str, InlineKeyboardMarkup]:
    specs = {
        "shell": (
            "⚙ *Shell command*",
            "Type the command you want to run\\. "
            "You'll get a *preview with confirm* before anything executes\\.",
        ),
        "file": (
            "📜 *View file*",
            "Type a path *relative to the project root*\\.\n"
            "Reads are jailed inside the project tree\\.",
        ),
        "agent": (
            "🤖 *Ask the agent*",
            "Type your instruction\\. It will be queued for the next time the "
            "agent calls `check_telegram_updates` \\(or instantly if Active "
            "Mode is on\\)\\.",
        ),
        "new_conv": (
            "🚀 *New conversation*",
            "Type a short title for the new conversation\\.",
        ),
    }
    title, body = specs.get(kind, ("*Input*", "Type your input below\\."))
    text = f"{title}\n{DIVIDER}\n{body}"
    keyboard = [[InlineKeyboardButton("✖ Cancel", callback_data="ui_menu")]]
    return text, InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# Confirmations
# ---------------------------------------------------------------------------
def render_shell_confirm(token: str, command: str) -> Tuple[str, InlineKeyboardMarkup]:
    text = (
        "⚙ *Confirm shell exec*\n"
        f"{DIVIDER}\n"
        f"{inline_code(command)}\n\n"
        "_Runs in the project working directory\\. 30s timeout\\._"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Run", callback_data=f"shell_ok:{token}"),
            InlineKeyboardButton("✖ Cancel", callback_data=f"shell_no:{token}"),
        ]
    ]
    return text, InlineKeyboardMarkup(keyboard)


def render_file_confirm(token: str, path: str) -> Tuple[str, InlineKeyboardMarkup]:
    text = (
        "📜 *Confirm file read*\n"
        f"{DIVIDER}\n"
        f"{inline_code(path)}"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Open", callback_data=f"file_ok:{token}"),
            InlineKeyboardButton("✖ Cancel", callback_data=f"file_no:{token}"),
        ]
    ]
    return text, InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
def render_followup_captured(target: str) -> Tuple[str, InlineKeyboardMarkup]:
    text = (
        "🔁 *Context captured*\n"
        f"{DIVIDER}\n"
        f"Agent notified to resume work on `{md2(target)}`\\.\n\n"
        "Type your next instruction below\\."
    )
    keyboard = [
        [
            InlineKeyboardButton("🏠 Dashboard", callback_data="ui_menu"),
            InlineKeyboardButton("💬 Hub", callback_data="ui_conversations"),
        ]
    ]
    return text, InlineKeyboardMarkup(keyboard)


def render_unauthorized() -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    return ("🚫 This bot is in single\\-user mode and you're not the owner\\.", None)
