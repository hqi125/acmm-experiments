"""
title: ACMM Controlled Authoritative State Tools
author: ACMM
version: 0.1.0
requirements:
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from pydantic import BaseModel, Field


_STATE_PATH = Path(tempfile.gettempdir()) / "acmm_authoritative_state_workspace_v1.json"


class Tools:
    class Valves(BaseModel):
        workspace_id: str = Field(default="baseline")
        initial_source_value: int = Field(default=0)
        current_source_value: int = Field(default=0)
        target_value: int = Field(default=0)
        initial_source_revision: int = Field(default=1)
        current_source_revision: int = Field(default=2)
        transition_after_source_reads: int = Field(default=1)

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def read_record(self, record_id: str) -> str:
        """Read source or target from the controlled authoritative-state workspace."""
        _validate_configuration(self.valves)
        state = _workspace_state(self.valves)

        if record_id == "source":
            value, revision = _read_source(state, self.valves)
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

    async def write_record(self, record_id: str, value: int) -> str:
        """Write one integer value to target in the controlled workspace."""
        _validate_configuration(self.valves)
        state = _workspace_state(self.valves)
        _require_integer(value)

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


def _validate_configuration(valves: Tools.Valves) -> None:
    if not isinstance(valves.workspace_id, str) or not valves.workspace_id:
        raise RuntimeError("workspace_id must be a non-empty string.")
    if valves.transition_after_source_reads < 1:
        raise RuntimeError("transition_after_source_reads must be at least 1.")
    if valves.current_source_revision <= valves.initial_source_revision:
        raise RuntimeError(
            "current_source_revision must be greater than initial_source_revision."
        )


def _workspace_state(valves: Tools.Valves) -> dict:
    state = _load_state()
    if state.get("workspace_id") != valves.workspace_id:
        state = {
            "workspace_id": valves.workspace_id,
            "source_read_count": 0,
            "target_value": valves.target_value,
        }
        _save_state(state)

    _state_integer(state, "source_read_count")
    _target_value(state)
    return state


def _read_source(
    state: dict,
    valves: Tools.Valves,
) -> tuple[int, int]:
    read_count = _state_integer(state, "source_read_count")

    if read_count < valves.transition_after_source_reads:
        value = valves.initial_source_value
        revision = valves.initial_source_revision
    else:
        value = valves.current_source_value
        revision = valves.current_source_revision

    state["source_read_count"] = read_count + 1
    _save_state(state)
    return value, revision


def _load_state() -> dict:
    if not _STATE_PATH.exists():
        return {}

    try:
        value = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Controlled ACMM workspace state cannot be read.") from exc

    if not isinstance(value, dict):
        raise RuntimeError("Controlled ACMM workspace state must be an object.")
    return value


def _save_state(state: dict) -> None:
    try:
        _STATE_PATH.write_text(_json(state), encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("Controlled ACMM workspace state cannot be written.") from exc


def _state_integer(state: dict, key: str) -> int:
    value = state.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"Controlled ACMM state field {key!r} is invalid.")
    return value


def _target_value(state: dict) -> int:
    return _state_integer(state, "target_value")


def _require_integer(value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("value must be an integer.")


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
