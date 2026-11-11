import pytest

from telegravity.formatting import (
    SAFE_TEXT_LIMIT,
    badge,
    code_block,
    inline_code,
    iso_utc,
    md2,
    now_str,
    short,
    split_message,
    truncate_block,
    utf16_len,
)


def test_md2_escapes_all_specials():
    raw = "a_b*c[d](e)f~g`h>i#j+k-l=m|n{o}p.q!r\\"
    escaped = md2(raw)
    # Every special must be preceded by a backslash; no special slips through unescaped.
    for ch in raw:
        if ch in r"_*[]()~`>#+-=|{}.!\\":
            assert "\\" + ch in escaped


def test_md2_leaves_plain_text_alone():
    assert md2("hello world") == "hello world"


def test_code_block_escapes_inner_backticks():
    body = code_block("```\nx\n```", "py")
    assert body.startswith("```py\n")
    assert body.endswith("\n```")
    assert "\\`" in body


def test_inline_code_escapes_backticks_and_backslashes():
    out = inline_code("a`b\\c")
    assert "\\`" in out
    assert "\\\\" in out


def test_now_str_format():
    s = now_str()
    # YYYY-MM-DD HH:MM:SS
    assert len(s) == 19
    assert s[4] == "-" and s[10] == " "


def test_iso_utc_has_timezone():
    s = iso_utc()
    assert "+" in s or s.endswith("Z") or "-" in s[10:]


def test_short_pads_under_limit():
    assert short("hi", 10) == "hi"


def test_short_truncates_over_limit():
    out = short("abcdefghijklmnop", 8)
    assert out.endswith("…")
    assert len(out) == 8


def test_truncate_block_passes_short_text():
    assert truncate_block("hi", 100) == "hi"


def test_truncate_block_appends_suffix():
    out = truncate_block("x" * 500, limit=50, suffix="..end")
    assert out.endswith("..end")
    assert len(out) == 50


def test_badge_known_and_unknown():
    assert badge("active") == "🟢"
    assert badge("executing") == "⚡"
    assert badge("not-a-badge") == "•"


# ---------------------------------------------------------------------------
# Telegram's 4096-unit message limit
# ---------------------------------------------------------------------------
def test_utf16_len_counts_what_telegram_counts():
    assert utf16_len("abc") == 3
    # Astral plane: one Python character, two UTF-16 units.
    assert utf16_len("𝔘") == 2
    # Emoji + variation selector: two characters, three units.
    assert utf16_len("🛰️") == 3


def test_split_message_leaves_short_text_alone():
    assert split_message("hello") == ["hello"]
    assert split_message("a" * SAFE_TEXT_LIMIT) == ["a" * SAFE_TEXT_LIMIT]


def test_split_message_respects_the_limit_in_utf16_units():
    # len() would say this fits in two chunks; UTF-16 says otherwise, and
    # Telegram agrees with UTF-16.
    text = "🛰️" * 3000
    chunks = split_message(text)
    assert len(chunks) > 1
    assert all(utf16_len(c) <= SAFE_TEXT_LIMIT for c in chunks)
    assert "".join(chunks) == text


def test_split_message_prefers_line_breaks():
    text = "\n".join(f"line {i}" for i in range(3000))
    chunks = split_message(text)
    assert len(chunks) > 1
    # No chunk starts or ends mid-line.
    for chunk in chunks:
        assert chunk.splitlines()[0].startswith("line ")
        assert chunk.splitlines()[-1].startswith("line ")


def test_split_message_hard_cuts_a_single_oversized_line():
    text = "x" * (SAFE_TEXT_LIMIT * 2 + 11)
    chunks = split_message(text)
    assert len(chunks) == 3
    assert "".join(chunks) == text


def test_split_message_never_yields_an_empty_chunk():
    for text in ("", "\n" * (SAFE_TEXT_LIMIT + 50), "   "):
        chunks = split_message(text)
        assert chunks  # always at least one
    assert all(c for c in split_message("a\n\n\n\n" + "b" * (SAFE_TEXT_LIMIT + 5)))


def test_split_message_rejects_a_nonsensical_limit():
    with pytest.raises(ValueError):
        split_message("anything", limit=1)
