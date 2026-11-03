from __future__ import annotations

import json
from pathlib import Path
import tempfile

from helpers import plugins
from helpers.tool import Response, Tool


_PLUGIN_NAME = "acmm_tools"
_STATE_PATH = Path(tempfile.gettempdir()) / "acmm_authoritative_state_workspace_v1.json"


class WriteRecord(Tool):
    async def execute(self, **kwargs):
        args = {**self.args, **kwargs}
        config = plugins.get_plugin_config(_PLUGIN_NAME, agent=self.agent) or {}
        state = _workspace_state(config)
        record_id = _record_id(args)
        value = _integer(args.get("value"))

        if record_id != "target":
            return Response(
                message=json.dumps(
                    {
                        "ok": False,
                        "error": "only target may be written in this controlled workspace",
                    }
                ),
                break_loop=False,
            )

        state["target_value"] = value
        _save_state(state)
        return Response(
            message=json.dumps(
                {
                    "ok": True,
                    "record_id": "target",
                    "value": value,
                    "written": True,
                    "observed_value": value,
                }
            ),
            break_loop=False,
        )


def _workspace_state(config):
    workspace_id = _workspace_id(config)
    state = _load_state()
    if state.get("workspace_id") != workspace_id:
        state = {
            "workspace_id": workspace_id,
            "source_read_count": 0,
            "target_value": _integer_config(config, "target_value"),
        }
        _save_state(state)

    _state_integer(state, "source_read_count")
    _target_value(state)
    return state


def _load_state():
    if not _STATE_PATH.exists():
        return {}
    try:
        value = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("controlled workspace state cannot be read") from exc
    if not isinstance(value, dict):
        raise RuntimeError("controlled workspace state must be an object")
    return value


def _save_state(state):
    try:
        _STATE_PATH.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("controlled workspace state cannot be written") from exc


def _workspace_id(config):
    value = config.get("workspace_id")
    if not isinstance(value, str) or not value:
        raise ValueError("workspace_id must be a non-empty string")
    return value


def _record_id(args):
    value = args.get("record_id")
    if not isinstance(value, str) or not value:
        raise ValueError("record_id must be a non-empty string")
    return value


def _integer(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("value must be an integer")
    return value


def _integer_config(config, name):
    value = config.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _state_integer(state, name):
    value = state.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"controlled state field {name!r} is invalid")
    return value


def _target_value(state):
    return _state_integer(state, "target_value")
