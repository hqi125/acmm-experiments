from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path

import yaml
from typing import Any, Mapping

from acmm.experiment_api import (
    runtime_materialization_context,
    runtime_materialization_finalization,
    runtime_resource_admission,
    runtime_resource_execution_context,
    runtime_resource_governor_session,
)

from .api_governor import github_api_governor, github_api_usage_delta
from .controller import github_controller_client


_ESTIMATOR = "historical_max_x1.25_v1"
_SAFETY_FACTOR = 1.25


@dataclass
class github_resource_governor_execution:
    history_samples: list[dict[str, Any]]
    history_artifacts: list[str]
    legacy_history_artifacts: list[str]


@dataclass(frozen=True)
class github_resource_admission_handle:
    start_snapshot: Mapping[str, Any]
    forecast: Mapping[str, Any]


class github_execution_resource_governor:
    def __init__(
        self,
        controller: github_controller_client,
        governor: github_api_governor,
        *,
        safety_factor: float = _SAFETY_FACTOR,
    ) -> None:
        if safety_factor < 1.0:
            raise ValueError("Resource forecast safety factor must be at least 1.0.")
        self._controller = controller
        self._governor = governor
        self._safety_factor = float(safety_factor)

    def execution_initialize(
        self,
        context: runtime_resource_execution_context,
    ) -> runtime_resource_governor_session:
        samples: list[dict[str, Any]] = []
        canonical_artifacts = list(context.history_artifacts)
        for record in context.history_records:
            samples.extend(_canonical_samples(record))

        legacy_artifacts: list[str] = []
        parent = Path(context.session_dir).parent
        known_execution_ids = {
            str(record.get("execution", {}).get("id"))
            for record in context.history_records
            if isinstance(record.get("execution"), Mapping)
        }
        legacy_candidates = [
            session / "apparatus_api_usage.json"
            for session in parent.glob("execution_*")
            if session.is_dir()
            and session != Path(context.session_dir)
            and (session / "apparatus_api_usage.json").is_file()
        ]
        legacy_candidates.sort(key=lambda path: (path.stat().st_mtime, str(path)))
        for legacy_path in legacy_candidates:
            session = legacy_path.parent
            execution_id = session.name.removeprefix("execution_")
            if execution_id in known_execution_ids:
                continue
            run_count = _single_scenario_legacy_run_count(
                session / "experiment_execution.yaml"
            )
            if run_count is None:
                continue
            try:
                value = json.loads(legacy_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            delta = value.get("delta") if isinstance(value, Mapping) else None
            if not isinstance(delta, Mapping):
                continue
            sample = _sample_from_delta(delta)
            sample["run_count"] = run_count
            samples.append(sample)
            legacy_artifacts.append(str(legacy_path))

        handle = github_resource_governor_execution(
            history_samples=samples,
            history_artifacts=canonical_artifacts,
            legacy_history_artifacts=legacy_artifacts,
        )
        return runtime_resource_governor_session(
            handle=handle,
            record={
                "id": "github_execution_resource_governor_v1",
                "estimator": _ESTIMATOR,
                "safety_factor": self._safety_factor,
                "history_sample_count": len(samples),
                "legacy_history_artifacts": legacy_artifacts,
                "limit_precedence": [
                    "provider_headers",
                    "persisted_provider_state",
                    "configured_secondary_fallback",
                ],
            },
        )

    def materialization_admit(
        self,
        session_handle: github_resource_governor_execution,
        context: runtime_materialization_context,
    ) -> runtime_resource_admission:
        if not isinstance(session_handle, github_resource_governor_execution):
            raise TypeError("GitHub resource-governor session handle is invalid.")
        forecast = _forecast(
            session_handle.history_samples,
            self._safety_factor,
            target_run_count=len(context.selected_run_indices),
        )
        boundary = self._governor.wait_for_forecast_capacity(
            forecast_content_requests=int(forecast["content_requests"]),
            forecast_primary_requests={
                str(domain): int(value)
                for domain, value in forecast["primary_requests"].items()
            },
        )
        start_snapshot = self._controller.api_usage_snapshot()
        cold_start = not session_handle.history_samples
        record = {
            "status": "admitted",
            "estimator": _ESTIMATOR,
            "history_sample_count": len(session_handle.history_samples),
            "cold_start": cold_start,
            "forecast": forecast,
            "boundary": boundary,
            "decision": {
                "status": "admitted",
                "wait_seconds": float(boundary.get("wait_seconds", 0.0)),
                "reason": (
                    "cold_start_live_limits_only"
                    if cold_start
                    else "historical_forecast_with_live_limits"
                ),
            },
        }
        return runtime_resource_admission(
            handle=github_resource_admission_handle(
                start_snapshot=dict(start_snapshot),
                forecast=forecast,
            ),
            record=record,
        )

    def materialization_finalize(
        self,
        session_handle: github_resource_governor_execution,
        context: runtime_materialization_context,
        admission_handle: github_resource_admission_handle,
        outcome: runtime_materialization_finalization,
    ) -> Mapping[str, Any]:
        if not isinstance(session_handle, github_resource_governor_execution):
            raise TypeError("GitHub resource-governor session handle is invalid.")
        if not isinstance(admission_handle, github_resource_admission_handle):
            raise TypeError("GitHub resource admission handle is invalid.")
        end_snapshot = self._controller.api_usage_snapshot()
        delta = github_api_usage_delta(admission_handle.start_snapshot, end_snapshot)
        sample = _sample_from_delta(delta)
        session_handle.history_samples.append(sample)
        return {
            "completed": outcome.completed,
            "interrupted": outcome.interrupted,
            "detail": outcome.detail,
            "delta": delta,
            "sample": sample,
            "provider_window_after": end_snapshot.get("provider_window", {}),
        }


def _canonical_samples(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    materializations = record.get("materializations")
    if not isinstance(materializations, list):
        return values
    for item in materializations:
        if not isinstance(item, Mapping):
            continue
        usage = item.get("usage")
        if not isinstance(usage, Mapping):
            continue
        run_indices = item.get("selected_run_indices")
        run_count = len(run_indices) if isinstance(run_indices, list) else 0
        sample = usage.get("sample")
        if isinstance(sample, Mapping):
            normalized = dict(sample)
            if run_count > 0:
                normalized["run_count"] = run_count
            values.append(normalized)
            continue
        delta = usage.get("delta")
        if isinstance(delta, Mapping):
            normalized = _sample_from_delta(delta)
            if run_count > 0:
                normalized["run_count"] = run_count
            values.append(normalized)
    return values


def _sample_from_delta(delta: Mapping[str, Any]) -> dict[str, Any]:
    metrics = delta.get("metrics") if isinstance(delta.get("metrics"), Mapping) else {}
    requests = _non_negative_number(metrics.get("requests"))
    not_modified = _non_negative_number(metrics.get("status_304"))
    domains = (
        delta.get("credential_domains")
        if isinstance(delta.get("credential_domains"), Mapping)
        else {}
    )
    primary: dict[str, int] = {}
    for domain, raw in domains.items():
        if not isinstance(raw, Mapping):
            continue
        domain_requests = _non_negative_number(raw.get("requests"))
        domain_304 = _non_negative_number(raw.get("status_304"))
        primary[str(domain)] = max(0, int(domain_requests - domain_304))
    git_plane = (
        delta.get("git_content_plane")
        if isinstance(delta.get("git_content_plane"), Mapping)
        else {}
    )
    git_metrics = (
        git_plane.get("metrics")
        if isinstance(git_plane.get("metrics"), Mapping)
        else {}
    )
    return {
        "content_requests": int(_non_negative_number(metrics.get("content_requests"))),
        "mutations": int(_non_negative_number(metrics.get("mutations"))),
        "requests": int(requests),
        "non_304_requests": max(0, int(requests - not_modified)),
        "primary_requests": primary,
        "git_pushes": int(_non_negative_number(git_metrics.get("pushes"))),
    }


def _forecast(
    samples: list[dict[str, Any]],
    safety_factor: float,
    *,
    target_run_count: int,
) -> dict[str, Any]:
    if target_run_count < 1:
        raise ValueError("Target materialization run count must be positive.")
    if not samples:
        return {
            "target_run_count": target_run_count,
            "content_requests": 0,
            "mutations": 0,
            "requests": 0,
            "non_304_requests": 0,
            "primary_requests": {},
            "git_pushes": 0,
        }

    def scale(sample: Mapping[str, Any]) -> float:
        run_count = int(_non_negative_number(sample.get("run_count")))
        if run_count <= 0:
            return 1.0
        # Never scale a measured fixed setup cost downward. Scaling upward is
        # intentionally linear and therefore conservative when setup is shared.
        return max(1.0, target_run_count / run_count)

    scalar_keys = (
        "content_requests",
        "mutations",
        "requests",
        "non_304_requests",
        "git_pushes",
    )
    result = {
        key: int(
            math.ceil(
                max(
                    _non_negative_number(sample.get(key)) * scale(sample)
                    for sample in samples
                )
                * safety_factor
            )
        )
        for key in scalar_keys
    }
    domains = {
        str(domain)
        for sample in samples
        for domain in (
            sample.get("primary_requests", {}).keys()
            if isinstance(sample.get("primary_requests"), Mapping)
            else ()
        )
    }
    result["primary_requests"] = {
        domain: int(
            math.ceil(
                max(
                    _non_negative_number(
                        sample.get("primary_requests", {}).get(domain, 0)
                        if isinstance(sample.get("primary_requests"), Mapping)
                        else 0
                    )
                    * scale(sample)
                    for sample in samples
                )
                * safety_factor
            )
        )
        for domain in sorted(domains)
    }
    result["target_run_count"] = target_run_count
    return result


def _single_scenario_legacy_run_count(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(manifest, Mapping):
        return None
    slots = manifest.get("slots")
    if not isinstance(slots, list) or not slots:
        return None
    scenario_ids = {
        str(slot.get("scenario_id"))
        for slot in slots
        if isinstance(slot, Mapping) and slot.get("scenario_id") is not None
    }
    if len(scenario_ids) != 1:
        return None
    return len(slots)


def _non_negative_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, float(value))
