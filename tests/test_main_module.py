"""``python -m telegravity`` should defer to ``server.main``."""

from unittest.mock import patch


def test_main_module_calls_server_main():
    with patch("telegravity.server.main") as fake_main:
        import importlib
        import telegravity.__main__ as m

        importlib.reload(m)
        # __main__ does not auto-invoke unless run as a script; check the import path is wired.
        assert m.main is not None


def test_run_as_module(monkeypatch):
    called = {}

    def fake_main():
        called["yes"] = True

    monkeypatch.setattr("telegravity.server.main", fake_main)

    # Simulate ``python -m telegravity`` by executing the file with __name__ == "__main__".
    import runpy

    runpy.run_module("telegravity", run_name="__main__")
    assert called.get("yes") is True


def test_package_exposes_version():
    import telegravity

    assert telegravity.__version__
