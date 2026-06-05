# 🛰️ Telegravity

> *Chat-control for any MCP agent.*
> The orbital uplink between Telegram and your AI coding agent —
> works with **Antigravity**, **Claude Code**, **Cursor**, **Cline**, **Zed Agent**,
> or anything else that speaks the Model Context Protocol.

Telegravity is a single-binary MCP server that turns Telegram into a remote
cockpit for your AI coding agent. It exposes a tiny set of tools the agent
calls to pull your instructions, post live status updates, and stream
conversation history — while the Telegram side gives you a polished
dashboard, conversation hub, and an *Active Mode* that wakes the agent the
instant you type.

## ✨ What you get

- **Wow-effect onboarding** — first `/start` runs a four-step guided tour
- **Live dashboard** with agent heartbeat (`💭 Thinking · ⚡ Executing · ✅ Done`),
  unread inbox counter, current workspace, and chat-mode badge
- **Conversation hub** — per-thread history with interaction logs, files
  touched, and step counters
- **Active Mode** — `wait_for_remote_instruction` long-polls so the agent
  reacts to your Telegram messages in milliseconds
- **Path-aware workspaces** — pick a project in Telegram and the agent is told
  its real directory (auto-imported from Antigravity's project registry);
  queued instructions arrive tagged with the target path
- **Agent execution, scoped to the workspace** — `run_command` / `read_file` /
  `write_file` run jailed to the selected project's directory, so a remote
  selection takes effect even when a different folder is open in the IDE (opt-in)
- **Single-user lockdown** — only your authorized `chat_id` can drive the bot
- **Confirm-to-execute** shell and file-view actions from the dashboard too
- **MarkdownV2 throughout** — user-supplied text never breaks the layout

## 🚀 Install

```bash
pip install telegravity
```

or, from source:

```bash
git clone https://github.com/yourusername/telegravity.git
cd telegravity
pip install -e .
```

## 🔑 Configure

Create a `.env` in the project where you want to run the agent:

```env
# Required
TELEGRAM_TOKEN=123456:ABC...           # from @BotFather
AUTHORIZED_CHAT_ID=123456789           # ask @userinfobot on Telegram

# Optional
INITIAL_WORKSPACES=MyApp,SideProject
ENABLE_SHELL_EXEC=0                    # 1 to allow run_command + chat shell
ENABLE_FILE_VIEW=0                     # 1 to allow read_file + chat file view
ENABLE_FILE_WRITE=0                    # 1 to allow the agent's write_file tool
# TELEGRAVITY_AUTOIMPORT=1             # auto-import Antigravity projects (default on)
# TELEGRAVITY_WORKSPACE_BASE=/abs/dir  # give bare labels a path under <base>/<label>
# TELEGRAVITY_DATA_DIR=/abs/path       # default ~/.telegravity
```

## 🧩 Wire to your MCP client

Add this to your MCP configuration. The block name (`telegravity` here) is
arbitrary — the *command* is what matters.

<details open>
<summary><b>Antigravity</b> — <code>mcp_config.json</code></summary>

```json
{
  "mcpServers": {
    "telegravity": {
      "command": "telegravity",
      "env": {
        "TELEGRAM_TOKEN": "...",
        "AUTHORIZED_CHAT_ID": "..."
      }
    }
  }
}
```
</details>

<details>
<summary><b>Claude Code</b> — <code>~/.claude.json</code> (or per-project <code>.mcp.json</code>)</summary>

```json
{
  "mcpServers": {
    "telegravity": {
      "command": "telegravity",
      "env": {
        "TELEGRAM_TOKEN": "...",
        "AUTHORIZED_CHAT_ID": "..."
      }
    }
  }
}
```

Or one-liner: `claude mcp add telegravity -e TELEGRAM_TOKEN=... -e AUTHORIZED_CHAT_ID=... -- telegravity`
</details>

<details>
<summary><b>Cursor / Cline / Zed Agent</b></summary>

All three read the same MCP server schema. Drop the block above into the
client's MCP settings file. Refer to your IDE docs for the exact path.
</details>

If you installed in a venv and the `telegravity` command isn't on `PATH`,
either point `command` at `/abs/path/to/venv/bin/telegravity` or use
`python -m telegravity`.

Runtime data (state, conversations, logs, workspace list) is written to
`~/.telegravity` by default — no working directory required, so the config
above works out of the box. Set `TELEGRAVITY_DATA_DIR` in the `env` block to
relocate it.

## 🎮 Use it

1. Open the chat with your bot and send `/start` — welcome card + 30-second
   tour show up.
2. Pick a workspace from the dashboard — the project you want the agent to work
   on. Workspaces (and their real directories) are auto-imported from
   Antigravity's project registry; add your own in `workspaces.txt`.
3. In your IDE, install the bundled [`SKILL.md`](SKILL.md) (Active Mode) and ask
   the agent to *"enter Active Mode"*. It calls `wait_for_remote_instruction`,
   parks, and wakes on every Telegram message.
4. Type your instruction in Telegram. It arrives tagged with the workspace's
   directory; the agent works there — using its own tools, or Telegravity's
   workspace-rooted `run_command` / `read_file` / `write_file` when the chosen
   project isn't the folder open in the IDE — reports back with `send_message`,
   and animates the dashboard via `update_conversation` /
   `register_agent_activity`.

### Slash commands

| Command            | Action                              |
| ------------------ | ----------------------------------- |
| `/menu`            | Open the dashboard                  |
| `/conversations`   | Open the conversation hub           |
| `/workspaces`      | Switch workspace                    |
| `/chat`            | Toggle Chat Mode                    |
| `/activity`        | Show the activity feed              |
| `/reload`          | Re-scan all workspace sources       |
| `/help`            | Show the welcome card               |

## 🔧 MCP tools exposed to the agent

| Tool                              | Purpose                                                                |
| --------------------------------- | ---------------------------------------------------------------------- |
| `check_telegram_updates()`        | Drain buffered Telegram messages since last call                        |
| `wait_for_remote_instruction(t)`  | Long-poll up to `t` seconds for the next user message — *Active Mode*   |
| `send_message(text)`              | Push a message from agent → user                                        |
| `register_agent_activity(...)`    | Heartbeat for the dashboard (`thinking` / `executing` / `done` / …)     |
| `get_state()`                     | Compact snapshot of workspace, its directory, conversations, buffer     |
| `set_active_workspace(name)`      | Switch the active workspace (the project to work on)                    |
| `run_command(cmd, timeout_sec)`   | Run a shell command in the active workspace's dir (`ENABLE_SHELL_EXEC`)  |
| `read_file(rel_path)`             | Read a file under the active workspace (`ENABLE_FILE_VIEW`)             |
| `write_file(rel_path, content)`   | Write a file under the active workspace (`ENABLE_FILE_WRITE`)           |
| `update_conversation(...)`        | Add a rich interaction log (title, summary, files, progress, content)   |
| `import_conversations(ws, [...])` | Bulk-seed conversation titles (idempotent)                              |

Plus the resource `telegram://inbox` for read-only buffer access.

## ⚠️ Limitations to know

- **MCP is reactive.** Your agent only calls these tools when it's running.
  Without Active Mode, Telegram messages sit in the buffer until the agent
  thinks again. Use `wait_for_remote_instruction` for instant pickup.
- **Telegravity can't switch the IDE's open folder.** No MCP primitive can
  redirect Antigravity to another project. Instead the selected workspace's
  *path* is handed to the agent, and `run_command` / `read_file` / `write_file`
  operate on that directory — so a remote workspace selection takes effect even
  when a different folder is open in the IDE.
- **One Telegram identity.** This is a *single-user* tool by design — the
  whole security model leans on the `AUTHORIZED_CHAT_ID` filter.
- **One bot, one process.** The bot uses long-poll `get_updates`; running
  two copies against the same token will cause Telegram-side conflicts.
- **No transport encryption claim.** State lives as JSON under `~/.telegravity/`
  (or your `TELEGRAVITY_DATA_DIR`).
  Don't store secrets in conversation titles or summaries.

## 🛡️ Security model

- Every inbound update is filtered against `AUTHORIZED_CHAT_ID`.
  Unauthorized senders are logged and silently ignored.
- Shell exec and file read/write are *off* by default (`ENABLE_SHELL_EXEC` /
  `ENABLE_FILE_VIEW` / `ENABLE_FILE_WRITE`). The dashboard's shell/file actions
  go through a tap-to-confirm prompt with a 60-second TTL. `read_file` /
  `write_file` are path-jailed to the selected workspace directory (the current
  working directory only as a fallback); `run_command` runs with its `cwd` set
  to that directory.
- The Telegram bot token never leaves the process. No outbound network
  calls besides Telegram and the MCP transport (stdio).

## 🧪 Develop

```bash
pip install -e ".[dev]"
pytest                # full suite + coverage report + 90% threshold
```

Run the package directly:

```bash
python -m telegravity
```

Tests: **210 passing · 93% coverage (90% enforced) · branch coverage on**.

## 📐 Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the deep dive.

## 📜 License

MIT.
