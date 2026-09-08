"""PrintPal application — entry point, bootstrap, and REPL loop.

This module sets up the MCP connection, wraps tools with permissions, creates
the AI agent, and runs the interactive REPL that dispatches slash commands
and natural language prompts.
"""

from __future__ import annotations

import copy
import os
import random
import re
import sys

import jsonref
from dotenv import load_dotenv
from mcp import StdioServerParameters
from smolagents import CodeAgent, LiteLLMModel, MCPClient

try:
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.keys import Keys

    _HAS_PT = True
except ImportError:
    _HAS_PT = False

from rich.panel import Panel
from rich.text import Text

from . import db
from .commands import (
    COMMANDS,
    cmd_backup,
    cmd_config,
    cmd_cost,
    cmd_help,
    cmd_load,
    cmd_logs,
    cmd_mode,
    cmd_print,
    cmd_print_cancel,
    cmd_print_connect,
    cmd_print_disconnect,
    cmd_print_files,
    cmd_print_pause,
    cmd_print_queue,
    cmd_print_resume,
    cmd_print_status,
    cmd_printer,
    cmd_save,
    cmd_self_destruct,
    cmd_sessions,
    cmd_slice,
    cmd_thing_dispatch,
    prompt_save_if_dirty,
)
from .completer import CommandCompleter
from .config import EXAMPLES, MODEL_ID, SETTING_TO_ENV, TIPS
from .permissions import ApprovalMode, PermissionState, PermissionTool
from .scanner import scan_for_downloads
from .sessions import _resolve_name, migrate_json_sessions, save_session
from .ui import ACCENT, LOGO, console, format_tokens, make_bar

load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# --- mcpadapt 0.1.20 monkeypatch ---
# jsonref.replace_refs returns lazy proxy objects that aren't JSON-serializable.
# mcpadapt passes these into Tool.output_schema, and smolagents later calls
# json.dumps(output_schema) -> TypeError. Deep-copy forces proxies to materialize.
_original_replace_refs = jsonref.replace_refs


def _replace_refs_jsonable(*args, **kwargs):
    result = _original_replace_refs(*args, **kwargs)
    return copy.deepcopy(result)


jsonref.replace_refs = _replace_refs_jsonable


def _inject_db_settings() -> None:
    """Load DB settings into os.environ (overriding .env values)."""
    settings = db.get_all_settings()
    for db_key, env_key in SETTING_TO_ENV.items():
        if settings.get(db_key):
            os.environ[env_key] = settings[db_key]


def _printmcp_server_params() -> tuple[StdioServerParameters, str]:
    """Build the StdioServerParameters for the PrintMCP server.

    Default: ``uvx printmcp`` (the release published on PyPI). Set the
    ``PRINTPAL_PRINTMCP_COMMAND`` environment variable to override the launch
    command — e.g. to develop against a local PrintMCP checkout:

        export PRINTPAL_PRINTMCP_COMMAND="uv run --directory /path/to/PrintMCP printmcp"

    or, from a venv that has printmcp installed:

        export PRINTPAL_PRINTMCP_COMMAND="python -m printmcp"

    The value is split with shlex (so quoted args work). Returns the params
    plus a short human-readable label of the source for the banner.
    """
    import shlex

    override = os.environ.get("PRINTPAL_PRINTMCP_COMMAND", "").strip()
    if override:
        parts = shlex.split(override)
        if not parts:
            override = ""  # treat whitespace-only as unset
        else:
            return (
                StdioServerParameters(
                    command=parts[0],
                    args=parts[1:],
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                ),
                f"local ({override})",
            )
    return (
        StdioServerParameters(
            command="uvx",
            args=["printmcp"],
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        ),
        "pypi (uvx printmcp)",
    )


def _sanitize_session_name(prompt: str) -> str:
    """Convert a user prompt to a valid session name."""
    name = prompt.lower().strip()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    if len(name) > 40:
        name = name[:40].rstrip("-")
    return name or "session"


def _unique_session_name(base: str) -> str:
    """Ensure the session name is unique in the DB."""
    if not db.get_session_by_name(base):
        return base
    i = 2
    while db.get_session_by_name(f"{base}-{i}"):
        i += 1
    return f"{base}-{i}"


def _mode_rprompt_text(perm_state: PermissionState) -> str:
    if perm_state.mode == ApprovalMode.AUTO:
        return "[auto]"
    elif perm_state.mode == ApprovalMode.BYPASS:
        return "[bypass] !"
    return "[manual]"


