from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Mapping


class github_mcp_usage_reader:
    def __init__(self, state_path: str | Path, *, now=time.time) -> None:
        self._state_path = Path(state_path)
        self._now = now

    @property
    def state_path(self) -> Path:
        return self._state_path

    def snapshot(self) -> Mapping[str, Any]:
        observed_at = float(self._now())
        raw = self._read_state()
        available = bool(raw)
        method_counts = _count_mapping(raw.get("method_counts"))
        request_kind_counts = _count_mapping_preserve(raw.get("request_kind_counts"))
        metrics = {
            "requests": _number(raw.get("request_count")),
            "mutations": _number(raw.get("mutation_count")),
            "primary_rate_limit_events": _number(raw.get("primary_rate_limit_events")),
            "secondary_rate_limit_events": _number(raw.get("secondary_rate_limit_events")),
            "gate_admissions": _number(raw.get("gate_admission_count")),
            "gate_recoveries": _number(raw.get("gate_recovery_count")),
            "gate_errors": _number(raw.get("gate_error_count")),
            "gate_admission_wait_seconds": _number(raw.get("gate_admission_wait_seconds")),
            "gate_recovery_wait_seconds": _number(raw.get("gate_recovery_wait_seconds")),
        }
        for key, value in request_kind_counts.items():
            metrics[f"request_kind.{key}"] = float(value)
        state = {
            "backoff_level": _count(raw.get("backoff_level")),
            "cooldown_remaining_seconds": _remaining_seconds(
                raw.get("cooldown_until_unix"), observed_at
            ),
            "last_rate_limit_kind": str(raw.get("last_rate_limit_kind") or ""),
            "last_rate_limit_age_seconds": _age_seconds(
                raw.get("last_rate_limit_at_unix"), observed_at
            ),
            "last_request_age_seconds": _age_seconds(
                raw.get("last_request_at_unix"), observed_at
            ),
            "last_mutation_age_seconds": _age_seconds(
                raw.get("last_mutation_at_unix"), observed_at
            ),
        }
        return {
            "schema_version": "0.2",
            "observed_at": observed_at,
            "available": available,
            "source": {
                "kind": "github_mcp_governor_state",
                "path": str(self._state_path),
                "state_schema_version": str(raw.get("schema_version") or ""),
                "governor_version": str(raw.get("governor_version") or ""),
            },
            "metrics": metrics,
            "method_counts": method_counts,
            "request_kind_counts": request_kind_counts,
            "state": state,
        }

    def _read_state(self) -> Mapping[str, Any]:
        if not self._state_path.is_file():
            return {}
        try:
            value = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, Mapping) else {}


def github_mcp_usage_delta(
    start: Mapping[str, Any],
    end: Mapping[str, Any],
) -> dict[str, Any]:
    start_metrics = _mapping(start.get("metrics"))
    end_metrics = _mapping(end.get("metrics"))
    metric_keys = sorted(set(start_metrics) | set(end_metrics))
    metrics = {
        key: max(0.0, _number(end_metrics.get(key)) - _number(start_metrics.get(key)))
        for key in metric_keys
    }

    start_methods = _mapping(start.get("method_counts"))
    end_methods = _mapping(end.get("method_counts"))
    method_keys = sorted(set(start_methods) | set(end_methods))
    method_counts = {
        key: max(0, _count(end_methods.get(key)) - _count(start_methods.get(key)))
        for key in method_keys
    }

    start_kinds = _mapping(start.get("request_kind_counts"))
    end_kinds = _mapping(end.get("request_kind_counts"))
    kind_keys = sorted(set(start_kinds) | set(end_kinds))
    request_kind_counts = {
        key: max(0, _count(end_kinds.get(key)) - _count(start_kinds.get(key)))
        for key in kind_keys
    }

    return {
        "schema_version": "0.2",
        "start_observed_at": _number(start.get("observed_at")),
        "end_observed_at": _number(end.get("observed_at")),
        "available": bool(start.get("available") or end.get("available")),
        "metrics": metrics,
        "method_counts": method_counts,
        "request_kind_counts": request_kind_counts,
        "end_state": dict(_mapping(end.get("state"))),
        "source": dict(_mapping(end.get("source"))),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _count_mapping(value: Any) -> dict[str, int]:
    return {
        str(key).upper(): _count(raw)
        for key, raw in _mapping(value).items()
        if str(key).strip()
    }


def _count_mapping_preserve(value: Any) -> dict[str, int]:
    return {
        str(key): _count(raw)
        for key, raw in _mapping(value).items()
        if str(key).strip()
    }


def _count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return 0


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    return float(value) if isinstance(value, (int, float)) else 0.0


def _remaining_seconds(value: Any, observed_at: float) -> float:
    until = _number(value)
    return max(0.0, until - observed_at) if until > 0 else 0.0


def _age_seconds(value: Any, observed_at: float) -> float | None:
    timestamp = _number(value)
    if timestamp <= 0:
        return None
    return max(0.0, observed_at - timestamp)
