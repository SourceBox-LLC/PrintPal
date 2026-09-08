# AGENTS.md

Instructions for AI coding agents working on the PrintPal codebase.

## What is PrintPal?

PrintPal is a terminal-based 3D printing assistant. It uses an AI agent (smolagents + LiteLLM) to drive a 3D printing pipeline via an MCP server called PrintMCP. The agent searches Thingiverse, downloads models, slices them with CuraEngine **or OrcaSlicer**, and prints them via OctoPrint — all from a REPL with slash commands.

## Tech stack

- **Python 3.10+** (target `>=3.10` in pyproject.toml)
- **uv** for dependency management — `uv sync` to install, `uv run printpal` to run
- **smolagents** (HuggingFace) — the agent framework that runs the LLM and executes tool calls
- **PrintMCP** (PyPI: `printmcp`) — the MCP server providing Thingiverse/Cura/OrcaSlicer/OctoPrint tools, launched via `uvx printmcp`
- **Rich** — terminal UI (panels, tables, styled text)
- **prompt_toolkit** — input handling (placeholder text, arrow-key history, Shift+Tab key bindings)
- **SQLite** — everything is stored in `~/.printpal/printpal.db` (sessions, things as BLOBs, settings, logs)

## File structure

| File | Responsibility | Key things to know |
|------|---------------|-------------------|
| `src/printpal/app.py` | Entry point, bootstrap, REPL loop, command dispatch | Contains `_inject_db_settings()`, `_sanitize_session_name()`, error resilience wrappers, auto-save logic. Command args are parsed with `shlex` (quoted values work). `_printmcp_server_params()` picks `uvx printmcp` (PyPI) by default, or the `PRINTPAL_PRINTMCP_COMMAND` override for a local checkout. `MODEL_ID` is imported from `config.py`. |
| `src/printpal/config.py` | App-level constants | `MODEL_ID`, `SETTING_TO_ENV` (DB key → env var mapping), `ORCA_DEFAULTS` + `ORCA_FLAG_OVERRIDES` (default OrcaSlicer presets + slice-flag → setting map), `TIPS`, `EXAMPLES`. When model switching is added, the model registry will live here. |
| `src/printpal/commands/` | All `/slash` command implementations (sub-package) | `__init__.py` re-exports all `cmd_*` functions + `COMMANDS` dict. Split by domain: `session.py`, `thing.py` (incl. `/slice` with Cura/Orca backend pick), `printer.py` (`/printer` presets), `print.py`, `mode.py`, `admin.py`, `help.py`, `helpers.py`. |
| `src/printpal/permissions.py` | Permission system | `PermissionTool` subclasses `smolagents.Tool` (required by CodeAgent's isinstance check). Wraps each MCP tool, intercepts `forward()`. Three modes: DEFAULT (ask all), AUTO (read-only/safe auto-approved), BYPASS (everything auto-approved). Per-session allow-list stored in DB. |
| `src/printpal/sessions.py` | Session save/load | Serializes `AgentMemory` steps to JSON, reconstructs on load. Drops `model_input_messages` on load (not needed for continuation). `load_session()` returns a dict with `success`, `prompt_history`, and `permissions`. |
| `src/printpal/db.py` | SQLite layer | Every function opens/closes its own connection (uses WAL mode). `init_db()` adds columns incrementally for schema migrations. `migrate_to_blob_storage()` converts old `file_path` rows to `file_data` BLOBs. |
| `src/printpal/scanner.py` | Download + slice scanner | Walks agent memory after `agent.run()` to detect `thingiverse_download_model` and (`cura_slice_model` or `orca_slice_model`) calls. Reads files from disk into BLOBs, deletes disk files. |
| `src/printpal/completer.py` | Command autocomplete | `CommandCompleter` does prefix matching on slash commands. Only activates when input starts with `/`. |
| `src/printpal/pricing.py` | Model pricing data | `MODEL_PRICING` dict (per-1M-token prices), `MASKED_KEYS`, `RESTART_KEYS`. |
| `src/printpal/ui.py` | Shared UI constants + helpers | `console = Console(highlight=False)`, `ACCENT = "#d4b702"` (matches smolagents' yellow), `LOGO` (ASCII art), `format_size()`, `format_duration()`, `prompt_yes_no()`, `make_bar()` (visual progress bars), `format_tokens()` (compact token formatting). Import from here, don't create new Console instances. |

## Key patterns

### MCP tool calling
PrintMCP runs as a subprocess via `uvx printmcp`. `MCPClient` connects to it over stdio. Tools are returned as smolagents `Tool` instances. We wrap them with `PermissionTool` before passing to `CodeAgent`:
```python
wrapped_tools = [PermissionTool(t, perm_state) for t in tools]
agent = CodeAgent(tools=wrapped_tools, model=model)
```

### Direct tool calls (slash commands)
`/slice`, `/print`, etc. call MCP tools directly via `call_tool()` or `tool.forward()` — no LLM, no tokens spent. These bypass the permission system since they're user-initiated.

### Download + slice scanner
smolagents wraps all MCP tool calls inside a Python code executor, so `step.tool_calls[0].name` is always `python_interpreter`, not the actual tool name. The scanner (in `scanner.py`) checks `step.code_action` for `thingiverse_download_model`/`cura_slice_model`/`orca_slice_model`, parses the results from `step.observations` using `ast.literal_eval`, reads the files from disk into BLOBs, and deletes the disk files.

### mcpadapt monkeypatch
`jsonref.replace_refs` (used by mcpadapt) returns lazy proxy objects that aren't JSON-serializable. We monkeypatch it in `app.py` to deep-copy the result. This is a known mcpadapt 0.1.20 bug.

### Auto-save
When `auto_save` setting is `"true"`, sessions are auto-saved after each `agent.run()`. The session name is derived from the user's first prompt (sanitized to `[a-z0-9-]`, max 40 chars, deduplicated). `current_session_name` variable tracks the active session across the REPL loop.

### Error handling
The REPL loop has nested try/except: outer catches `EOFError`/`KeyboardInterrupt` for clean exit, inner catches `Exception` for command errors (prints red, logs to DB, continues). Agent runs catch `KeyboardInterrupt` separately ("Interrupted.") and `Exception` ("Agent error:").

## Environment variables

| Variable | Source | Purpose |
|----------|--------|---------|
| `ANTHROPIC_API_KEY` | `.env` | LLM API key for Claude |
| `THINGIVERSE_TOKEN` | `.env` or `/config` | Thingiverse API access |
| `OCTOPRINT_URL` | `.env` or `/config` | OctoPrint server URL |
| `OCTOPRINT_API_KEY` | `.env` or `/config` | OctoPrint API key |
| `PRINTMCP_CURA_DIR` | `.env` or `/config` | Cura install path (auto-detected if unset) |
| `PRINTMCP_ORCA_COMMAND` | `.env` or `/config` | OrcaSlicer launch command (auto-detected if unset) |
| `PRINTMCP_ORCA_PROFILES` | `.env` or `/config` | OrcaSlicer bundled presets dir (auto-detected if unset) |
| `PRINTPAL_PRINTMCP_COMMAND` | env only | Override the PrintMCP launch command (e.g. `uv run --directory /path/to/PrintMCP printmcp`) to use a local checkout instead of PyPI. |

DB settings (via `/config set`) override `.env` values. They're injected into `os.environ` on startup before the MCP server starts.

## Testing

`pytest` (in dev dependencies) — `uv run python -m pytest` from the repo root. Tests are offline
and isolate the DB (monkeypatch `db.DB_PATH` to a temp file). Mark end-to-end tests with
`@pytest.mark.integration`. Lint with `uvx ruff check src tests` (or `uvx ruff check .`).

## Things to avoid

- Don't create new `Console()` instances — use `from ui import console`
- Don't call MCP tools without the `call_tool()` wrapper (it catches exceptions)
- Don't store files on disk — everything goes in the SQLite DB as BLOBs
- Don't add dependencies without checking they work with Python 3.10
- Don't change the `ACCENT` color (`#d4b702`) — it matches smolagents' theme
- Don't modify `permissions.py` tool categories without considering the safety implications
- Don't use `print()` for UI output — use `console.print()` with Rich `Text` objects

## PrintMCP

PrintMCP is a separate project: https://github.com/SourceBox-LLC/PrintMCP

It's installed via `uvx printmcp` (no local install needed). PrintPal launches it as a subprocess and talks to it over stdio. If PrintMCP needs changes, work on that repo separately — don't modify PrintMCP code inside PrintPal.