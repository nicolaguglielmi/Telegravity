from telegravity.formatting import (
    badge,
    code_block,
    inline_code,
    iso_utc,
    md2,
    now_str,
    short,
    truncate_block,
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
