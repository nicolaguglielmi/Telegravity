"""Renderers should produce deterministic Markdown + button layouts."""

import pytest
from telegram import InlineKeyboardMarkup

from telegravity.ui import views


def _button_texts(markup: InlineKeyboardMarkup) -> list[str]:
    return [b.text for row in markup.inline_keyboard for b in row]


def _callback_data(markup: InlineKeyboardMarkup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------
def test_render_welcome_addresses_user(state):
    text, markup = views.render_welcome(state, "Nicola")
    assert "Nicola" in text
    assert "🛰️" in text
    assert "tour:1" in _callback_data(markup)
    assert "ui_menu" in _callback_data(markup)


def test_render_welcome_without_name(state):
    text, _ = views.render_welcome(state, "")
    assert "Hi" not in text  # no greeting when name missing


def test_render_tour_each_step_has_nav(state):
    for step in range(1, 5):
        text, markup = views.render_tour(step)
        assert f"{step} /" in text
        # First step has only Next; last has finish; middle have both
        cbs = _callback_data(markup)
        if step == 1:
            assert "tour:2" in cbs
            assert not any("tour:0" in c for c in cbs)
        elif step == 4:
            assert "ui_menu" in cbs
        else:
            assert f"tour:{step-1}" in cbs
            assert f"tour:{step+1}" in cbs


def test_render_tour_clamps_out_of_range(state):
    text_high, _ = views.render_tour(99)
    text_max, _ = views.render_tour(4)
    assert text_high == text_max
    text_low, _ = views.render_tour(-1)
    text_min, _ = views.render_tour(1)
    assert text_low == text_min


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def test_dashboard_without_workspace_shows_picker(state, config):
    state.workspaces = ["Alpha", "Beta", "Gamma"]
    text, markup = views.render_dashboard(state, config)
    assert "not selected" in text
    cbs = _callback_data(markup)
    assert "select:Alpha" in cbs
    assert "select:Beta" in cbs
    assert "ui_sync" in cbs


def test_dashboard_without_workspaces_hints_user(state, config):
    state.workspaces = []
    text, _ = views.render_dashboard(state, config)
    assert "No workspaces" in text


def test_dashboard_with_workspace_shows_focus(state, config):
    state.workspaces = ["Alpha"]
    state.current_workspace = "Alpha"
    state.add_conversation("Alpha", "Build feature")
    state.active_conversation_index = 0
    text, markup = views.render_dashboard(state, config)
    assert "Alpha" in text
    assert "Build feature" in text
    assert "Conversations (1)" in " ".join(_button_texts(markup))


def test_dashboard_inbox_counter(state, config):
    import asyncio

    state.workspaces = ["Alpha"]
    state.current_workspace = "Alpha"
    asyncio.run(state.add_message("msg1"))
    asyncio.run(state.add_message("msg2"))
    text, _ = views.render_dashboard(state, config)
    assert "2 new" in text


def test_dashboard_shell_button_only_when_enabled(state, monkeypatch, data_dir):
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("AUTHORIZED_CHAT_ID", "1")
    monkeypatch.setenv("ENABLE_SHELL_EXEC", "1")
    monkeypatch.setenv("ENABLE_FILE_VIEW", "1")
    from telegravity.config import Config

    cfg = Config.load()
    state.current_workspace = "Alpha"
    state.workspaces = ["Alpha"]
    _, markup = views.render_dashboard(state, cfg)
    cbs = _callback_data(markup)
    assert "ui_prompt_command" in cbs
    assert "ui_prompt_file" in cbs


def test_dashboard_chat_mode_label_reflects_state(state, config):
    state.workspaces = ["Alpha"]
    state.current_workspace = "Alpha"
    state.chat_mode = True
    text, markup = views.render_dashboard(state, config)
    assert "`ON`" in text
    assert any("Chat: ON" in b.text for row in markup.inline_keyboard for b in row)


# ---------------------------------------------------------------------------
# Workspace picker
# ---------------------------------------------------------------------------
def test_workspace_picker_empty(state):
    state.workspaces = []
    text, markup = views.render_workspace_picker(state)
    assert "No workspaces" in text
    assert "ui_menu" in _callback_data(markup)


def test_workspace_picker_pairs_buttons(state):
    state.workspaces = ["A", "B", "C", "D", "E"]
    _, markup = views.render_workspace_picker(state)
    # Five workspaces → three rows (2+2+1) + back row
    assert len(markup.inline_keyboard) >= 3


# ---------------------------------------------------------------------------
# Conversation hub + details
# ---------------------------------------------------------------------------
def test_conversation_hub_empty(state):
    state.current_workspace = "Alpha"
    text, markup = views.render_conversation_hub(state)
    assert "No conversations" in text
    assert "ui_menu" in _callback_data(markup)


def test_conversation_hub_lists_threads(state):
    state.current_workspace = "Alpha"
    state.add_conversation("Alpha", "Thread A")
    state.add_conversation("Alpha", "Thread B")
    state.conversations["Alpha"][0]["status"] = "done"
    text, markup = views.render_conversation_hub(state)
    assert "Thread A" in text or any("Thread A" in b for b in _button_texts(markup))
    cbs = _callback_data(markup)
    assert "conv_view:0" in cbs
    assert "conv_view:1" in cbs


def test_conversation_detail_missing_index(state):
    state.current_workspace = "Alpha"
    text, markup = views.render_conversation_detail(state, 99)
    assert "not found" in text
    assert "ui_conversations" in _callback_data(markup)


def test_conversation_detail_with_interactions(state):
    state.current_workspace = "Alpha"
    state.add_conversation("Alpha", "Build")
    state.conversations["Alpha"][0]["interactions"] = [
        {"title": "step one", "time": "12:00"},
        {"title": "step two", "time": "12:01"},
    ]
    text, markup = views.render_conversation_detail(state, 0)
    assert "Build" in text
    cbs = _callback_data(markup)
    assert "int_view:0:0" in cbs
    assert "int_view:0:1" in cbs
    assert "ui_enter_chat:0" in cbs


def test_conversation_detail_no_interactions(state):
    state.current_workspace = "Alpha"
    state.add_conversation("Alpha", "Empty")
    text, _ = views.render_conversation_detail(state, 0)
    assert "No interactions" in text


def test_interaction_detail_missing(state):
    state.current_workspace = "Alpha"
    text, markup = views.render_interaction_detail(state, 99, 0)
    assert "not found" in text


def test_interaction_detail_missing_step(state):
    state.current_workspace = "Alpha"
    state.add_conversation("Alpha", "X")
    text, markup = views.render_interaction_detail(state, 0, 5)
    assert "Step not found" in text
    assert "conv_view:0" in _callback_data(markup)


def test_interaction_detail_renders_all_fields(state):
    state.current_workspace = "Alpha"
    state.add_conversation("Alpha", "Topic")
    state.conversations["Alpha"][0]["interactions"] = [
        {
            "title": "Step",
            "summary": "did the thing",
            "files": ["a.py", "b.py"],
            "content": "console output here",
            "time": "12:00",
        },
        {"title": "Step 2", "time": "12:01"},
    ]
    text, markup = views.render_interaction_detail(state, 0, 0)
    assert "did the thing" in text
    # File paths are MarkdownV2-escaped (`.` → `\.`)
    assert "a\\.py" in text
    assert "console output here" in text
    # Only Next nav since we're at first
    cbs = _callback_data(markup)
    assert "int_view:0:1" in cbs
    assert not any(c == "int_view:0:-1" for c in cbs)


def test_interaction_detail_prev_nav_on_last_step(state):
    state.current_workspace = "Alpha"
    state.add_conversation("Alpha", "Topic")
    state.conversations["Alpha"][0]["interactions"] = [
        {"title": "S1", "time": "12:00"},
        {"title": "S2", "time": "12:01"},
    ]
    _, markup = views.render_interaction_detail(state, 0, 1)
    cbs = _callback_data(markup)
    assert "int_view:0:0" in cbs


# ---------------------------------------------------------------------------
# Activity feed + prompts + confirms + misc
# ---------------------------------------------------------------------------
def test_activity_feed_empty(state):
    text, _ = views.render_activity_feed(state)
    assert "No activity" in text


def test_activity_feed_with_messages(state):
    import asyncio

    asyncio.run(state.add_message("[12:00] user: hi"))
    text, _ = views.render_activity_feed(state)
    assert "user" in text and "hi" in text


def test_prompt_renders_each_kind():
    for kind in ("shell", "file", "agent", "new_conv"):
        text, markup = views.render_prompt(kind)
        assert text
        assert "ui_menu" in _callback_data(markup)


def test_prompt_unknown_kind_default():
    text, _ = views.render_prompt("totally-unknown")
    assert "Input" in text


def test_shell_confirm_buttons():
    text, markup = views.render_shell_confirm("tok123", "ls -la")
    assert "ls" in text
    cbs = _callback_data(markup)
    assert "shell_ok:tok123" in cbs
    assert "shell_no:tok123" in cbs


def test_file_confirm_buttons():
    text, markup = views.render_file_confirm("tok456", "README.md")
    assert "README" in text
    cbs = _callback_data(markup)
    assert "file_ok:tok456" in cbs


def test_followup_captured():
    text, markup = views.render_followup_captured("Build feature")
    assert "Build feature" in text
    assert "ui_menu" in _callback_data(markup)


def test_unauthorized_has_no_markup():
    text, markup = views.render_unauthorized()
    assert "single" in text
    assert markup is None
