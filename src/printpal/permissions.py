"""Permission system for PrintPal.

Wraps MCP tools with an approval layer so the user can control what the agent
is allowed to do. Three modes control how aggressively approvals are needed:

- default (manual): ask for every tool call
- auto: auto-approve read-only and safe actions, ask for physical actuation
- bypass: auto-approve everything (with warning)

Per-session allow-lists let the user grant "always allow" for specific tools.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from rich.panel import Panel
from rich.text import Text

import smolagents
from .ui import console, ACCENT


# ---------------------------------------------------------------------------
# Tool categories
# ---------------------------------------------------------------------------

READ_ONLY = {
    "thingiverse_search_models",
    "thingiverse_get_model",
    "octoprint_get_status",
    "octoprint_list_files",
    "octoprint_get_job",
}

SAFE_ACTIONS = {
    "thingiverse_download_model",
    "cura_slice_model",
    "octoprint_upload_file",
}

PHYSICAL = {
    "octoprint_connect",
    "octoprint_start_print",
    "octoprint_control_job",
    "octoprint_set_temperature",
    "octoprint_home",
    "octoprint_move",
}

ALL_TOOLS = READ_ONLY | SAFE_ACTIONS | PHYSICAL


def _tool_category(name: str) -> str:
    if name in READ_ONLY:
        return "Read-only"
    if name in SAFE_ACTIONS:
        return "Safe action"
    if name in PHYSICAL:
        return "Physical actuation"
    return "Unknown"


# ---------------------------------------------------------------------------
# Approval mode
# ---------------------------------------------------------------------------


class ApprovalMode(str, Enum):
    DEFAULT = "default"
    AUTO = "auto"
    BYPASS = "bypass"

    @property
    def label(self) -> str:
        return {
            ApprovalMode.DEFAULT: "Manual",
            ApprovalMode.AUTO: "Auto",
            ApprovalMode.BYPASS: "Bypass",
        }.get(self, "Manual")


# ---------------------------------------------------------------------------
# Permission state (per-session, serializable)
# ---------------------------------------------------------------------------


class PermissionState:
    """Tracks the current permission mode and per-session allow-list."""

    def __init__(self, mode: ApprovalMode = ApprovalMode.DEFAULT):
        self.mode = mode
        self.allow_list: set[str] = set()

    def should_ask(self, tool_name: str) -> bool:
        """Return True if the user should be prompted before this tool runs."""
        if tool_name in self.allow_list:
            return False
        if self.mode == ApprovalMode.BYPASS:
            return False
        if self.mode == ApprovalMode.AUTO:
            if tool_name in READ_ONLY or tool_name in SAFE_ACTIONS:
                return False
            return True
        # DEFAULT: ask for everything not in allow-list
        return True

    def allow(self, tool_name: str) -> None:
        """Add a tool to the session allow-list."""
        self.allow_list.add(tool_name)

    def reset(self) -> None:
        """Reset to default mode with empty allow-list."""
        self.mode = ApprovalMode.DEFAULT
        self.allow_list.clear()

    def cycle(self) -> ApprovalMode:
        """Cycle between default and auto (for Shift+Tab)."""
        if self.mode == ApprovalMode.DEFAULT:
            self.mode = ApprovalMode.AUTO
        else:
            self.mode = ApprovalMode.DEFAULT
        return self.mode

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "allow_list": sorted(self.allow_list),
        }

    @classmethod
    def from_dict(cls, data: dict) -> PermissionState:
        mode_str = data.get("mode", "default")
        try:
            mode = ApprovalMode(mode_str)
        except ValueError:
            mode = ApprovalMode.DEFAULT
        state = cls(mode=mode)
        state.allow_list = set(data.get("allow_list", []))
        return state

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> PermissionState:
        try:
            return cls.from_dict(json.loads(json_str))
        except (json.JSONDecodeError, TypeError):
            return cls()


# ---------------------------------------------------------------------------
# Approval prompt
# ---------------------------------------------------------------------------


def _prompt_approval(tool_name: str, args: dict | None = None) -> str:
    """Show approval prompt. Returns 'y', 'n', or 'a'.

    The prompt is printed after flushing the console buffer to avoid
    collisions with smolagents' Rich panel output that may be in-flight.
    """
    import sys as _sys

    category = _tool_category(tool_name)

    _sys.stdout.flush()
    _sys.stderr.flush()

    lines = [
        Text(f"Tool:     {tool_name}", style=f"bold {ACCENT}"),
        Text(f"Category: {category}"),
    ]
    if args:
        arg_str = ", ".join(
            f"{k}={v}" for k, v in args.items() if k != "response_format"
        )
        if arg_str:
            lines.append(Text(f"Args:     {arg_str[:120]}"))

    console.print(
        Panel(
            Text("\n").join(lines),
            title=Text("\u26a0  Permission Required", style="bold"),
            border_style=ACCENT,
        )
    )

    console.print(Text("  [y] Yes   [n] No   [a] Always allow this tool", style="dim"))
    console.print(Text("\u276f ", style=f"bold {ACCENT}"), end="")
    _sys.stdout.flush()
    try:
        response = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "n"
    console.print()
    return response if response in {"y", "n", "a"} else "n"


# ---------------------------------------------------------------------------
# PermissionTool wrapper
# ---------------------------------------------------------------------------


class PermissionTool(smolagents.Tool):
    """Wraps an MCP tool with permission checking.

    Subclasses smolagents.Tool so it passes the isinstance(tool, BaseTool)
    check in CodeAgent.__init__.
    """

    def __init__(self, inner_tool: Any, perm_state: PermissionState):
        self._inner = inner_tool
        self._perm = perm_state

        # Copy all attributes smolagents' CodeAgent reads
        self.name = inner_tool.name
        self.description = inner_tool.description
        self.inputs = inner_tool.inputs
        self.output_type = inner_tool.output_type
        self.is_initialized = True
        self.skip_forward_signature_validation = True
        if hasattr(inner_tool, "output_schema"):
            self.output_schema = inner_tool.output_schema
        if hasattr(inner_tool, "structured_output"):
            self.structured_output = inner_tool.structured_output

    def forward(self, *args, **kwargs) -> Any:
        """Check permission then delegate to inner tool."""
        if self._perm.should_ask(self.name):
            display_args = None
            if args and len(args) == 1 and isinstance(args[0], dict):
                display_args = args[0]
            elif kwargs:
                display_args = {
                    k: v for k, v in kwargs.items() if k != "response_format"
                }

            response = _prompt_approval(self.name, display_args)

            if response == "n":
                raise PermissionError(f"Permission denied: {self.name}")
            elif response == "a":
                self._perm.allow(self.name)

        return self._inner.forward(*args, **kwargs)
