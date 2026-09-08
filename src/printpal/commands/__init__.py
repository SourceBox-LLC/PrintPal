"""Command package for PrintPal.

Re-exports all command functions and the COMMANDS dict so that ``app.py``
can import everything from a single package.
"""

from __future__ import annotations

COMMANDS = {
    "/save": "Save the current session. Usage: /save [name]",
    "/load": "Load a saved session. Usage: /load <name|id>",
    "/sessions": "List all saved sessions.",
    "/thing": "Manage downloaded models. Usage: /thing [id|export <id> [dest]|delete <id>]",
    "/slice": "Slice a model to G-code (Cura or OrcaSlicer). Usage: /slice <id> [flags] [--slicer cura|orca]",
    "/printer": "Manage printer presets. Usage: /printer [list|show <name>|use <name>|add <name>|remove <name>]",
    "/print": "Full print pipeline: preheat, upload, start. Usage: /print <id> [--no-preheat]",
    "/print status": "Live printer status, temps, and job progress. Ctrl+C to stop.",
    "/print pause": "Pause the active print job.",
    "/print resume": "Resume the paused print job.",
    "/print cancel": "Cancel the active print job (wasted material).",
    "/print connect": "Connect to the printer.",
    "/print disconnect": "Disconnect from the printer.",
    "/print files": "List G-code files on the OctoPrint server.",
    "/print queue": "Show the print queue. Usage: /print queue [remove <pos>|clear]",
    "/mode": "Show or set permission mode. Usage: /mode [default|auto|bypass]",
    "/config": "Show or set app settings. Usage: /config [set <key> <val>|get <key>|unset <key>]",
    "/cost": "Show token usage and estimated cost for this session.",
    "/logs": "Show recent logs. Usage: /logs [<limit>|error|clear]",
    "/backup": "Create or manage DB backups. Usage: /backup [list|restore <name>]",
    "/redraw": "Clear and redraw the UI (use after terminal resize).",
    "/self-destruct": "Delete ALL data — database, backups, everything. Irreversible.",
    "/new": "Clear the current session and start fresh. (alias: /clear)",
    "/clear": "Alias for /new.",
    "/exit": "Exit PrintPal. (aliases: /quit, /q)",
    "/quit": "Alias for /exit.",
    "/q": "Alias for /exit.",
    "/help": "Show available commands.",
}

from .admin import cmd_backup, cmd_config, cmd_cost, cmd_logs, cmd_self_destruct  # noqa: E402
from .help import cmd_help  # noqa: E402
from .helpers import (  # noqa: E402
    call_tool,
    find_tool,
    parse_gcode_temps,
    parse_slice_flags,
    preheat,
    prompt_save_if_dirty,
)
from .mode import cmd_mode  # noqa: E402
from .print import (  # noqa: E402
    cmd_print,
    cmd_print_cancel,
    cmd_print_connect,
    cmd_print_disconnect,
    cmd_print_files,
    cmd_print_pause,
    cmd_print_queue,
    cmd_print_resume,
    cmd_print_status,
)
from .printer import cmd_printer  # noqa: E402
from .session import cmd_load, cmd_save, cmd_sessions  # noqa: E402
from .thing import cmd_slice, cmd_thing, cmd_thing_dispatch  # noqa: E402

__all__ = [
    "COMMANDS",
    "find_tool",
    "call_tool",
    "prompt_save_if_dirty",
    "parse_slice_flags",
    "parse_gcode_temps",
    "preheat",
    "cmd_save",
    "cmd_load",
    "cmd_sessions",
    "cmd_thing",
    "cmd_thing_dispatch",
    "cmd_slice",
    "cmd_printer",
    "cmd_print",
    "cmd_print_status",
    "cmd_print_pause",
    "cmd_print_resume",
    "cmd_print_cancel",
    "cmd_print_connect",
    "cmd_print_disconnect",
    "cmd_print_files",
    "cmd_print_queue",
    "cmd_mode",
    "cmd_config",
    "cmd_cost",
    "cmd_logs",
    "cmd_backup",
    "cmd_self_destruct",
    "cmd_help",
]
