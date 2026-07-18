"""Download and slice scanner for PrintPal.

After each ``agent.run()``, this scanner walks the agent's memory steps to
detect ``thingiverse_download_model`` and ``cura_slice_model`` calls. It
parses the tool results from the step observations, reads the files from
disk into BLOBs, stores them in the ``things`` table, and deletes the disk
files (self-contained storage).
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

from . import db


def scan_for_downloads(agent) -> None:
    """Walk agent memory for download and slice tool calls, insert into the things table."""
    for step in agent.memory.steps:
        if not hasattr(step, "code_action") or not step.code_action:
            continue
        if step.is_final_answer:
            continue

        step_key = f"{id(agent)}:{step.step_number}"
        if db.is_step_scanned(step_key):
            continue

        if "thingiverse_download_model" in step.code_action:
            _insert_download_from_step(step)
            db.mark_step_scanned(step_key)
        elif "cura_slice_model" in step.code_action:
            _insert_slice_from_step(step)
            db.mark_step_scanned(step_key)


def _insert_download_from_step(step) -> None:
    """Parse a download step's output and insert thing rows with BLOB data."""
    observations = step.observations or ""
    data = None

    output = step.action_output
    if isinstance(output, dict):
        data = output
    elif isinstance(output, str):
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            pass

    if not data and "'files'" in observations:
        start = observations.find("{")
        if start >= 0:
            depth = 0
            end = start
            for i, ch in enumerate(observations[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            raw = observations[start:end]
            try:
                data = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                pass

    if not data:
        file_matches = re.findall(r"- (.+?) \((\d+) bytes\) -> (.+)", observations)
        if not file_matches:
            return
        thing_match = re.search(r"Thing\s*ID:\s*(\d+)", observations, re.IGNORECASE)
        name_match = re.search(r"Name:\s*(.+?)(?:\n|$)", observations)
        license_match = re.search(r"License:\s*(.+?)(?:\n|$)", observations)
        data = {
            "thing_id": int(thing_match.group(1)) if thing_match else None,
            "name": name_match.group(1).strip() if name_match else "Unknown",
            "license": license_match.group(1).strip() if license_match else None,
            "files": [
                {"name": m[0], "size_bytes": int(m[1]), "path": m[2]}
                for m in file_matches
            ],
        }

    if not data or not data.get("files"):
        return

    thingiverse_id = data.get("thing_id")
    name = data.get("name") or "Unknown"
    license = data.get("license")
    dest_dir = data.get("dest_dir", "")

    for f in data["files"]:
        file_path = f.get("path") or os.path.join(dest_dir, f.get("name", ""))
        if not file_path:
            continue
        file_name = f.get("name") or os.path.basename(file_path)
        file_size = f.get("size_bytes")
        file_data = None
        try:
            file_data = Path(file_path).read_bytes()
            if file_size is None:
                file_size = len(file_data)
            Path(file_path).unlink()
        except OSError:
            pass
        db.insert_thing(
            thingiverse_id=thingiverse_id,
            name=name,
            creator=None,
            license=license,
            url=None,
            file_name=file_name,
            file_size=file_size,
            file_data=file_data,
            file_type="model",
            status="downloaded",
        )


def _insert_slice_from_step(step) -> None:
    """Parse a cura_slice_model step's output and insert G-code as a thing row."""
    observations = step.observations or ""
    data = None

    output = step.action_output
    if isinstance(output, dict):
        data = output
    elif isinstance(output, str):
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            pass

    if not data:
        if "gcode_path" in observations or "'gcode_path'" in observations:
            start = observations.find("{")
            if start >= 0:
                depth = 0
                end = start
                for i, ch in enumerate(observations[start:], start):
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                raw = observations[start:end]
                try:
                    data = ast.literal_eval(raw)
                except (ValueError, SyntaxError):
                    pass

    if not data or not data.get("gcode_path"):
        return

    gcode_path = data.get("gcode_path", "")
    if not gcode_path:
        return

    gcode_name = os.path.basename(gcode_path)
    gcode_size = data.get("gcode_size_bytes")

    file_data = None
    try:
        file_data = Path(gcode_path).read_bytes()
        if gcode_size is None:
            gcode_size = len(file_data)
        Path(gcode_path).unlink()
    except OSError:
        pass

    model_name = data.get("model", "")
    sliced_from = None
    things = db.list_things()
    for t in things:
        if t["file_type"] == "model" and t["file_name"] == model_name:
            sliced_from = t["id"]
            break

    source_thing = db.get_thing(sliced_from) if sliced_from else None
    thingiverse_id = source_thing["thingiverse_id"] if source_thing else None
    name = source_thing["name"] if source_thing else (model_name or "Unknown")
    license = source_thing["license"] if source_thing else None
    url = source_thing["url"] if source_thing else None
    creator = source_thing["creator"] if source_thing else None

    db.insert_thing(
        thingiverse_id=thingiverse_id,
        name=name,
        creator=creator,
        license=license,
        url=url,
        file_name=gcode_name,
        file_size=gcode_size,
        file_data=file_data,
        file_type="gcode",
        sliced_from=sliced_from,
        status="sliced",
    )