def _get_token_usage(agent) -> tuple[int, int]:
    """Get (total_tokens, context_window) from the agent's monitor."""
    try:
        usage = agent.monitor.get_total_token_counts()
        total = usage.input_tokens + usage.output_tokens
    except Exception:
        total = 0
    # Claude Sonnet 4.6 context window is 200k
    context_window = 200_000
    return total, context_window


def _get_session_cost(agent, model_id: str) -> float:
    """Get the running cost estimate from the agent's monitor."""
    try:
        from .pricing import MODEL_PRICING

        usage = agent.monitor.get_total_token_counts()
        pricing = MODEL_PRICING.get(model_id, {"input": 0, "output": 0})
        input_cost = (usage.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (usage.output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost
    except Exception:
        return 0.0


def _print_banner(tool_count: int = 0, printmcp_source: str = "", slicer: str = "") -> None:
    tip = random.choice(TIPS)
    if tool_count > 0:
        mcp_status = Text(f"PrintMCP: connected ({tool_count} tools)", style="green")
        if printmcp_source:
            mcp_status.append(f"  [{printmcp_source}]", style="dim")
        if slicer:
            mcp_status.append(f"\nslicer: {slicer}", style="dim")
        mcp_status.append("\n")
    else:
        mcp_status = Text("PrintMCP: not connected\n", style="bold red")

    logo_text = Text(LOGO, style=f"bold {ACCENT}")

    console.print(
        Panel(
            logo_text
            + mcp_status
            + Text(f"model: {MODEL_ID}\n", style="dim")
            + Text(f"★ {tip}", style=f"italic {ACCENT}"),
            border_style=ACCENT,
        )
    )


def _detect_slicer_label(tool_names: set[str]) -> str:
    """Human label for which slicer backend(s) the connected PrintMCP exposed."""
    has_orca = "orca_slice_model" in tool_names
    has_cura = "cura_slice_model" in tool_names
    if has_orca and has_cura:
        return "OrcaSlicer + Cura"
    if has_orca:
        return "OrcaSlicer"
    if has_cura:
        return "Cura"
    return ""


def _print_status_line(
    tool_count: int = 0,
    perm_state: PermissionState | None = None,
    agent=None,
    session_name: str | None = None,
) -> None:
    """Print a width-aware visual status bar before the prompt.

    Segments are conditionally shown based on terminal width so the status
    bar always fits on one line. Priority order (highest first):
    model > mode > token count > cost > session > things > token bar > tools
    """
    width = console.size.width if console.size.width > 0 else 80

    things = db.list_things()
    thing_count = len(things)
    models = sum(1 for t in things if t["file_type"] == "model")
    gcodes = sum(1 for t in things if t["file_type"] == "gcode")

    queue = db.get_queue()
    queue_count = len(queue)

    # Gather all possible segments with their approximate widths
    seg_model = Text(f"\U0001f5a8 {MODEL_ID}", style=f"bold {ACCENT}")

    seg_mode = None
    if perm_state:
        if perm_state.mode == ApprovalMode.AUTO:
            seg_mode = Text("  auto", style="green")
        elif perm_state.mode == ApprovalMode.BYPASS:
            seg_mode = Text("  bypass", style="bold red")
        else:
            seg_mode = Text("  manual", style="dim")

    seg_tokens_compact = None
    seg_tokens_bar = None
    seg_cost = None
    if agent:
        total_tokens, ctx_window = _get_token_usage(agent)
        if total_tokens > 0:
            seg_tokens_compact = Text(f"  {format_tokens(total_tokens)}", style="dim")
            bar = make_bar(total_tokens, ctx_window, 16)
            pct = total_tokens / ctx_window if ctx_window > 0 else 0
            bar_style = "bold red" if pct > 0.95 else "yellow" if pct > 0.80 else "dim"
            seg_tokens_bar = Text(
                f"  {bar} {format_tokens(total_tokens)}/{format_tokens(ctx_window)}",
                style=bar_style,
            )
            cost = _get_session_cost(agent, MODEL_ID)
            if cost > 0:
                seg_cost = Text(f"  ${cost:.2f}", style="dim")

    seg_session = Text(f"  {session_name}", style="dim") if session_name else None

    seg_things = None
    if thing_count:
        parts = []
        if models:
            parts.append(f"{models} model{'s' if models != 1 else ''}")
        if gcodes:
            parts.append(f"{gcodes} gcode")
        seg_things = Text(f"  {', '.join(parts)}", style="dim")
    else:
        seg_things = Text("  no things", style="dim")

    seg_tools = (
        Text(f"  {tool_count} tools", style="green")
        if tool_count > 0
        else Text("  mcp: offline", style="bold red")
    )

    seg_queue = Text(f"  queue: {queue_count}", style="yellow") if queue_count else None

    # Build segments by priority, estimating cumulative width
    # Each Text segment's plain text length is our width estimate
    def _text_len(t: Text | None) -> int:
        return len(t.plain) if t else 0

    segments = [seg_model]

    # Mode — always show (priority 2)
    if seg_mode:
        segments.append(seg_mode)

    # Token bar or compact (priority 3)
    # Use bar if width allows, otherwise compact
    if seg_tokens_bar and width >= 100:
        segments.append(seg_tokens_bar)
    elif seg_tokens_compact:
        segments.append(seg_tokens_compact)

    # Cost (priority 4)
    if seg_cost and width >= 70:
        segments.append(seg_cost)

    # Session name (priority 5)
    if seg_session and width >= 80:
        segments.append(seg_session)

    # Things (priority 6)
    if seg_things and width >= 90:
        segments.append(seg_things)

    # Queue (priority 7)
    if seg_queue and width >= 100:
        segments.append(seg_queue)

    # Tools (priority 8)
    if seg_tools and width >= 100:
        segments.append(seg_tools)

    # Print the status bar with separator
    console.print(Text("").join(segments))
    console.print(Text("\u2500" * width, style="dim"))


def _read_prompt(history, perm_state: PermissionState) -> str:
    example = random.choice(EXAMPLES)
    if not _HAS_PT or not sys.stdin.isatty():
        console.print(Text("\u276f ", style=f"bold {ACCENT}"), end="")
        return input().strip()

    from prompt_toolkit import PromptSession
    from prompt_toolkit.key_binding import KeyBindings

    session = PromptSession(history=history)
    kb = KeyBindings()

    @kb.add(Keys.BackTab)
    def _cycle_mode(event):
        perm_state.cycle()
        event.app.invalidate()

    completer = CommandCompleter()

    return session.prompt(
        FormattedText([("bold #d4b702", "\u276f ")]),
        placeholder=FormattedText([("gray", example)]),
        rprompt=_mode_rprompt_text(perm_state),
        completer=completer,
        key_bindings=kb,
    ).strip()


def main():
    try:
        db.init_db()
        db.log_message("INFO", "PrintPal started")
        migrated = db.migrate_to_blob_storage()
        if migrated > 0:
            console.print(
                Text(
                    f"Migrated {migrated} file(s) to database storage.",
                    style=f"bold {ACCENT}",
                )
            )
        migrate_json_sessions()
    except Exception as e:
        console.print(Text(f"Database error: {e}", style="bold red"))
        console.print(Text("Try /self-destruct to reset, or check ~/.printpal/", style="dim"))
        return

    try:
        _inject_db_settings()
    except Exception:
        pass

    server_params, printmcp_source = _printmcp_server_params()

    try:
        with MCPClient(server_params, structured_output=True) as tools:
            model = LiteLLMModel(model_id=MODEL_ID)

            perm_state = PermissionState()
            wrapped_tools = [PermissionTool(t, perm_state) for t in tools]

            agent = CodeAgent(
                tools=wrapped_tools,
                model=model,
                executor_kwargs={"timeout_seconds": 600},
            )
            dirty = False
            history = InMemoryHistory() if _HAS_PT else None
            tool_count = len(tools)
            current_session_name = None
            slicer_label = _detect_slicer_label({t.name for t in tools})
            _print_banner(tool_count, printmcp_source, slicer_label)

            while True:
                try:
                    _print_status_line(tool_count, perm_state, agent, current_session_name)
                    user_input = _read_prompt(history, perm_state)
                except (EOFError, KeyboardInterrupt):
                    console.print()
                    break
                except Exception as e:
                    console.print(Text(f"Error: {e}", style="bold red"))
                    try:
                        db.log_message("ERROR", f"REPL: {type(e).__name__}: {e}")
                    except Exception:
                        pass
                    continue

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    try:
                        import shlex

                        parts = shlex.split(user_input)
                    except ValueError:
                        # Unbalanced quote — fall back to plain whitespace split.
                        parts = user_input.split()
                    cmd = parts[0].lower()
                    args = parts[1:]

                    try:
                        if cmd in {"/exit", "/quit", "/q"}:
                            prompt_save_if_dirty(
                                dirty,
                                agent,
                                MODEL_ID,
                                history.get_strings() if history else [],
                                perm_state.to_json(),
                            )
                            break

                        if cmd == "/help":
                            cmd_help()
                            continue

                        if cmd == "/save":
                            if cmd_save(
                                agent,
                                args,
                                MODEL_ID,
                                history.get_strings() if history else [],
                                perm_state.to_json(),
                            ):
                                dirty = False
                                current_session_name = args[0] if args else current_session_name
                            continue

                        if cmd == "/load":
                            result = cmd_load(
                                agent,
                                args,
                                dirty,
                                MODEL_ID,
                                history.get_strings() if history else [],
                                perm_state.to_json(),
                            )
                            if result["loaded"]:
                                dirty = False
                                if _HAS_PT:
                                    history = InMemoryHistory()
                                    for p in result["prompt_history"]:
                                        history.append_string(p)
                                perm_state = PermissionState.from_json(result["permissions"])
                                for wt in wrapped_tools:
                                    wt._perm = perm_state
                                resolved = _resolve_name(args[0])
                                current_session_name = resolved
                            continue

                        if cmd in {"/new", "/clear"}:
                            prompt_save_if_dirty(
                                dirty,
                                agent,
                                MODEL_ID,
                                history.get_strings() if history else [],
                                perm_state.to_json(),
                            )
                            agent.memory.reset()
                            if _HAS_PT:
                                history = InMemoryHistory()
                            perm_state.reset()
                            dirty = False
                            current_session_name = None
                            console.print(Text("Session cleared.", style="dim"))
                            continue

                        if cmd == "/sessions":
                            cmd_sessions()
                            continue

                        if cmd == "/mode":
                            cmd_mode(args, perm_state)
                            continue

                        if cmd == "/config":
                            cmd_config(args)
                            continue

                        if cmd == "/cost":
                            cmd_cost(agent, MODEL_ID)
                            continue

                        if cmd == "/logs":
                            cmd_logs(args)
                            continue

                        if cmd == "/backup":
                            cmd_backup(args)
                            continue

                        if cmd == "/redraw":
                            console.clear()
                            _print_banner(tool_count, printmcp_source, slicer_label)
                            continue

                        if cmd == "/self-destruct":
                            if cmd_self_destruct():
                                break
                            continue

                        if cmd == "/thing":
                            cmd_thing_dispatch(args)
                            continue

                        if cmd == "/slice":
                            cmd_slice(args, tools)
                            continue

                        if cmd == "/printer":
                            cmd_printer(args)
                            continue

                        if cmd == "/print":
                            if not args:
                                cmd_print(args, tools)
                            elif args[0].lower() == "status":
                                cmd_print_status(tools)
                            elif args[0].lower() == "pause":
                                cmd_print_pause(tools)
                            elif args[0].lower() == "resume":
                                cmd_print_resume(tools)
                            elif args[0].lower() == "cancel":
                                cmd_print_cancel(tools)
                            elif args[0].lower() == "connect":
                                cmd_print_connect(tools)
                            elif args[0].lower() == "disconnect":
                                cmd_print_disconnect(tools)
                            elif args[0].lower() == "files":
                                cmd_print_files(tools)
                            elif args[0].lower() == "queue":
                                cmd_print_queue(args[1:])
                            else:
                                cmd_print(args, tools)
                            continue

                        console.print(
                            Text(
                                f"Unknown command '{cmd}'. Available: {', '.join(COMMANDS.keys())}",
                                style="bold red",
                            )
                        )
                        continue

                    except Exception as e:
                        console.print(Text(f"Error: {e}", style="bold red"))
                        try:
                            db.log_message("ERROR", f"Command '{cmd}': {type(e).__name__}: {e}")
                        except Exception:
                            pass
                        continue

                try:
                    agent.run(user_input)
                    scan_for_downloads(agent)
                    dirty = True

                    if db.get_setting("auto_save") == "true":
                        if not current_session_name:
                            base_name = _sanitize_session_name(user_input)
                            current_session_name = _unique_session_name(base_name)
                        save_session(
                            agent,
                            current_session_name,
                            MODEL_ID,
                            history.get_strings() if history else [],
                            perm_state.to_json(),
                        )
                        dirty = False
                        console.print(
                            Text(
                                f"  Auto-saved as '{current_session_name}'.",
                                style="dim",
                            )
                        )

                except KeyboardInterrupt:
                    console.print(Text("Interrupted.", style="dim"))
                    dirty = True
                except Exception as e:
                    console.print(Text(f"Agent error: {e}", style="bold red"))
                    try:
                        db.log_message("ERROR", f"Agent run: {type(e).__name__}: {e}")
                    except Exception:
                        pass
                    dirty = True

    except TimeoutError as e:
        console.print(
            Text(
                f"MCP server didn't respond in time — is 'printmcp' installed and a valid stdio MCP server? {e}",
                style="bold red",
            )
        )
        try:
            db.log_message("ERROR", f"MCP timeout: {e}")
        except Exception:
            pass

    try:
        db.log_message("INFO", "PrintPal exited")
    except Exception:
        pass
