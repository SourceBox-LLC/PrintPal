"""Shared helpers for command implementations.

Includes tool lookup, direct tool calling, the slice flag parser, G-code
temperature parsing, and the preheat progress display.
"""

from __future__ import annotations

import json
import re
import time

from rich.console import Group
from rich.live import Live
from rich.text import Text

from ..ui import console, ACCENT, prompt_yes_no, format_duration
from ..sessions import next_default_name, save_session


# ---------------------------------------------------------------------------
# Tool helpers
# ---------------------------------------------------------------------------


def find_tool(tools: list, name: str):
    """Find an MCP tool by name in the tools list."""
    for tool in tools:
        if tool.name == name:
            return tool
    return None


def call_tool(tools: list, name: str, **kwargs) -> dict | None:
    """Call an MCP tool directly by name. Returns parsed dict or None."""
    tool = find_tool(tools, name)
    if tool is None:
        return None
    try:
        result = tool.forward(**kwargs)
    except Exception:
        return None
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None
    return None


# ---------------------------------------------------------------------------
# Session save helper
# ---------------------------------------------------------------------------


def prompt_save_if_dirty(
    dirty: bool,
    agent,
    model_id: str,
    prompt_history: list[str] | None = None,
    permissions: str = "{}",
) -> bool:
    if not dirty:
        return True
    if prompt_yes_no("Unsaved changes. Save first? [y/N] "):
        name = next_default_name()
        save_session(agent, name, model_id, prompt_history, permissions)
        console.print(Text(f"Saved as '{name}'.", style=f"bold {ACCENT}"))
        return True
    return False


# ---------------------------------------------------------------------------
# Slice flag parser
# ---------------------------------------------------------------------------

SLICE_FLAGS = {
    "--layer-height": ("--lh", "layer_height", float, 0.2, (0.05, 0.6)),
    "--infill": ("--inf", "infill_density", int, 20, (0, 100)),
    "--supports": ("--sup", "supports", bool, False, None),
    "--adhesion": ("--ad", "adhesion_type", str, "skirt", None),
    "--temp": ("--t", "material_print_temperature", int, 200, (150, 300)),
    "--bed": ("--b", "material_bed_temperature", int, 60, (0, 120)),
    "--printer": ("--p", "printer", str, "creality_ender3pro", None),
    "--slicer": ("--sl", "_slicer", str, None, None),
}


def parse_slice_flags(args: list[str]) -> dict:
    """Parse slice flags from args. Returns dict of tool kwargs."""
    result = {}
    i = 0
    while i < len(args):
        arg = args[i].lower()
        matched = False
        for long_flag, (short_flag, key, typ, default, bounds) in SLICE_FLAGS.items():
            if arg != long_flag and arg != short_flag:
                continue
            matched = True
            if typ is bool:
                result[key] = True
            else:
                if i + 1 >= len(args):
                    raise ValueError(f"Missing value for {arg}")
                i += 1
                val = args[i]
                try:
                    parsed = (
                        int(val) if typ is int else float(val) if typ is float else val
                    )
                except ValueError:
                    raise ValueError(f"Invalid value for {arg}: {val}")
                if bounds:
                    lo, hi = bounds
                    if parsed < lo or parsed > hi:
                        raise ValueError(f"{arg} must be {lo}-{hi}, got {parsed}")
                result[key] = parsed
            break
        if not matched:
            raise ValueError(f"Unknown flag: {arg}")
        i += 1
    return result


# ---------------------------------------------------------------------------
# G-code temperature parsing + preheat
# ---------------------------------------------------------------------------


def parse_gcode_temps(file_data: bytes) -> tuple[int, int]:
    """Parse M190 (bed) and M109 (tool) target temps from G-code."""
    tool_temp = 200
    bed_temp = 60
    try:
        text = file_data.decode("utf-8", errors="replace")
        for line in text.splitlines()[:200]:
            line = line.strip()
            m190 = re.match(r"M190\s+S(\d+)", line)
            if m190:
                bed_temp = int(m190.group(1))
            m109 = re.match(r"M109\s+S(\d+)", line)
            if m109:
                tool_temp = int(m109.group(1))
            if m190 and m109:
                break
    except Exception:
        pass
    return tool_temp, bed_temp


def preheat(tools: list, tool_temp: int, bed_temp: int) -> bool:
    """Preheat bed and tool, showing live progress. Returns True on success."""
    status_tool = find_tool(tools, "octoprint_get_status")
    temp_tool = find_tool(tools, "octoprint_set_temperature")
    if not status_tool or not temp_tool:
        console.print(Text("OctoPrint tools not available.", style="bold red"))
        return False

    console.print(
        Text(
            f"Preheating bed to {bed_temp}°C, tool to {tool_temp}°C...",
            style=f"bold {ACCENT}",
        )
    )

    call_tool(
        tools,
        "octoprint_set_temperature",
        heater="bed",
        target=bed_temp,
        confirm=True,
        response_format="json",
    )
    call_tool(
        tools,
        "octoprint_set_temperature",
        heater="tool",
        target=tool_temp,
        confirm=True,
        response_format="json",
    )

    max_wait = 600
    poll_interval = 3
    elapsed = 0

    try:
        with Live(console=console, refresh_per_second=1) as live:
            while elapsed < max_wait:
                status = call_tool(
                    tools, "octoprint_get_status", response_format="json"
                )
                if not status:
                    live.update(
                        Text("Could not read printer status.", style="bold red")
                    )
                    break

                temps = status.get("temperatures", {})
                bed = temps.get("bed", {})
                tool = temps.get("tool0", {})
                bed_actual = bed.get("actual", 0) or 0
                tool_actual = tool.get("actual", 0) or 0

                bed_ok = abs(bed_actual - bed_temp) <= 2
                tool_ok = abs(tool_actual - tool_temp) <= 2

                bed_pct = min(
                    100, int((bed_actual / bed_temp * 100) if bed_temp else 100)
                )
                tool_pct = min(
                    100, int((tool_actual / tool_temp * 100) if tool_temp else 100)
                )

                bed_bar = "█" * (bed_pct // 10) + "░" * (10 - bed_pct // 10)
                tool_bar = "█" * (tool_pct // 10) + "░" * (10 - tool_pct // 10)

                lines = [
                    Text(
                        f"  Bed:  {bed_actual:.0f}°C → {bed_temp}°C  {bed_bar}  {'✓' if bed_ok else '…'}"
                    ),
                    Text(
                        f"  Tool: {tool_actual:.0f}°C → {tool_temp}°C  {tool_bar}  {'✓' if tool_ok else '…'}"
                    ),
                ]
                if bed_ok and tool_ok:
                    lines.append(Text("  Temperatures reached.", style="green"))
                    live.update(Group(*lines))
                    return True
                if elapsed > 0:
                    lines.append(
                        Text(f"  Elapsed: {format_duration(elapsed)}", style="dim")
                    )
                live.update(Group(*lines))

                time.sleep(poll_interval)
                elapsed += poll_interval

        console.print(
            Text("  Preheat timeout (10 min). Proceeding anyway.", style="yellow")
        )
        return True
    except KeyboardInterrupt:
        console.print(
            Text("\n  Preheat interrupted. Proceeding anyway.", style="yellow")
        )
        return True
