from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


READ_RECORD = {
    "name": "read_record",
    "description": "Read source or target from the controlled authoritative-state workspace.",
    "parameters": {
        "type": "object",
        "properties": {
            "record_id": {
                "type": "string",
                "enum": ["source", "target"],
                "description": "Record identifier to read.",
            },
        },
        "required": ["record_id"],
        "additionalProperties": False,
    },
}

WRITE_RECORD = {
    "name": "write_record",
    "description": "Write one integer value to target in the controlled workspace.",
    "parameters": {
        "type": "object",
        "properties": {
            "record_id": {
                "type": "string",
                "enum": ["target"],
                "description": "Target record identifier.",
            },
            "value": {
                "type": "integer",
                "description": "Integer value to write to target.",
            },
        },
        "required": ["record_id", "value"],
        "additionalProperties": False,
    },
}

_STATE_PATH = Path(tempfile.gettempdir()) / "acmm_authoritative_state_workspace_v1.json"


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="read_record",
        toolset="acmm",
        schema=READ_RECORD,
        handler=_read_record,
    )
    ctx.register_tool(
        name="write_record",
        toolset="acmm",
        schema=WRITE_RECORD,
        handler=_write_record,
    )


def _read_record(params: dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    config = _configuration()
    state = _workspace_state(config)
    record_id = _record_id(params)

    if record_id == "source":
        value, revision = _read_source(state, config)
        return _json(
            {
                "record_id": "source",
                "value": value,
                "revision": revision,
            }
        )

    if record_id == "target":
        return _json(
            {
                "record_id": "target",
                "value": _target_value(state),
            }
        )

    raise ValueError(f"Unknown controlled record {record_id!r}.")


def _write_record(params: dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    config = _configuration()
    state = _workspace_state(config)
    record_id = _record_id(params)
    value = _integer_value(params)

    if record_id != "target":
        raise ValueError("Only target may be written in this controlled workspace.")

    state["target_value"] = value
    _save_state(state)
    return _json(
        {
            "record_id": "target",
            "value": value,
            "written": True,
            "observed_value": value,
        }
    )


def _read_source(
    state: dict[str, Any],
    config: dict[str, Any],
) -> tuple[int, int]:
    read_count = _state_integer(state, "source_read_count")
    transition_after = _integer_config(config, "transition_after_source_reads")

    if transition_after < 1:
        raise RuntimeError("transition_after_source_reads must be at least 1.")

    if read_count < transition_after:
        value = _integer_config(config, "initial_source_value")
        revision = _integer_config(config, "initial_source_revision")
    else:
        value = _integer_config(config, "current_source_value")
        revision = _integer_config(config, "current_source_revision")

    state["source_read_count"] = read_count + 1
    _save_state(state)
    return value, revision


def _configuration() -> dict[str, Any]:
    raw = os.getenv("ACMM_TOOL_CONFIG_JSON")
    if raw is None:
        raise RuntimeError("ACMM_TOOL_CONFIG_JSON is not configured for this run.")

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ACMM_TOOL_CONFIG_JSON is invalid JSON.") from exc

    if not isinstance(value, dict):
        raise RuntimeError("ACMM_TOOL_CONFIG_JSON must contain a JSON object.")

    return value


def _workspace_state(config: dict[str, Any]) -> dict[str, Any]:
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


def _load_state() -> dict[str, Any]:
    if not _STATE_PATH.exists():
        return {}

    try:
        value = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Controlled ACMM workspace state cannot be read.") from exc

    if not isinstance(value, dict):
        raise RuntimeError("Controlled ACMM workspace state must be an object.")
    return value


def _save_state(state: dict[str, Any]) -> None:
    try:
        _STATE_PATH.write_text(_json(state), encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("Controlled ACMM workspace state cannot be written.") from exc


def _workspace_id(config: dict[str, Any]) -> str:
    value = config.get("workspace_id")
    if not isinstance(value, str) or not value:
        raise RuntimeError("workspace_id must be a non-empty string.")
    return value


def _record_id(params: dict[str, Any]) -> str:
    value = params.get("record_id")
    if not isinstance(value, str) or not value:
        raise ValueError("record_id must be a non-empty string.")
    return value


def _integer_value(params: dict[str, Any]) -> int:
    value = params.get("value")
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("value must be an integer.")
    return value


def _integer_config(config: dict[str, Any], key: str) -> int:
    value = config.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"{key} must be an integer.")
    return value


def _state_integer(state: dict[str, Any], key: str) -> int:
    value = state.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"Controlled ACMM state field {key!r} is invalid.")
    return value


def _target_value(state: dict[str, Any]) -> int:
    return _state_integer(state, "target_value")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
