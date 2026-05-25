# 🏗️ Telegravity Architecture

Telegravity is a single Python process that does two things concurrently:

1. **MCP server** over stdio — answers JSON-RPC calls from your AI agent
   (Antigravity, Claude Code, Cursor, Cline, Zed Agent, …).
2. **Telegram bot** — long-polls `getUpdates` and renders the chat UI.

Both share an in-memory `StateManager` (with an `asyncio.Lock` around the
mutating bits) and persist to a `data/` directory.

```
┌───────────────────────────────────────────────────────────────────────┐
│                         telegravity process                           │
│                                                                       │
│   ┌────────────────┐                ┌──────────────────────────────┐  │
│   │  MCP server    │  ◄── stdio ──► │       Any MCP client         │  │
│   │  (FastMCP)     │                │ Antigravity · Claude Code …  │  │
│   │                │                └──────────────────────────────┘  │
│   └──────┬─────────┘                                                  │
│          │                                                            │
│          ▼                                                            │
│   ┌────────────────────────────────────────────────────┐              │
│   │              StateManager  (asyncio.Lock)          │              │
│   │  • message buffer       • conversations DB          │             │
│   │  • workspace list       • agent heartbeat           │             │
│   │  • user-state machine   • last_ai_index             │             │
│   └────────────────┬───────────────────────────────────┘              │
│                    ▲                                                  │
│                    │                                                  │
│   ┌────────────────┴─────────────┐                                    │
│   │  Telegram polling worker     │   ◄── HTTPS ──►  Telegram Bot API  │
│   │  • AuthGate filter           │                                    │
│   │  • Router (commands/cb)      │                                    │
│   │  • Messenger (send/edit)     │                                    │
│   │  • PendingRegistry (confirm) │                                    │
│   └──────────────────────────────┘                                    │
└───────────────────────────────────────────────────────────────────────┘
```

## Package layout

```
telegravity/
├── __init__.py
├── __main__.py            # `python -m telegravity`
├── __version__.py
├── config.py              # env loading + validation (Config dataclass)
├── paths.py               # data-dir resolution (lazy, env-overridable)
├── state.py               # StateManager (single source of truth)
├── auth.py                # AuthGate (single-user filter)
├── formatting.py          # MarkdownV2 escape, badges, timestamps
├── mcp_tools.py           # FastMCP tool definitions + Gateway binding
├── server.py              # entrypoint: wires bot + state + MCP + workers
└── ui/
    ├── messenger.py       # send-or-edit menus, manages stale message IDs
    ├── pending.py         # PendingRegistry (TTL token store for confirms)
    ├── executor.py        # gated shell + safe_read_file
    ├── views.py           # screen renderers → (text, InlineKeyboardMarkup)
    └── router.py          # command + callback routing
```

## Lifecycle

`telegravity.server.run()` orchestrates startup:

1. Load `Config` (raises `ConfigError` with a friendly message if invalid).
2. Build `StateManager` (loads `data/state.json`, conversations, logs).
3. Build `Bot`, `AuthGate`, `Messenger`, `PendingRegistry`, `Router`.
4. Bind the MCP `Gateway` so the tools can reach bot/state/config.
5. Register slash commands with Telegram.
6. Send the startup card to the authorized chat.
7. Spawn `_poll_loop` (Telegram updates) and `_watch_workspaces` (hot
   reload).
8. Hand stdin/stdout to FastMCP's stdio loop. Shutdown cancels the workers.

## Message flow

### User → Agent (passive)

```
user types "fix the bug"
        │
        ▼
poll_loop ──► AuthGate ──► Router.handle_message
                              │
                              ▼
                       state.add_message
                              │
                              ▼
       (no-op until agent calls a tool)

agent calls check_telegram_updates  ──►  state.drain_messages
                                              │
                                              ▼
                                       returns ["[12:34] user: fix the bug"]
```

### User → Agent (Active Mode)

```
agent calls wait_for_remote_instruction(300)
        │
        ▼
state.wait_for_messages   (asyncio.Event.wait)
        ▲
        │     state.add_message fires NEW_MESSAGE_EVENT.set()
        │
user types in Telegram
```

Agent returns from the long-poll the instant the event fires.

### Agent → User

`send_message`, `update_conversation`, and `register_agent_activity` all push
to Telegram via the Bot API and (for the first two) also write to the local
activity log + state.

## State model

A single `StateManager` owns:

- `workspaces: list[str]` — projects, loaded from `INITIAL_WORKSPACES` ∪
  `data/workspaces.txt`. Hot-reloaded on file change.
- `conversations: dict[str, list[Conversation]]` — per-workspace threads,
  each with `interactions: list[Interaction]` (title, summary, files, steps,
  content, time).
- `message_buffer: list[str]` — ring buffer (configurable via
  `Config.BUFFER_LIMIT`, default 200).
- `last_ai_index: int` — cursor into the buffer; advances each time the agent
  drains messages.
- `agent: AgentHeartbeat` — last `status` and `detail` posted via
  `register_agent_activity`. Used by `render_dashboard`.
- `user_state: str` — small FSM for multi-step dialogs (waiting for a shell
  command, file path, agent prompt, new-conv title).
- `pending` (kept separately on the `Router`) — token-keyed dict of confirm
  prompts with TTL.

All mutating operations on the buffer go through an `asyncio.Lock` so the
Telegram worker and the MCP coroutines cannot race on `last_ai_index`.

## Security boundaries

- **Inbound auth**: `AuthGate.message_allowed` / `callback_allowed` compare
  `from_user.id` to `Config.authorized_chat_id`. Mismatches log an INFO line
  with the scanning chat_id and are silently dropped.
- **Shell exec**: opt-in (`ENABLE_SHELL_EXEC=1`). Every command is held in
  `PendingRegistry` for up to 60s and only runs after the user taps ✅.
  Output is truncated to 1500 chars per stream. 30s subprocess timeout.
- **File view**: opt-in. `safe_read_file` resolves the path relative to
  `Path.cwd()` and verifies the resolved path is still inside CWD via
  `Path.relative_to`. Rejects symlink escapes, directories, and files larger
  than 256 KB.
- **No outbound calls** besides Telegram and MCP stdio. No telemetry.

## UI ergonomics

- `Messenger.send_menu` tries `edit_message_text` first (so the dashboard
  feels instantaneous when tapping inline buttons), falls back to delete +
  send when that's not possible.
- `views.*` return `(text, InlineKeyboardMarkup)` pairs — each screen is one
  function, easy to A/B without touching the router.
- `formatting.md2` escapes MarkdownV2 specials so user-supplied text
  (workspace names, conversation titles, file paths) never breaks rendering.
- The activity feed and conversation steps share a consistent badge palette
  (`🟢 active`, `⚡ executing`, `✅ done`, `❌ error`, `💭 thinking`).

## Extending

- **New screen**: add a `render_*` function in `ui/views.py` and a callback
  branch in `ui/router.py`.
- **New MCP tool**: add to `telegravity/mcp_tools.py`. The `_gw()` helper
  gives you `bot`, `state`, `config`.
- **New workspace source**: extend `StateManager._load_workspaces` (e.g. read
  from a config file, a git submodule, …).
