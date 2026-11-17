from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, MutableMapping
from urllib.parse import urlparse

import yaml

from acmm.experiment_api import (
    runtime_provider_pressure_action_result_event,
    runtime_provider_pressure_app_suspension,
    runtime_provider_pressure_app_policy,
    runtime_provider_pressure_gate_configuration,
    runtime_provider_pressure_transport_action,
    runtime_provider_pressure_transport_recovery,
    runtime_provider_pressure_transport_request,
    runtime_provider_pressure_transport_response,
    runtime_provider_pressure_execution_context,
    runtime_provider_pressure_identity,
    runtime_provider_pressure_observation,
    runtime_provider_pressure_pacing_event,
    runtime_provider_pressure_policy,
    runtime_provider_pressure_recovery_event,
    runtime_provider_pressure_run_context,
    runtime_provider_pressure_run_outcome,
    runtime_provider_pressure_signal,
    runtime_provider_pressure_workload,
)

from .api_governor import github_api_governor, github_api_usage_delta
from .mcp_usage import github_mcp_usage_delta, github_mcp_usage_reader
from .controller import github_controller_client


@dataclass(frozen=True)
class github_pressure_measurement:
    start_snapshot: Mapping[str, Any]
    start_mcp_snapshot: Mapping[str, Any]


class github_provider_pressure_model:
    def __init__(
        self,
        controller: github_controller_client,
        governor: github_api_governor,
        *,
        mcp_usage: github_mcp_usage_reader | None = None,
        scope_id: str,
        definition: Mapping[str, Any],
        definition_sha256: str,
    ) -> None:
        self._controller = controller
        self._governor = governor
        self._mcp_usage = mcp_usage
        self._scope_id = str(scope_id)
        self._definition = dict(definition)
        self._definition_sha256 = str(definition_sha256)
        raw_watchdog_scenarios = self._definition.get(
            "action_watchdog_scenarios",
            self._definition.get("run_isolated_scenarios", ()),
        )
        self._watchdog_scenarios = frozenset(
            str(value) for value in raw_watchdog_scenarios
        )
        self._run_workload = _feature_mapping(self._definition.get("run_workload"))
        self._pressure_duration_scale_seconds = float(
            self._definition.get("pressure_duration_scale_seconds", 600.0)
        )
        if self._pressure_duration_scale_seconds <= 0:
            raise ValueError(
                "GitHub Provider Pressure pressure_duration_scale_seconds must be positive."
            )
        self._recovery_underprediction_scale_seconds = float(
            self._definition.get(
                "recovery_underprediction_scale_seconds",
                self._pressure_duration_scale_seconds,
            )
        )
        if self._recovery_underprediction_scale_seconds <= 0:
            raise ValueError(
                "GitHub Provider Pressure recovery_underprediction_scale_seconds "
                "must be positive."
            )
        raw_routes = self._definition.get("route_features")
        self._route_features = {
            str(route): _feature_mapping(features)
            for route, features in (
                raw_routes.items() if isinstance(raw_routes, Mapping) else ()
            )
        }
        raw_gate = self._definition.get("control_surface")
        gate = dict(raw_gate) if isinstance(raw_gate, Mapping) else {}
        self._gate_enabled = bool(gate.get("enabled", True))
        self._gate_bind_host = str(gate.get("bind_host") or "0.0.0.0")
        self._gate_bind_port = int(gate.get("bind_port", 8765))
        self._gate_advertised_url = str(
            gate.get("advertised_url")
            or f"http://host.docker.internal:{self._gate_bind_port}"
        )
        self._gate_request_interval_seconds = max(
            0.0, float(gate.get("request_interval_seconds", 1.0))
        )
        self._gate_mutation_interval_seconds = max(
            self._gate_request_interval_seconds,
            float(gate.get("mutation_interval_seconds", 2.0)),
        )
        raw_transport_actions = self._definition.get("transport_actions")
        self._transport_actions = (
            dict(raw_transport_actions)
            if isinstance(raw_transport_actions, Mapping)
            else {}
        )
        raw_console = self._definition.get("console_reporting")
        console = dict(raw_console) if isinstance(raw_console, Mapping) else {}
        self._console_action_patterns = tuple(
            str(value).strip()
            for value in console.get("action_patterns", ())
            if str(value).strip()
        )
        raw_policy = self._definition.get("policy")
        self._policy_parameters = (
            dict(raw_policy) if isinstance(raw_policy, Mapping) else {}
        )
        raw_app = self._definition.get("adaptive_pressure_pocket")
        app = dict(raw_app) if isinstance(raw_app, Mapping) else {}
        self._app_enabled = bool(app.get("enabled", False))
        self._app_actions = frozenset(str(value) for value in app.get("actions", ()))
        self._app_max_suspension_seconds = max(
            0.0, float(app.get("max_suspension_seconds", 600.0))
        )
        self._app_minimum_similarity = float(app.get("minimum_similarity", 0.75))
        if not 0.0 <= self._app_minimum_similarity <= 1.0:
            raise ValueError(
                "GitHub Adaptive Pressure Pocket minimum_similarity must be between 0 and 1."
            )
        self._app_provisional_probe_count = int(
            app.get("provisional_probe_count", 2)
        )
        self._app_established_probe_count = int(
            app.get("established_probe_count", 3)
        )
        if self._app_provisional_probe_count < 2:
            raise ValueError(
                "GitHub Adaptive Pressure Pocket provisional_probe_count must be at least 2."
            )
        if self._app_established_probe_count <= self._app_provisional_probe_count:
            raise ValueError(
                "GitHub Adaptive Pressure Pocket established_probe_count must exceed "
                "provisional_probe_count."
            )
        self._app_usage_metrics = tuple(
            str(value) for value in app.get(
                "usage_metrics",
                ("requests", "mutations", "content_requests", "pph_managed_requests"),
            )
        )
        self._app_provider_window_metrics = tuple(
            str(value) for value in app.get(
                "provider_window_metrics",
                ("content_requests_last_minute", "content_requests_last_hour"),
            )
        )
        raw_mcp = app.get("mcp_subject_usage")
        mcp = dict(raw_mcp) if isinstance(raw_mcp, Mapping) else {}
        self._app_mcp_enabled = bool(mcp.get("enabled", True))
        self._app_mcp_usage_metrics = tuple(
            str(value) for value in mcp.get(
                "usage_metrics",
                (
                    "requests",
                    "mutations",
                    "primary_rate_limit_events",
                    "secondary_rate_limit_events",
                ),
            )
        )
        self._app_mcp_method_metrics = tuple(
            str(value).upper()
            for value in mcp.get("method_metrics", ("GET", "POST", "PATCH", "PUT", "DELETE"))
        )
        self._app_mcp_state_metrics = tuple(
            str(value) for value in mcp.get(
                "state_metrics",
                ("backoff_level", "cooldown_remaining_seconds"),
            )
        )
        self._mcp_secondary_pressure_features = _feature_mapping(
            self._definition.get("mcp_secondary_pressure_features")
        )
        self._app_max_recent_probes = max(1, int(app.get("max_recent_probes", 32)))
        raw_geometry = app.get("geometry")
        geometry = dict(raw_geometry) if isinstance(raw_geometry, Mapping) else {}
        self._app_max_pressure_samples = max(
            1, int(geometry.get("max_pressure_samples_per_pocket", 32))
        )
        self._app_max_safe_observations = max(
            1, int(geometry.get("max_safe_observations", 64))
        )
        self._app_safe_boundary_min_observations = max(
            1, int(geometry.get("safe_boundary_min_observations", 2))
        )
        self._app_safe_boundary_min_probe_count = max(
            1, int(geometry.get("safe_boundary_min_probe_count", 2))
        )
        self._app_safe_boundary_margin = float(
            geometry.get("safe_boundary_margin", 0.05)
        )
        if not 0.0 <= self._app_safe_boundary_margin <= 1.0:
            raise ValueError(
                "GitHub Adaptive Pressure Pocket safe_boundary_margin must be "
                "between 0 and 1."
            )
        raw_prior = app.get("cold_start_prior")
        prior = dict(raw_prior) if isinstance(raw_prior, Mapping) else {}
        self._app_prior_enabled = bool(prior.get("enabled", False))
        self._app_prior_deactivate_at_probe_count = int(
            prior.get("deactivate_at_probe_count", self._app_provisional_probe_count)
        )
        if self._app_prior_deactivate_at_probe_count < 1:
            raise ValueError(
                "GitHub Adaptive Pressure Pocket cold-start prior probe threshold "
                "must be positive."
            )
        reference = prior.get("reference_limits")
        self._app_prior_reference_limits = (
            dict(reference) if isinstance(reference, Mapping) else {}
        )
        self._app_prior_actuated_dimensions = frozenset(
            str(value) for value in prior.get("actuated_dimensions", ())
        )
        self._app_prior_threshold_source = str(
            prior.get("operational_threshold_source", "controller_fallback_policy")
        )
        self._run_usage_starts: dict[tuple[str, int], Mapping[str, Any]] = {}
        self._run_mcp_usage_starts: dict[tuple[str, int], Mapping[str, Any]] = {}
        self._app_window_starts: dict[
            tuple[str, int], tuple[Mapping[str, Any], Mapping[str, Any]]
        ] = {}

    def _mcp_usage_snapshot(self) -> Mapping[str, Any]:
        if self._mcp_usage is None:
            return {
                "schema_version": "0.1",
                "observed_at": 0.0,
                "available": False,
                "metrics": {},
                "method_counts": {},
                "state": {},
            }
        return dict(self._mcp_usage.snapshot())

    def identity(
        self,
        context: runtime_provider_pressure_execution_context,
    ) -> runtime_provider_pressure_identity:
        return runtime_provider_pressure_identity(
            provider_id="github",
            scope_id=self._scope_id,
            model_id=str(self._definition["model_id"]),
            model_version=str(self._definition["model_version"]),
            model_definition_sha256=self._definition_sha256,
        )

    def policy(
        self,
        context: runtime_provider_pressure_execution_context,
    ) -> runtime_provider_pressure_policy:
        raw = self._definition.get("policy")
        if not isinstance(raw, Mapping):
            raise ValueError("GitHub Provider Pressure policy is missing.")
        return runtime_provider_pressure_policy(
            baseline_score=float(raw.get("baseline_score", 1.0)),
            punishment_increment=float(raw.get("punishment_increment", 1.5)),
            reward_decrement=float(raw.get("reward_decrement", 0.04)),
            score_ceiling=float(raw.get("score_ceiling", 8.0)),
            admission_free_score=float(raw.get("admission_free_score", 1.0)),
            base_delay_seconds=float(raw.get("base_delay_seconds", 30.0)),
            max_delay_seconds=float(raw.get("max_delay_seconds", 600.0)),
            confidence_observation_scale=int(
                raw.get("confidence_observation_scale", 20)
            ),
        )

    def app_policy(
        self,
        context: runtime_provider_pressure_execution_context,
    ) -> runtime_provider_pressure_app_policy:
        del context
        return runtime_provider_pressure_app_policy(
            enabled=self._app_enabled,
            actions=tuple(sorted(self._app_actions)),
            max_recent_probes=self._app_max_recent_probes,
        )

    def action_console_report(
        self,
        context: runtime_provider_pressure_run_context,
        action_id: str,
        workload: runtime_provider_pressure_workload,
        record: Mapping[str, Any],
    ) -> bool:
        del context, workload, record
        return any(
            fnmatchcase(action_id, pattern)
            for pattern in self._console_action_patterns
        )

    def transport_gate_configuration(
        self,
        context: runtime_provider_pressure_execution_context,
    ) -> runtime_provider_pressure_gate_configuration | None:
        del context
        if not self._gate_enabled or self._mcp_usage is None:
            return None
        return runtime_provider_pressure_gate_configuration(
            control_path=str(self._mcp_usage.state_path.parent / "pph-gate.json"),
            bind_host=self._gate_bind_host,
            bind_port=self._gate_bind_port,
            advertised_url=self._gate_advertised_url,
        )

    def transport_action(
        self,
        context: runtime_provider_pressure_run_context,
        request: runtime_provider_pressure_transport_request,
    ) -> runtime_provider_pressure_transport_action:
        del context
        kind = str(request.request_kind or "").strip().lower()
        parsed = urlparse(request.url)
        if not kind:
            if parsed.path == "/graphql":
                kind = "graphql"
            elif parsed.hostname == "raw.githubusercontent.com":
                kind = "raw"
            elif parsed.hostname == "api.github.com":
                kind = "rest"
            else:
                kind = "other"
        method = request.method.upper()
        graphql_operation = str(request.metadata.get("graphql_operation") or "").strip().lower()
        mutation = method in {"POST", "PATCH", "PUT", "DELETE"}
        if kind == "graphql" and graphql_operation in {"query", "mutation"}:
            mutation = graphql_operation == "mutation"
        plane = str(request.plane or "").strip().lower()
        route = str(request.metadata.get("route") or "").strip()
        if plane == "trusted_controller" and route:
            action_id = route
            configured = self._route_features.get(action_id)
            features = _feature_mapping(configured) if isinstance(configured, Mapping) else {}
        else:
            action_id = _transport_action_id(kind, mutation, plane=plane)
            configured = self._transport_actions.get(action_id)
            features = _feature_mapping(configured) if isinstance(configured, Mapping) else {}
        if not features:
            features = _default_transport_features(
                kind,
                method,
                parsed.path,
                plane=plane,
            )
        return runtime_provider_pressure_transport_action(
            action_id=action_id,
            workload=runtime_provider_pressure_workload(
                features=features,
                metadata={
                    "transport_plane": request.plane,
                    "transport_kind": kind,
                    "transport_method": method,
                    "transport_host": parsed.hostname or "",
                    "transport_path": parsed.path,
                    "graphql_operation": graphql_operation or None,
                    "baseline_request_interval_seconds": self._gate_request_interval_seconds,
                    "baseline_mutation_interval_seconds": self._gate_mutation_interval_seconds,
                    "baseline_mutation": mutation,
                    **dict(request.metadata),
                },
            ),
            metadata={
                "transport_plane": request.plane,
                "transport_kind": kind,
            },
        )

    def transport_recovery(
        self,
        context: runtime_provider_pressure_run_context,
        request: runtime_provider_pressure_transport_request,
        response: runtime_provider_pressure_transport_response,
    ) -> runtime_provider_pressure_transport_recovery | None:
        del context
        status = response.status
        graphql_rate_limited = _graphql_rate_limit_error(request, response)
        if status not in {403, 429} and not graphql_rate_limited:
            return None
        try:
            attempt = max(0, int(float(response.metadata.get("attempt", 0) or 0)))
        except (TypeError, ValueError):
            attempt = 0
        if attempt >= 5:
            return None
        retry_safe = _transport_retry_safe(request)
        headers = {str(k).casefold(): str(v) for k, v in response.headers.items()}
        remaining = headers.get("x-ratelimit-remaining", "").strip()
        retry_after = _retry_after_seconds(headers.get("retry-after"))
        reset_delay = _rate_reset_seconds(headers.get("x-ratelimit-reset"))
        if remaining == "0":
            if retry_after is not None:
                delay, source = retry_after + 3.0, "retry_after"
            elif reset_delay is not None:
                delay, source = reset_delay + 3.0, "rate_reset"
            else:
                delay, source = 60.0, "documented_fallback"
            self._governor.remember_provider_recovery(
                kind="primary", wait_seconds=delay
            )
            return runtime_provider_pressure_transport_recovery(
                kind="primary",
                wait_seconds=delay,
                recommendation_source=source,
                retry=retry_safe,
                metadata={
                    "provider_status": status,
                    "graphql_rate_limit_error": graphql_rate_limited,
                },
            )

        detail = response.body.casefold()
        secondary = (
            status == 429
            or graphql_rate_limited
            or retry_after is not None
            or "secondary rate limit" in detail
            or "abuse detection" in detail
            or "abuse rate" in detail
        )
        if not secondary:
            return None
        if retry_after is not None:
            delay, source = retry_after + 3.0, "retry_after"
        elif reset_delay is not None:
            delay, source = reset_delay + 3.0, "rate_reset"
        else:
            ladder = (60.0, 120.0, 240.0, 480.0, 960.0)
            delay = ladder[min(attempt, len(ladder) - 1)]
            source = "documented_fallback"
        self._governor.remember_provider_recovery(
            kind="secondary", wait_seconds=delay
        )
        return runtime_provider_pressure_transport_recovery(
            kind="secondary",
            wait_seconds=delay,
            recommendation_source=source,
            retry=retry_safe,
            metadata={
                "provider_status": status,
                "graphql_rate_limit_error": graphql_rate_limited,
            },
        )

    def historical_replay(
        self,
        context: runtime_provider_pressure_execution_context,
    ) -> tuple[runtime_provider_pressure_observation, ...]:
        root = Path(context.generated_root)
        observations: list[tuple[float, runtime_provider_pressure_observation]] = []
        for usage_path in root.rglob("apparatus_api_usage.json"):
            session = usage_path.parent
            if session == Path(context.session_dir):
                continue
            manifest_path = session / "experiment_execution.yaml"
            if not manifest_path.is_file():
                continue
            try:
                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                usage = json.loads(usage_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError):
                continue
            if not isinstance(manifest, Mapping) or not isinstance(usage, Mapping):
                continue
            execution = manifest.get("execution")
            if not isinstance(execution, Mapping):
                continue
            if execution.get("experiment_id") != context.experiment_id:
                continue
            execution_id = str(execution.get("id") or session.name.removeprefix("execution_"))
            delta = usage.get("delta")
            if not isinstance(delta, Mapping):
                continue
            mcp_path = session / "mcp_subject_api_usage.json"
            mcp_delta: Mapping[str, Any] = {}
            if mcp_path.is_file():
                try:
                    mcp_usage = json.loads(mcp_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    mcp_usage = {}
                if isinstance(mcp_usage, Mapping) and isinstance(
                    mcp_usage.get("delta"), Mapping
                ):
                    mcp_delta = mcp_usage["delta"]
            observation = self._observation_from_delta(
                delta,
                source_kind="historical_replay",
                source_execution_id=execution_id,
                include_pressure_signals=True,
                metadata={
                    "artifact": str(usage_path),
                    "mcp_subject_artifact": (str(mcp_path) if mcp_path.is_file() else None),
                    "mcp_subject_usage_delta": dict(mcp_delta),
                    "selected_run_count": len(execution.get("selected_run_indices", ())),
                },
            )
            mcp_signals = self._mcp_pressure_signals(mcp_delta)
            if mcp_signals:
                observation = runtime_provider_pressure_observation(
                    source_kind=observation.source_kind,
                    source_execution_id=observation.source_execution_id,
                    signals=tuple((*observation.signals, *mcp_signals)),
                    metadata=dict(observation.metadata),
                )
            if not observation.signals:
                continue
            started = _timestamp(execution.get("started_at"), fallback=usage_path.stat().st_mtime)
            observations.append((started, observation))
        observations.sort(key=lambda item: (item[0], item[1].source_execution_id))
        return tuple(item[1] for item in observations)

    def run_workload(
        self,
        context: runtime_provider_pressure_run_context,
    ) -> runtime_provider_pressure_workload:
        if context.scenario_id not in self._watchdog_scenarios:
            return runtime_provider_pressure_workload(
                features={},
                metadata={
                    "classification": "scenario_slice_without_action_watchdog",
                    "scenario_id": context.scenario_id,
                },
            )
        return runtime_provider_pressure_workload(
            features={},
            metadata={
                "classification": "scenario_slice_universal_provider_gate",
                "scenario_id": context.scenario_id,
                "control_surface": "active_run_provider_gate",
            },
        )

    def run_measurement_start(
        self,
        context: runtime_provider_pressure_run_context,
    ) -> github_pressure_measurement:
        snapshot = dict(self._controller.api_usage_snapshot())
        mcp_snapshot = self._mcp_usage_snapshot()
        key = (context.execution_id, context.run_index)
        self._run_usage_starts[key] = snapshot
        self._run_mcp_usage_starts[key] = mcp_snapshot
        self._app_window_starts[key] = (dict(snapshot), dict(mcp_snapshot))
        return github_pressure_measurement(
            start_snapshot=snapshot,
            start_mcp_snapshot=mcp_snapshot,
        )

    def app_admission_suspension(
        self,
        context: runtime_provider_pressure_run_context,
        action_id: str,
        workload: runtime_provider_pressure_workload,
        model_state: Mapping[str, Any],
    ) -> runtime_provider_pressure_app_suspension:
        max_suspension = self._app_max_suspension_seconds

        if not self._app_enabled or not any(
            fnmatchcase(action_id, pattern) for pattern in self._app_actions
        ):
            return runtime_provider_pressure_app_suspension(
                duration_seconds=0.0,
                metadata={"eligible": False, "action_id": action_id},
            )

        key = (context.execution_id, context.run_index)
        run_start = self._run_usage_starts.get(key)
        run_mcp_start = self._run_mcp_usage_starts.get(key)
        current = dict(self._controller.api_usage_snapshot())
        mcp_current = self._mcp_usage_snapshot()
        window_start, mcp_window_start = self._app_window_starts.get(
            key,
            (
                dict(run_start) if run_start is not None else dict(current),
                dict(run_mcp_start) if run_mcp_start is not None else dict(mcp_current),
            ),
        )
        app_state = _app_state_view(model_state)
        usage_vector = _app_usage_vector(
            window_start,
            current,
            usage_metrics=self._app_usage_metrics,
            provider_window_metrics=self._app_provider_window_metrics,
        )
        usage_vector.update(
            _app_mcp_usage_vector(
                mcp_window_start,
                mcp_current,
                enabled=self._app_mcp_enabled,
                usage_metrics=self._app_mcp_usage_metrics,
                method_metrics=self._app_mcp_method_metrics,
                state_metrics=self._app_mcp_state_metrics,
            )
        )
        interval = _app_accumulation_interval(window_start, current)
        pocket, geometry_match = _best_app_pocket(
            app_state.get("pockets", ()),
            action_id=action_id,
            features=workload.features,
            usage_vector=usage_vector,
            accumulation_interval_seconds=interval,
            safe_observations=app_state.get("safe_observations", ()),
            minimum_similarity=self._app_minimum_similarity,
            safe_boundary_margin=self._app_safe_boundary_margin,
            safe_boundary_min_observations=self._app_safe_boundary_min_observations,
            safe_boundary_min_probe_count=self._app_safe_boundary_min_probe_count,
        )

        empirical_wait = 0.0
        pocket_id = None
        stage = None
        confidence = 0.0
        matched_probe_count = 0
        if pocket is not None:
            pocket_id = pocket.get("pocket_id")
            stage = pocket.get("stage")
            matched_probe_count = max(0, int(pocket.get("probe_count", 0) or 0))
            confidence = max(0.0, min(1.0, float(pocket.get("confidence", 0.0))))
            learned_wait = max(
                0.0,
                float(pocket.get("mean_provider_recovery_seconds", 0.0)),
            )
            empirical_wait = min(
                max_suspension,
                learned_wait * confidence * float(geometry_match.get("pressure_support_similarity", 0.0)),
            )

        prior = _app_cold_start_prior(
            current,
            enabled=(
                self._app_prior_enabled
                and matched_probe_count < self._app_prior_deactivate_at_probe_count
            ),
            reference_limits=self._app_prior_reference_limits,
            actuated_dimensions=self._app_prior_actuated_dimensions,
            threshold_source=self._app_prior_threshold_source,
        )
        prior_wait = min(max_suspension, float(prior["recommended_wait_seconds"]))
        suspension_seconds = max(empirical_wait, prior_wait)
        if suspension_seconds > 0:
            # A suspension ends the current burst window.  The next action starts
            # a fresh density interval instead of repeatedly matching the same
            # accumulated burst after the enforced pause.
            self._app_window_starts[key] = (dict(current), dict(mcp_current))

        return runtime_provider_pressure_app_suspension(
            duration_seconds=suspension_seconds,
            metadata={
                "eligible": True,
                "action_id": action_id,
                "usage_vector": usage_vector,
                "usage_planes": {
                    "controller": "app_window_start_to_action_admission",
                    "subject_mcp": "app_window_start_to_action_admission",
                },
                "mcp_window_start_available": bool(mcp_window_start),
                "mcp_snapshot_available": bool(mcp_current.get("available")),
                "accumulation_interval_seconds": interval,
                "matched_pocket_id": pocket_id,
                "nearest_pocket_id": geometry_match.get("nearest_pocket_id"),
                "similarity": geometry_match.get("pressure_support_similarity", 0.0),
                "pressure_support_similarity": geometry_match.get(
                    "pressure_support_similarity", 0.0
                ),
                "safe_counterexample_similarity": geometry_match.get(
                    "safe_counterexample_similarity", 0.0
                ),
                "safe_counterexample_count": geometry_match.get(
                    "safe_counterexample_count", 0
                ),
                "pressure_support_count": geometry_match.get(
                    "pressure_support_count", 0
                ),
                "safe_boundary_active": geometry_match.get(
                    "safe_boundary_active", False
                ),
                "safe_boundary_blocked": geometry_match.get(
                    "safe_boundary_blocked", False
                ),
                "geometry_match_reason": geometry_match.get("reason"),
                "minimum_similarity": self._app_minimum_similarity,
                "stage": stage,
                "confidence": confidence,
                "matched_probe_count": matched_probe_count,
                "empirical_recommended_wait_seconds": empirical_wait,
                "cold_start_prior": prior,
                "suspension_seconds": suspension_seconds,
            },
        )

    def pacing_observe(
        self,
        context: runtime_provider_pressure_run_context,
        event: runtime_provider_pressure_pacing_event,
    ) -> runtime_provider_pressure_observation:
        if event.source != "runtime" or event.reason != "provider_secondary_pressure":
            return runtime_provider_pressure_observation(
                source_kind="live_execution",
                source_execution_id=context.execution_id,
                signals=(),
                metadata={
                    "run_index": context.run_index,
                    "ignored_reason": event.reason,
                },
            )
        severity = max(
            0.001,
            float(event.duration_seconds) / self._pressure_duration_scale_seconds,
        )
        return runtime_provider_pressure_observation(
            source_kind="live_execution",
            source_execution_id=context.execution_id,
            signals=(
                runtime_provider_pressure_signal(
                    kind="punishment",
                    count=1,
                    features=event.features,
                    severity=severity,
                    pressure_duration_seconds=float(event.duration_seconds),
                    metadata={
                        "action_id": event.action_id,
                        "pacing_reason": event.reason,
                        "runtime_pacing_seconds": float(event.duration_seconds),
                        "pressure_duration_scale_seconds": self._pressure_duration_scale_seconds,
                        **dict(event.metadata),
                    },
                ),
            ),
            metadata={
                "run_index": context.run_index,
                "subject_id": context.subject_id,
                "scenario_id": context.scenario_id,
                "action_id": event.action_id,
                "pacing_reason": event.reason,
            },
        )

    def recovery_observe(
        self,
        context: runtime_provider_pressure_run_context,
        event: runtime_provider_pressure_recovery_event,
    ) -> runtime_provider_pressure_observation:
        underprediction = max(0.0, float(event.underprediction_seconds))
        if underprediction <= 0:
            return runtime_provider_pressure_observation(
                source_kind="live_execution",
                source_execution_id=context.execution_id,
                signals=(),
                metadata={
                    "run_index": context.run_index,
                    "subject_id": context.subject_id,
                    "scenario_id": context.scenario_id,
                    "action_id": event.action_id,
                    "decision_id": event.decision_id,
                    "provider_recovery_kind": event.kind,
                    "recommendation_source": event.recommendation_source,
                    "provider_wait_seconds": float(event.wait_seconds),
                    "admission_wait_seconds": float(event.admission_wait_seconds),
                    "underprediction_seconds": 0.0,
                },
            )

        severity = max(
            0.001,
            underprediction / self._recovery_underprediction_scale_seconds,
        )
        return runtime_provider_pressure_observation(
            source_kind="live_execution",
            source_execution_id=context.execution_id,
            signals=(
                runtime_provider_pressure_signal(
                    kind="punishment",
                    count=1,
                    features=event.features,
                    severity=severity,
                    pressure_duration_seconds=underprediction,
                    metadata={
                        "action_id": event.action_id,
                        "decision_id": event.decision_id,
                        "provider_recovery_kind": event.kind,
                        "recommendation_source": event.recommendation_source,
                        "provider_wait_seconds": float(event.wait_seconds),
                        "admission_wait_seconds": float(event.admission_wait_seconds),
                        "underprediction_seconds": underprediction,
                        "recovery_underprediction_scale_seconds": (
                            self._recovery_underprediction_scale_seconds
                        ),
                        **dict(event.metadata),
                    },
                ),
            ),
            metadata={
                "run_index": context.run_index,
                "subject_id": context.subject_id,
                "scenario_id": context.scenario_id,
                "action_id": event.action_id,
                "decision_id": event.decision_id,
                "provider_recovery_kind": event.kind,
                "recommendation_source": event.recommendation_source,
                "provider_wait_seconds": float(event.wait_seconds),
                "admission_wait_seconds": float(event.admission_wait_seconds),
                "underprediction_seconds": underprediction,
            },
        )

    def app_probe_recovery_metadata(
        self,
        context: runtime_provider_pressure_run_context,
        event: runtime_provider_pressure_recovery_event,
        probe: Mapping[str, Any],
        model_state: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del probe
        del model_state
        key = (context.execution_id, context.run_index)
        run_start = self._run_usage_starts.get(key)
        run_mcp_start = self._run_mcp_usage_starts.get(key)
        window_start, mcp_window_start = self._app_window_starts.get(
            key,
            (run_start or {}, run_mcp_start or {}),
        )
        current = dict(self._controller.api_usage_snapshot())
        mcp_current = self._mcp_usage_snapshot()
        return {
            "observed_at": _snapshot_observed_at(current),
            "usage_vector": _combined_app_usage_vector(
                window_start,
                current,
                mcp_checkpoint=mcp_window_start,
                mcp_current=mcp_current,
                usage_metrics=self._app_usage_metrics,
                provider_window_metrics=self._app_provider_window_metrics,
                mcp_enabled=self._app_mcp_enabled,
                mcp_usage_metrics=self._app_mcp_usage_metrics,
                mcp_method_metrics=self._app_mcp_method_metrics,
                mcp_state_metrics=self._app_mcp_state_metrics,
            ),
            "provider_recovery_kind": event.kind,
            "recommendation_source": event.recommendation_source,
        }

    def app_safe_observe(
        self,
        context: runtime_provider_pressure_run_context,
        event: runtime_provider_pressure_action_result_event,
        model_state: MutableMapping[str, Any],
    ) -> Mapping[str, Any]:
        del context
        app_state = _app_state_mutable(model_state)
        safe_observation = _record_app_safe_observation(
            app_state,
            event,
            max_safe_observations=self._app_max_safe_observations,
        )
        if safe_observation is None:
            return {
                "adaptive_pressure_pocket": "no_open_probe",
                "app_window_mode": "run_local_burst_window",
            }
        return {
            "adaptive_pressure_pocket": "safe_observation_recorded",
            "app_safe_observation_kind": safe_observation["kind"],
            "app_safe_observation_count": len(app_state["safe_observations"]),
            "app_window_mode": "run_local_burst_window",
        }

    def app_probe_close(
        self,
        context: runtime_provider_pressure_run_context,
        event: runtime_provider_pressure_action_result_event,
        probe: Mapping[str, Any],
        model_state: MutableMapping[str, Any],
    ) -> Mapping[str, Any]:
        app_state = _app_state_mutable(model_state)
        mcp_current = self._mcp_usage_snapshot()
        component_metadata = _numeric_or_mapping(probe.get("component_metadata"))
        recovery_events: list[dict[str, Any]] = []
        for value in probe.get("recovery_events", ()):
            if not isinstance(value, Mapping):
                continue
            metadata = _numeric_or_mapping(value.get("metadata"))
            recovery_events.append(
                {
                    "ordinal": int(value.get("ordinal", len(recovery_events) + 1)),
                    "kind": str(value.get("kind") or "secondary"),
                    "recommendation_source": str(
                        value.get("recommendation_source") or "unknown"
                    ),
                    "provider_wait_seconds": float(
                        value.get("provider_wait_seconds", 0.0) or 0.0
                    ),
                    "underprediction_seconds": float(
                        value.get("underprediction_seconds", 0.0) or 0.0
                    ),
                    "observed_at": float(metadata.get("observed_at", 0.0) or 0.0),
                    "usage_vector": dict(
                        _numeric_or_mapping(metadata.get("usage_vector"))
                    ),
                }
            )
        geometry_probe = {
            "probe_id": probe.get("probe_id"),
            "decision_id": probe.get("decision_id"),
            "execution_id": context.execution_id,
            "run_index": context.run_index,
            "subject_id": context.subject_id,
            "scenario_id": context.scenario_id,
            "action_id": event.action_id,
            "features": dict(_numeric_mapping(probe.get("features"))),
            "trigger_usage_vector": dict(
                _numeric_or_mapping(component_metadata.get("usage_vector"))
            ),
            "trigger_accumulation_interval_seconds": float(
                component_metadata.get("accumulation_interval_seconds", 0.0) or 0.0
            ),
            "trigger_matched_pocket_id": component_metadata.get("matched_pocket_id"),
            "trigger_similarity": float(
                component_metadata.get("similarity", 0.0) or 0.0
            ),
            "trigger_event_pph_pressure": float(
                probe.get("event_pph_pressure", 0.0) or 0.0
            ),
            "trigger_event_pph_wait_seconds": float(
                probe.get("event_pph_wait_seconds", 0.0) or 0.0
            ),
            "trigger_app_suspension_seconds": float(
                probe.get("app_suspension_seconds", 0.0) or 0.0
            ),
            "total_admission_wait_seconds": float(
                probe.get("total_admission_wait_seconds", 0.0) or 0.0
            ),
            "opened_at": probe.get("opened_at"),
            "closed_at": _snapshot_observed_at(
                dict(self._controller.api_usage_snapshot())
            ),
            "recovery_events": recovery_events,
            "total_provider_recovery_seconds": float(
                probe.get("total_provider_recovery_seconds", 0.0) or 0.0
            ),
            "total_underprediction_seconds": float(
                probe.get("total_underprediction_seconds", 0.0) or 0.0
            ),
            "status": "closed",
            "resolution": event.outcome,
            "result_metadata": dict(event.metadata),
        }
        pocket = _update_app_pocket(
            app_state,
            geometry_probe,
            minimum_similarity=self._app_minimum_similarity,
            provisional_probe_count=self._app_provisional_probe_count,
            established_probe_count=self._app_established_probe_count,
            max_delay_seconds=self._app_max_suspension_seconds,
            max_pressure_samples=self._app_max_pressure_samples,
            safe_boundary_margin=self._app_safe_boundary_margin,
            safe_boundary_min_observations=self._app_safe_boundary_min_observations,
            safe_boundary_min_probe_count=self._app_safe_boundary_min_probe_count,
        )
        recent = app_state["recent_geometry_probes"]
        recent.append(geometry_probe)
        if len(recent) > self._app_max_recent_probes:
            del recent[:-self._app_max_recent_probes]
        key = (context.execution_id, context.run_index)
        self._app_window_starts[key] = (
            dict(self._controller.api_usage_snapshot()),
            dict(mcp_current),
        )
        return {
            "app_pocket_id": pocket["pocket_id"],
            "app_pocket_stage": pocket["stage"],
            "app_pocket_confidence": pocket["confidence"],
            "app_pocket_probe_count": pocket["probe_count"],
            "app_pocket_geometry_update": pocket.get("last_geometry_update"),
            "app_pocket_split_from": pocket.get("split_from_pocket_id"),
            "app_window_mode": "run_local_burst_window",
            "mcp_snapshot_available": bool(mcp_current.get("available")),
        }

    def run_observe(
        self,
        context: runtime_provider_pressure_run_context,
        measurement_handle: github_pressure_measurement,
        outcome: runtime_provider_pressure_run_outcome,
    ) -> runtime_provider_pressure_observation:
        if not isinstance(measurement_handle, github_pressure_measurement):
            raise TypeError("GitHub Provider Pressure measurement handle is invalid.")
        end = self._controller.api_usage_snapshot()
        delta = github_api_usage_delta(measurement_handle.start_snapshot, end)
        mcp_end = self._mcp_usage_snapshot()
        mcp_delta = github_mcp_usage_delta(
            measurement_handle.start_mcp_snapshot,
            mcp_end,
        )
        key = (context.execution_id, context.run_index)
        self._run_usage_starts.pop(key, None)
        self._run_mcp_usage_starts.pop(key, None)
        self._app_window_starts.pop(key, None)
        base = self._observation_from_delta(
            delta,
            source_kind="live_execution",
            source_execution_id=context.execution_id,
            include_pressure_signals=False,
            metadata={
                "run_index": context.run_index,
                "subject_id": context.subject_id,
                "scenario_id": context.scenario_id,
                "completed": outcome.completed,
                "resolved": outcome.resolved,
                "attempt_count": outcome.attempt_count,
                "terminations": list(outcome.terminations),
                "detail": outcome.detail,
                "mcp_subject_usage_delta": mcp_delta,
            },
        )
        return runtime_provider_pressure_observation(
            source_kind=base.source_kind,
            source_execution_id=base.source_execution_id,
            signals=tuple((*base.signals, *self._mcp_pressure_signals(mcp_delta))),
            metadata=dict(base.metadata),
        )

    def _mcp_pressure_signals(
        self,
        delta: Mapping[str, Any],
    ) -> tuple[runtime_provider_pressure_signal, ...]:
        metrics = _numeric_mapping(delta.get("metrics"))
        secondary_events = _non_negative_int(
            metrics.get("secondary_rate_limit_events", 0)
        )
        if secondary_events <= 0 or not self._mcp_secondary_pressure_features:
            return ()
        return (
            runtime_provider_pressure_signal(
                kind="punishment",
                count=secondary_events,
                features=self._mcp_secondary_pressure_features,
                severity=1.0,
                pressure_duration_seconds=0.0,
                metadata={
                    "plane": "subject_mcp",
                    "provider_pressure_kind": "secondary",
                    "secondary_rate_limit_events": secondary_events,
                    "duration_observed": False,
                    "governor_state_schema": delta.get("source", {}).get(
                        "state_schema_version"
                    )
                    if isinstance(delta.get("source"), Mapping)
                    else None,
                    "governor_version": delta.get("source", {}).get("governor_version")
                    if isinstance(delta.get("source"), Mapping)
                    else None,
                },
            ),
        )

    def _observation_from_delta(
        self,
        delta: Mapping[str, Any],
        *,
        source_kind: str,
        source_execution_id: str,
        metadata: Mapping[str, Any],
        include_pressure_signals: bool,
    ) -> runtime_provider_pressure_observation:
        routes = delta.get("routes")
        route_map = routes if isinstance(routes, Mapping) else {}
        signals: list[runtime_provider_pressure_signal] = []
        retry_span = max(1, int(self._governor.policy.max_secondary_retries))
        metrics = delta.get("metrics") if isinstance(delta.get("metrics"), Mapping) else {}
        cooldown_wait = float(metrics.get("secondary_cooldown_wait_seconds", 0.0) or 0.0)

        route_rows: list[tuple[str, Mapping[str, float], Mapping[str, Any], int, int]] = []
        total_secondary_events = 0
        for route, features in sorted(self._route_features.items()):
            raw = route_map.get(route)
            if not isinstance(raw, Mapping):
                continue
            secondary_events = _non_negative_int(raw.get("secondary_rate_limit_events"))
            if secondary_events <= 0:
                secondary_events = min(
                    _non_negative_int(raw.get("status_403"))
                    + _non_negative_int(raw.get("status_429")),
                    _non_negative_int(metrics.get("secondary_rate_limit_events", 0)),
                )
            successes = sum(
                _non_negative_int(value)
                for key, value in raw.items()
                if str(key).startswith("status_")
                and _successful_status_key(str(key))
            )
            route_rows.append((route, features, raw, secondary_events, successes))
            total_secondary_events += secondary_events

        for route, features, raw, secondary_events, successes in route_rows:
            route_pressure_seconds = 0.0
            if secondary_events > 0 and cooldown_wait > 0:
                route_pressure_seconds = (
                    cooldown_wait * secondary_events / total_secondary_events
                    if total_secondary_events > 0
                    else cooldown_wait
                )
            if include_pressure_signals and secondary_events > 0:
                average_pressure_seconds = (
                    route_pressure_seconds / secondary_events
                    if route_pressure_seconds > 0
                    else self._pressure_duration_scale_seconds
                )
                signals.append(
                    runtime_provider_pressure_signal(
                        kind="punishment",
                        count=secondary_events,
                        features=features,
                        severity=max(
                            0.001,
                            average_pressure_seconds / self._pressure_duration_scale_seconds,
                        ),
                        pressure_duration_seconds=route_pressure_seconds,
                        metadata={
                            "route": route,
                            "historical_pacing_events": secondary_events,
                            "runtime_pacing_seconds": route_pressure_seconds,
                            "pressure_duration_scale_seconds": self._pressure_duration_scale_seconds,
                        },
                    )
                )

            # A request that only succeeds after provider-pressure pacing is a
            # recovery, not a clean stability reward. Historical aggregate
            # telemetry cannot identify individual attempts, so conservatively
            # reserve one eventual success per retry-span-sized pressure cluster.
            recovered_successes = (
                min(successes, int(math.ceil(secondary_events / retry_span)))
                if secondary_events > 0
                else 0
            )
            clean_successes = max(0, successes - recovered_successes)
            if clean_successes > 0:
                signals.append(
                    runtime_provider_pressure_signal(
                        kind="reward",
                        count=clean_successes,
                        features=features,
                        severity=1.0,
                        metadata={
                            "route": route,
                            "clean_successes": clean_successes,
                            "recovered_successes_excluded": recovered_successes,
                        },
                    )
                )

        return runtime_provider_pressure_observation(
            source_kind=source_kind,
            source_execution_id=source_execution_id,
            signals=tuple(signals),
            metadata={
                **dict(metadata),
                "secondary_rate_limit_events": _non_negative_int(
                    delta.get("metrics", {}).get("secondary_rate_limit_events", 0)
                    if isinstance(delta.get("metrics"), Mapping)
                    else 0
                ),
                "secondary_cooldown_wait_seconds": cooldown_wait,
            },
        )


def _app_cold_start_prior(
    snapshot: Mapping[str, Any],
    *,
    enabled: bool,
    reference_limits: Mapping[str, Any],
    actuated_dimensions: frozenset[str],
    threshold_source: str,
) -> dict[str, Any]:
    policy = _numeric_mapping(snapshot.get("policy"))
    window = _numeric_mapping(snapshot.get("provider_window"))
    reference_minute = max(
        1, int(reference_limits.get("content_requests_per_minute", 80) or 80)
    )
    reference_hour = max(
        1, int(reference_limits.get("content_requests_per_hour", 500) or 500)
    )
    policy_minute = max(
        1, int(policy.get("content_requests_per_minute", reference_minute) or reference_minute)
    )
    policy_hour = max(
        1, int(policy.get("content_requests_per_hour", reference_hour) or reference_hour)
    )
    operational_minute = min(reference_minute, policy_minute)
    operational_hour = min(reference_hour, policy_hour)
    minute_count = max(
        0, int(window.get("content_requests_last_minute", 0) or 0)
    )
    hour_count = max(
        0, int(window.get("content_requests_last_hour", 0) or 0)
    )
    minute_active = (
        enabled
        and "content_requests_per_minute" in actuated_dimensions
        and minute_count >= operational_minute
    )
    hour_active = (
        enabled
        and "content_requests_per_hour" in actuated_dimensions
        and hour_count >= operational_hour
    )
    minute_wait = (
        max(0.0, float(window.get("content_minute_capacity_wait_seconds", 0.0) or 0.0))
        if minute_active
        else 0.0
    )
    hour_wait = (
        max(0.0, float(window.get("content_hour_capacity_wait_seconds", 0.0) or 0.0))
        if hour_active
        else 0.0
    )
    wait = max(minute_wait, hour_wait)
    return {
        "enabled": bool(enabled),
        "active": bool(enabled and (minute_active or hour_active)),
        "threshold_source": threshold_source,
        "reference_limits": dict(reference_limits),
        "actuated_dimensions": sorted(actuated_dimensions),
        "operational_thresholds": {
            "content_requests_per_minute": operational_minute,
            "content_requests_per_hour": operational_hour,
        },
        "observed": {
            "content_requests_last_minute": minute_count,
            "content_requests_last_hour": hour_count,
        },
        "utilization": {
            "content_requests_per_minute": round(
                minute_count / float(operational_minute), 6
            ),
            "content_requests_per_hour": round(
                hour_count / float(operational_hour), 6
            ),
        },
        "wait_components_seconds": {
            "content_requests_per_minute": minute_wait,
            "content_requests_per_hour": hour_wait,
        },
        "recommended_wait_seconds": wait,
    }


def _app_state_view(model_state: Mapping[str, Any]) -> Mapping[str, Any]:
    value = model_state.get("adaptive_pressure_pocket")
    return value if isinstance(value, Mapping) else {}


def _app_state_mutable(model_state: MutableMapping[str, Any]) -> dict[str, Any]:
    value = model_state.get("adaptive_pressure_pocket")
    if not isinstance(value, dict):
        value = {
            "schema_version": "0.5",
            "next_pocket_sequence": 0,
            "pockets": [],
            "recent_geometry_probes": [],
            "safe_observations": [],
        }
        model_state["adaptive_pressure_pocket"] = value
    value["schema_version"] = "0.5"
    value.setdefault("next_pocket_sequence", 0)
    value.setdefault("pockets", [])
    value.setdefault("recent_geometry_probes", [])
    value.setdefault("safe_observations", [])
    value.pop("mcp_action_checkpoint", None)
    return value


def _numeric_or_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _snapshot_observed_at(snapshot: Mapping[str, Any] | None) -> float:
    if not isinstance(snapshot, Mapping):
        return 0.0
    value = snapshot.get("observed_at")
    return float(value) if isinstance(value, (int, float)) else 0.0


def _app_accumulation_interval(
    start: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> float:
    start_at = _snapshot_observed_at(start)
    current_at = _snapshot_observed_at(current)
    if start_at <= 0 or current_at <= start_at:
        return 0.0
    return max(0.0, current_at - start_at)


def _numeric_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _app_usage_vector(
    start: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    *,
    usage_metrics: tuple[str, ...],
    provider_window_metrics: tuple[str, ...],
) -> dict[str, float]:
    start_metrics = (
        _numeric_mapping(start.get("metrics"))
        if isinstance(start, Mapping)
        else None
    )
    current_metrics = _numeric_mapping(current.get("metrics"))
    vector: dict[str, float] = {}
    for metric in usage_metrics:
        after = float(current_metrics.get(metric, 0.0) or 0.0)
        before = (
            float(start_metrics.get(metric, 0.0) or 0.0)
            if start_metrics is not None
            else after
        )
        vector[f"delta.{metric}"] = max(0.0, after - before)
    provider_window = _numeric_mapping(current.get("provider_window"))
    for metric in provider_window_metrics:
        raw = provider_window.get(metric, 0.0)
        vector[f"window.{metric}"] = max(
            0.0,
            float(raw) if isinstance(raw, (int, float)) else 0.0,
        )
    return vector


def _app_mcp_usage_vector(
    checkpoint: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    *,
    enabled: bool,
    usage_metrics: tuple[str, ...],
    method_metrics: tuple[str, ...],
    state_metrics: tuple[str, ...],
) -> dict[str, float]:
    vector: dict[str, float] = {}
    current_available = bool(current.get("available"))
    checkpoint_available = bool(
        isinstance(checkpoint, Mapping) and checkpoint.get("available")
    )
    current_metrics = _numeric_mapping(current.get("metrics"))
    checkpoint_metrics = (
        _numeric_mapping(checkpoint.get("metrics"))
        if checkpoint_available
        else {}
    )
    for metric in usage_metrics:
        after = float(current_metrics.get(metric, 0.0) or 0.0)
        before = float(checkpoint_metrics.get(metric, after) or 0.0)
        vector[f"mcp.delta.{metric}"] = (
            max(0.0, after - before)
            if enabled and current_available and checkpoint_available
            else 0.0
        )

    current_methods = _numeric_mapping(current.get("method_counts"))
    checkpoint_methods = (
        _numeric_mapping(checkpoint.get("method_counts"))
        if checkpoint_available
        else {}
    )
    for method in method_metrics:
        normalized = str(method).upper()
        after = float(current_methods.get(normalized, 0.0) or 0.0)
        before = float(checkpoint_methods.get(normalized, after) or 0.0)
        vector[f"mcp.delta.method.{normalized}"] = (
            max(0.0, after - before)
            if enabled and current_available and checkpoint_available
            else 0.0
        )

    state = _numeric_mapping(current.get("state"))
    for metric in state_metrics:
        raw = state.get(metric, 0.0)
        vector[f"mcp.state.{metric}"] = (
            max(0.0, float(raw))
            if enabled and current_available and isinstance(raw, (int, float))
            else 0.0
        )
    return vector


def _combined_app_usage_vector(
    start: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    *,
    mcp_checkpoint: Mapping[str, Any] | None,
    mcp_current: Mapping[str, Any],
    usage_metrics: tuple[str, ...],
    provider_window_metrics: tuple[str, ...],
    mcp_enabled: bool,
    mcp_usage_metrics: tuple[str, ...],
    mcp_method_metrics: tuple[str, ...],
    mcp_state_metrics: tuple[str, ...],
) -> dict[str, float]:
    vector = _app_usage_vector(
        start,
        current,
        usage_metrics=usage_metrics,
        provider_window_metrics=provider_window_metrics,
    )
    vector.update(
        _app_mcp_usage_vector(
            mcp_checkpoint,
            mcp_current,
            enabled=mcp_enabled,
            usage_metrics=mcp_usage_metrics,
            method_metrics=mcp_method_metrics,
            state_metrics=mcp_state_metrics,
        )
    )
    return vector


def _app_feature_match(
    pocket: Mapping[str, Any],
    features: Mapping[str, float],
) -> bool:
    stored = pocket.get("features")
    if not isinstance(stored, Mapping):
        return False
    return {
        str(key): round(float(value), 6)
        for key, value in stored.items()
    } == {
        str(key): round(float(value), 6)
        for key, value in features.items()
    }


def _similarity_value(left: float, right: float) -> float:
    scale = max(1.0, abs(left), abs(right))
    return max(0.0, 1.0 - abs(left - right) / scale)


def _app_point_similarity(
    usage_vector: Mapping[str, float],
    accumulation_interval_seconds: float,
    point_usage_vector: Mapping[str, Any],
    point_accumulation_interval_seconds: float,
) -> float:
    point_map = _numeric_mapping(point_usage_vector)
    keys = sorted(set(usage_vector) | set(str(key) for key in point_map))
    if keys:
        vector_similarity = sum(
            _similarity_value(
                float(usage_vector.get(key, 0.0)),
                float(point_map.get(key, 0.0) or 0.0),
            )
            for key in keys
        ) / len(keys)
    else:
        vector_similarity = 1.0
    interval_similarity = _similarity_value(
        float(accumulation_interval_seconds),
        float(point_accumulation_interval_seconds),
    )
    return round(0.8 * vector_similarity + 0.2 * interval_similarity, 6)


def _app_pressure_support(
    usage_vector: Mapping[str, float],
    accumulation_interval_seconds: float,
    pocket: Mapping[str, Any],
    *,
    minimum_similarity: float,
) -> tuple[float, int]:
    samples = pocket.get("geometry_samples")
    values: list[float] = []
    if isinstance(samples, list):
        for sample in samples:
            if not isinstance(sample, Mapping):
                continue
            values.append(
                _app_point_similarity(
                    usage_vector,
                    accumulation_interval_seconds,
                    _numeric_mapping(sample.get("usage_vector")),
                    float(sample.get("accumulation_interval_seconds", 0.0) or 0.0),
                )
            )
    if values:
        return max(values), sum(1 for value in values if value >= minimum_similarity)
    center = _numeric_mapping(pocket.get("center_usage_vector"))
    similarity = _app_point_similarity(
        usage_vector,
        accumulation_interval_seconds,
        center,
        float(pocket.get("mean_accumulation_interval_seconds", 0.0) or 0.0),
    )
    legacy_count = max(1, int(pocket.get("probe_count", 0) or 0))
    return similarity, legacy_count if similarity >= minimum_similarity else 0


def _app_safe_counterevidence(
    safe_observations: Any,
    *,
    action_id: str,
    features: Mapping[str, float],
    usage_vector: Mapping[str, float],
    accumulation_interval_seconds: float,
    minimum_similarity: float,
) -> tuple[float, int]:
    best = 0.0
    nearby = 0
    for observation in safe_observations if isinstance(safe_observations, list) else ():
        if not isinstance(observation, Mapping):
            continue
        if observation.get("action_id") != action_id:
            continue
        if not _app_feature_match(observation, features):
            continue
        similarity = _app_point_similarity(
            usage_vector,
            accumulation_interval_seconds,
            _numeric_mapping(observation.get("usage_vector")),
            float(observation.get("accumulation_interval_seconds", 0.0) or 0.0),
        )
        best = max(best, similarity)
        if similarity >= minimum_similarity:
            nearby += 1
    return round(best, 6), nearby


def _app_pocket_match(
    pocket: Mapping[str, Any],
    *,
    action_id: str,
    features: Mapping[str, float],
    usage_vector: Mapping[str, float],
    accumulation_interval_seconds: float,
    safe_observations: Any,
    minimum_similarity: float,
    safe_boundary_margin: float,
    safe_boundary_min_observations: int,
    safe_boundary_min_probe_count: int,
    apply_safe_boundary: bool = True,
) -> dict[str, Any]:
    support, pressure_support_count = _app_pressure_support(
        usage_vector,
        accumulation_interval_seconds,
        pocket,
        minimum_similarity=minimum_similarity,
    )
    safe_similarity, safe_count = _app_safe_counterevidence(
        safe_observations,
        action_id=action_id,
        features=features,
        usage_vector=usage_vector,
        accumulation_interval_seconds=accumulation_interval_seconds,
        minimum_similarity=minimum_similarity,
    )
    probe_count = max(0, int(pocket.get("probe_count", 0) or 0))
    safe_boundary_active = (
        apply_safe_boundary
        and probe_count >= safe_boundary_min_probe_count
        and safe_count >= safe_boundary_min_observations
        and safe_count > pressure_support_count
    )
    safe_boundary_blocked = (
        safe_boundary_active
        and safe_similarity + safe_boundary_margin >= support
    )
    if support < minimum_similarity:
        reason = "below_similarity"
    elif safe_boundary_blocked:
        reason = "safe_boundary"
    else:
        reason = "matched"
    return {
        "pocket_id": pocket.get("pocket_id"),
        "pressure_support_similarity": round(support, 6),
        "safe_counterexample_similarity": round(safe_similarity, 6),
        "safe_counterexample_count": safe_count,
        "pressure_support_count": pressure_support_count,
        "safe_boundary_active": safe_boundary_active,
        "safe_boundary_blocked": safe_boundary_blocked,
        "reason": reason,
        "eligible": reason == "matched",
    }


def _best_app_pocket(
    pockets: Any,
    *,
    action_id: str,
    features: Mapping[str, float],
    usage_vector: Mapping[str, float],
    accumulation_interval_seconds: float,
    safe_observations: Any = (),
    minimum_similarity: float = 0.75,
    safe_boundary_margin: float = 0.05,
    safe_boundary_min_observations: int = 2,
    safe_boundary_min_probe_count: int = 2,
    apply_safe_boundary: bool = True,
) -> tuple[Mapping[str, Any] | None, dict[str, Any]]:
    best: Mapping[str, Any] | None = None
    best_match: dict[str, Any] | None = None
    nearest: Mapping[str, Any] | None = None
    nearest_match: dict[str, Any] | None = None
    for candidate in pockets if isinstance(pockets, list) else ():
        if not isinstance(candidate, Mapping):
            continue
        if candidate.get("action_id") != action_id:
            continue
        if not _app_feature_match(candidate, features):
            continue
        match = _app_pocket_match(
            candidate,
            action_id=action_id,
            features=features,
            usage_vector=usage_vector,
            accumulation_interval_seconds=accumulation_interval_seconds,
            safe_observations=safe_observations,
            minimum_similarity=minimum_similarity,
            safe_boundary_margin=safe_boundary_margin,
            safe_boundary_min_observations=safe_boundary_min_observations,
            safe_boundary_min_probe_count=safe_boundary_min_probe_count,
            apply_safe_boundary=apply_safe_boundary,
        )
        if (
            nearest_match is None
            or match["pressure_support_similarity"]
            > nearest_match["pressure_support_similarity"]
        ):
            nearest = candidate
            nearest_match = match
        if not bool(match["eligible"]):
            continue
        if (
            best_match is None
            or match["pressure_support_similarity"]
            > best_match["pressure_support_similarity"]
        ):
            best = candidate
            best_match = match
    if best is not None and best_match is not None:
        return best, {
            **best_match,
            "nearest_pocket_id": best.get("pocket_id"),
        }
    if nearest is not None and nearest_match is not None:
        return None, {
            **nearest_match,
            "nearest_pocket_id": nearest.get("pocket_id"),
        }
    return None, {
        "pocket_id": None,
        "nearest_pocket_id": None,
        "pressure_support_similarity": 0.0,
        "safe_counterexample_similarity": 0.0,
        "safe_counterexample_count": 0,
        "pressure_support_count": 0,
        "safe_boundary_active": False,
        "safe_boundary_blocked": False,
        "reason": "no_feature_match",
        "eligible": False,
    }

def _app_stage(
    probe_count: int,
    *,
    provisional_probe_count: int,
    established_probe_count: int,
) -> str:
    if probe_count >= established_probe_count:
        return "established"
    if probe_count >= provisional_probe_count:
        return "provisional"
    return "exploratory"


def _update_running_mean(before: float, count_before: int, value: float) -> float:
    return (before * count_before + value) / float(count_before + 1)


def _rebuild_app_geometry(pocket: MutableMapping[str, Any]) -> None:
    samples = pocket.get("geometry_samples")
    usable = [sample for sample in samples if isinstance(sample, Mapping)] if isinstance(samples, list) else []
    if not usable:
        return
    keys: set[str] = set()
    for sample in usable:
        keys.update(str(key) for key in _numeric_mapping(sample.get("usage_vector")))
    center: dict[str, float] = {}
    usage_min: dict[str, float] = {}
    usage_max: dict[str, float] = {}
    for key in sorted(keys):
        values = [
            float(_numeric_mapping(sample.get("usage_vector")).get(key, 0.0) or 0.0)
            for sample in usable
        ]
        center[key] = sum(values) / float(len(values))
        usage_min[key] = min(values)
        usage_max[key] = max(values)
    intervals = [
        max(0.0, float(sample.get("accumulation_interval_seconds", 0.0) or 0.0))
        for sample in usable
    ]
    pocket["center_usage_vector"] = center
    pocket["mean_accumulation_interval_seconds"] = sum(intervals) / float(len(intervals))
    pocket["boundary"] = {
        "usage_min": usage_min,
        "usage_max": usage_max,
        "accumulation_interval_min_seconds": min(intervals),
        "accumulation_interval_max_seconds": max(intervals),
        "pressure_support_sample_count": len(usable),
    }


def _append_app_geometry_sample(
    pocket: MutableMapping[str, Any],
    probe: Mapping[str, Any],
    *,
    max_pressure_samples: int,
) -> None:
    samples = pocket.setdefault("geometry_samples", [])
    if not isinstance(samples, list):
        samples = []
        pocket["geometry_samples"] = samples
    samples.append(
        {
            "probe_id": probe.get("probe_id"),
            "usage_vector": {
                str(key): float(value)
                for key, value in _numeric_mapping(
                    probe.get("trigger_usage_vector")
                ).items()
                if isinstance(value, (int, float))
            },
            "accumulation_interval_seconds": max(
                0.0,
                float(
                    probe.get("trigger_accumulation_interval_seconds", 0.0)
                    or 0.0
                ),
            ),
        }
    )
    if len(samples) > max_pressure_samples:
        del samples[:-max_pressure_samples]
    _rebuild_app_geometry(pocket)


def _app_safe_observation_from_result(
    event: runtime_provider_pressure_action_result_event,
) -> dict[str, Any] | None:
    if event.outcome != "success":
        return None
    admission = event.metadata.get("admission_decision")
    if not isinstance(admission, Mapping):
        return None
    if float(admission.get("event_pph_wait_seconds", 0.0) or 0.0) > 0.0:
        return None
    if float(admission.get("app_suspension_seconds", 0.0) or 0.0) > 0.0:
        return None
    admission_metadata = admission.get("metadata")
    if not isinstance(admission_metadata, Mapping):
        return None
    app_suspension = admission_metadata.get("app_suspension")
    if not isinstance(app_suspension, Mapping):
        return None
    app_metadata = app_suspension.get("metadata")
    if not isinstance(app_metadata, Mapping) or not bool(app_metadata.get("eligible")):
        return None
    usage_vector = {
        str(key): float(value)
        for key, value in _numeric_mapping(app_metadata.get("usage_vector")).items()
        if isinstance(value, (int, float))
    }
    return {
        "decision_id": event.decision_id,
        "action_id": event.action_id,
        "features": dict(event.features),
        "usage_vector": usage_vector,
        "accumulation_interval_seconds": max(
            0.0,
            float(app_metadata.get("accumulation_interval_seconds", 0.0) or 0.0),
        ),
        "matched_pocket_id": app_metadata.get("matched_pocket_id"),
        "pressure_support_similarity": float(
            app_metadata.get("pressure_support_similarity", 0.0) or 0.0
        ),
        "kind": "zero_wait_success",
    }


def _record_app_safe_observation(
    app_state: MutableMapping[str, Any],
    event: runtime_provider_pressure_action_result_event,
    *,
    max_safe_observations: int,
) -> dict[str, Any] | None:
    observation = _app_safe_observation_from_result(event)
    if observation is None:
        return None
    observations = app_state.setdefault("safe_observations", [])
    if not isinstance(observations, list):
        observations = []
        app_state["safe_observations"] = observations
    observations.append(observation)
    if len(observations) > max_safe_observations:
        del observations[:-max_safe_observations]
    return observation


def _update_app_pocket(
    app_state: MutableMapping[str, Any],
    probe: Mapping[str, Any],
    *,
    minimum_similarity: float,
    provisional_probe_count: int,
    established_probe_count: int,
    max_delay_seconds: float,
    max_pressure_samples: int,
    safe_boundary_margin: float,
    safe_boundary_min_observations: int,
    safe_boundary_min_probe_count: int,
) -> dict[str, Any]:
    usage_vector = {
        str(key): float(value)
        for key, value in _numeric_mapping(probe.get("trigger_usage_vector")).items()
        if isinstance(value, (int, float))
    }
    interval = max(
        0.0,
        float(probe.get("trigger_accumulation_interval_seconds", 0.0) or 0.0),
    )
    features = {
        str(key): float(value)
        for key, value in _numeric_mapping(probe.get("features")).items()
        if isinstance(value, (int, float))
    }
    action_id = str(probe.get("action_id") or "unknown")
    pocket_value, geometry_match = _best_app_pocket(
        app_state.get("pockets", ()),
        action_id=action_id,
        features=features,
        usage_vector=usage_vector,
        accumulation_interval_seconds=interval,
        safe_observations=app_state.get("safe_observations", ()),
        minimum_similarity=minimum_similarity,
        safe_boundary_margin=safe_boundary_margin,
        safe_boundary_min_observations=safe_boundary_min_observations,
        safe_boundary_min_probe_count=safe_boundary_min_probe_count,
        apply_safe_boundary=False,
    )
    update_kind = "expanded"
    split_from_pocket_id = None
    if pocket_value is None:
        sequence = int(app_state.get("next_pocket_sequence", 0))
        app_state["next_pocket_sequence"] = sequence + 1
        if geometry_match.get("nearest_pocket_id") is not None:
            update_kind = "geometry_split"
            split_from_pocket_id = geometry_match.get("nearest_pocket_id")
        else:
            update_kind = "created"
        pocket: dict[str, Any] = {
            "pocket_id": f"pocket-{sequence:04d}",
            "action_id": action_id,
            "features": features,
            "center_usage_vector": dict(usage_vector),
            "mean_accumulation_interval_seconds": interval,
            "boundary": {
                "usage_min": dict(usage_vector),
                "usage_max": dict(usage_vector),
                "accumulation_interval_min_seconds": interval,
                "accumulation_interval_max_seconds": interval,
                "pressure_support_sample_count": 0,
            },
            "geometry_samples": [],
            "probe_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "interrupted_count": 0,
            "mean_provider_recovery_seconds": 0.0,
            "max_provider_recovery_seconds": 0.0,
            "mean_underprediction_seconds": 0.0,
            "stage": "exploratory",
            "confidence": 0.0,
            "recommended_suspension_seconds": 0.0,
            "last_probe_id": None,
            "created_reason": update_kind,
            "split_from_pocket_id": split_from_pocket_id,
        }
        app_state["pockets"].append(pocket)
    else:
        pocket = pocket_value if isinstance(pocket_value, dict) else dict(pocket_value)

    count_before = int(pocket.get("probe_count", 0))
    _append_app_geometry_sample(
        pocket,
        probe,
        max_pressure_samples=max_pressure_samples,
    )

    recovery_seconds = max(
        0.0,
        float(probe.get("total_provider_recovery_seconds", 0.0) or 0.0),
    )
    underprediction_seconds = max(
        0.0,
        float(probe.get("total_underprediction_seconds", 0.0) or 0.0),
    )
    pocket["mean_provider_recovery_seconds"] = _update_running_mean(
        float(pocket.get("mean_provider_recovery_seconds", 0.0) or 0.0),
        count_before,
        recovery_seconds,
    )
    pocket["max_provider_recovery_seconds"] = max(
        float(pocket.get("max_provider_recovery_seconds", 0.0) or 0.0),
        recovery_seconds,
    )
    pocket["mean_underprediction_seconds"] = _update_running_mean(
        float(pocket.get("mean_underprediction_seconds", 0.0) or 0.0),
        count_before,
        underprediction_seconds,
    )
    resolution = str(probe.get("resolution") or "failure")
    counter = f"{resolution}_count"
    if counter in {"success_count", "failure_count", "interrupted_count"}:
        pocket[counter] = int(pocket.get(counter, 0)) + 1
    pocket["probe_count"] = count_before + 1
    pocket["stage"] = _app_stage(
        int(pocket["probe_count"]),
        provisional_probe_count=provisional_probe_count,
        established_probe_count=established_probe_count,
    )
    pocket["confidence"] = round(
        min(1.0, int(pocket["probe_count"]) / float(established_probe_count)),
        6,
    )
    pocket["recommended_suspension_seconds"] = min(
        max_delay_seconds,
        float(pocket["mean_provider_recovery_seconds"]) * float(pocket["confidence"]),
    )
    pocket["last_probe_id"] = probe.get("probe_id")
    pocket["last_geometry_update"] = update_kind
    return pocket

def load_github_provider_pressure_definition(path: Path) -> tuple[dict[str, Any], str]:
    raw = Path(path).read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("GitHub Provider Pressure definition must be a JSON object.")
    for key in ("model_id", "model_version", "policy", "route_features"):
        if key not in value:
            raise ValueError(f"GitHub Provider Pressure definition is missing '{key}'.")
    return value, hashlib.sha256(raw).hexdigest()


def _feature_mapping(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, float] = {}
    for key, raw in value.items():
        weight = float(raw)
        if weight < 0:
            raise ValueError("GitHub Provider Pressure feature weights cannot be negative.")
        if weight > 0:
            result[str(key)] = weight
    return result


def _successful_status_key(key: str) -> bool:
    try:
        status = int(key.removeprefix("status_"))
    except ValueError:
        return False
    return 200 <= status < 400


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def _timestamp(value: Any, *, fallback: float) -> float:
    if not isinstance(value, str):
        return float(fallback)
    rendered = value.strip().replace("Z", "+00:00")
    try:
        from datetime import datetime

        return datetime.fromisoformat(rendered).timestamp()
    except ValueError:
        return float(fallback)


__all__ = [
    "github_provider_pressure_model",
    "load_github_provider_pressure_definition",
]


def _transport_retry_safe(
    request: runtime_provider_pressure_transport_request,
) -> bool:
    method = request.method.upper().strip()
    if method in {"GET", "HEAD", "OPTIONS"}:
        return True
    kind = str(request.request_kind or "").strip().lower()
    if kind == "graphql":
        operation = str(
            request.metadata.get("graphql_operation") or ""
        ).strip().lower()
        return operation == "query"
    return False


def _graphql_rate_limit_error(
    request: runtime_provider_pressure_transport_request,
    response: runtime_provider_pressure_transport_response,
) -> bool:
    parsed = urlparse(request.url)
    request_kind = str(request.request_kind or "").strip().casefold()
    if request_kind != "graphql" and parsed.path != "/graphql":
        return False
    if response.status not in {200, 403, 429}:
        return False

    body = str(response.body or "")
    if not body.strip():
        return False
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = None

    errors: list[Mapping[str, Any]] = []
    if isinstance(payload, Mapping):
        raw_errors = payload.get("errors")
        if isinstance(raw_errors, list):
            errors = [item for item in raw_errors if isinstance(item, Mapping)]
    if not errors:
        return False

    for error in errors:
        extensions = error.get("extensions")
        if not isinstance(extensions, Mapping):
            extensions = {}
        labels = (
            error.get("type"),
            error.get("code"),
            extensions.get("type"),
            extensions.get("code"),
        )
        for value in labels:
            normalized = str(value or "").strip().casefold().replace("-", "_")
            if normalized in {
                "rate_limited",
                "ratelimited",
                "rate_limit",
                "rate_limit_exceeded",
            }:
                return True
        detail = str(error.get("message") or "").casefold()
        if (
            "rate limit" in detail
            or "abuse detection" in detail
            or "abuse rate" in detail
        ):
            return True
    return False


def _transport_action_id(kind: str, mutation: bool, *, plane: str = "subject_mcp") -> str:
    normalized = kind if kind in {"rest", "graphql", "raw"} else "other"
    operation = "mutation" if mutation else "read"
    prefix = "mcp" if plane == "subject_mcp" else "controller"
    return f"{prefix}.{normalized}.{operation}"


def _default_transport_features(
    kind: str,
    method: str,
    path: str,
    *,
    plane: str = "subject_mcp",
) -> dict[str, float]:
    plane_feature = "plane.subject_mcp" if plane == "subject_mcp" else "plane.trusted_controller"
    features: dict[str, float] = {
        f"protocol.http.{method.upper()}": 0.15,
        "provider.github.shared_pressure": 1.0,
        plane_feature: 0.5,
        f"transport.{kind}": 0.5,
    }
    if method.upper() in {"POST", "PATCH", "PUT", "DELETE"}:
        features["mutation"] = 0.25
        features["semantic.update"] = 0.35
    else:
        features["semantic.read"] = 0.25
    resource = _github_path_resource(path)
    if resource:
        features[f"resource.{resource}"] = 0.4
    return features


def _github_path_resource(path: str) -> str:
    value = str(path).casefold()
    for marker, resource in (
        ("/issues", "issue"),
        ("/pulls", "pull_request"),
        ("/git/", "git"),
        ("/contents", "content"),
        ("/actions", "actions"),
        ("/branches", "branch"),
        ("/commits", "commit"),
        ("/repos/", "repository"),
    ):
        if marker in value:
            return resource
    return ""


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(str(value).strip())
    except ValueError:
        return None
    return max(0.0, parsed)


def _rate_reset_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        reset = float(str(value).strip())
    except ValueError:
        return None
    now = __import__("time").time()
    return max(0.0, reset - now) if reset > now else None
