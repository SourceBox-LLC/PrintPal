"""Tests for the PrintMCP server-command override in app.main's bootstrap.

PrintPal launches PrintMCP as a stdio subprocess. By default it uses the
published PyPI package (``uvx printmcp``); setting PRINTPAL_PRINTMCP_COMMAND
lets a developer point at a local checkout instead (e.g.
``uv run --directory /path/to/PrintMCP printmcp``). These tests pin that
behavior so the default path can't regress.
"""

from __future__ import annotations

from printpal.app import _printmcp_server_params


def test_default_is_pypi_uvx(monkeypatch):
    """No override -> default to the published server via uvx."""
    monkeypatch.delenv("PRINTPAL_PRINTMCP_COMMAND", raising=False)
    params, source = _printmcp_server_params()
    assert params.command == "uvx"
    assert params.args == ["printmcp"]
    assert "pypi" in source
    assert (params.env or {}).get("PYTHONUNBUFFERED") == "1"


def test_override_command_and_label(monkeypatch):
    """An override is shlex-split with args and labeled as local."""
    monkeypatch.setenv(
        "PRINTPAL_PRINTMCP_COMMAND",
        "uv run --directory '/opt/PrintMCP checkout' printmcp",
    )
    params, source = _printmcp_server_params()
    assert params.command == "uv"
    # shlex removed the quotes around the spaced path but kept it one arg.
    assert params.args == ["run", "--directory", "/opt/PrintMCP checkout", "printmcp"]
    assert source.startswith("local (")
    assert "printmcp" in source


def test_override_python_module_form(monkeypatch):
    """python -m printmcp works too (venv with printmcp installed)."""
    monkeypatch.setenv("PRINTPAL_PRINTMCP_COMMAND", "python -m printmcp")
    params, source = _printmcp_server_params()
    assert params.command == "python"
    assert params.args == ["-m", "printmcp"]
    assert "local" in source


def test_whitespace_override_falls_back_to_default(monkeypatch):
    """A whitespace-only override is treated as unset."""
    monkeypatch.setenv("PRINTPAL_PRINTMCP_COMMAND", "   ")
    params, source = _printmcp_server_params()
    assert params.command == "uvx"
    assert "pypi" in source
