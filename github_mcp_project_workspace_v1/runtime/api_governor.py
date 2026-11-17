from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import time
import threading
from typing import Any, Callable, Iterator, Mapping

from .provider_gate_client import (
    github_provider_gate_admission,
    github_provider_gate_client,
    github_provider_gate_error,
)


_STATE_SCHEMA_VERSION = "0.3"

try:
    import fcntl
except ImportError:  # pragma: no cover - Experiment 2 runs under Linux/WSL.
    fcntl = None

_LOCAL_LOCKS_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[str, threading.RLock] = {}


@dataclass(frozen=True)
class github_api_governor_policy:
    request_interval_seconds: float = 1.0
    mutation_interval_seconds: float = 2.0
    content_requests_per_minute: int = 60
    content_requests_per_hour: int = 360
    primary_remaining_floor: int = 1000
    primary_reset_grace_seconds: float = 3.0
    retry_after_grace_seconds: float = 3.0
    max_secondary_retries: int = 5
    provider_authoritative_rate_limits: bool = True
    secondary_backoff_seconds: tuple[float, ...] = (
        60.0,
        120.0,
        240.0,
        480.0,
        960.0,
    )

    def __post_init__(self) -> None:
        if self.request_interval_seconds < 0:
            raise ValueError("GitHub request interval must not be negative.")
        if self.mutation_interval_seconds < 0:
            raise ValueError("GitHub mutation interval must not be negative.")
        if self.content_requests_per_minute < 1:
            raise ValueError("GitHub minute content budget must be positive.")
        if self.content_requests_per_hour < 1:
            raise ValueError("GitHub hourly content budget must be positive.")
        if self.primary_remaining_floor < 0:
            raise ValueError("GitHub primary-rate reserve must not be negative.")
        if self.primary_reset_grace_seconds < 0:
            raise ValueError("GitHub primary reset grace must not be negative.")
        if self.retry_after_grace_seconds < 0:
            raise ValueError("GitHub Retry-After grace must not be negative.")
        if self.max_secondary_retries < 0:
            raise ValueError("GitHub secondary retry count must not be negative.")
        if not self.secondary_backoff_seconds or any(
            delay <= 0 for delay in self.secondary_backoff_seconds
        ):
            raise ValueError("GitHub secondary backoff delays must be positive.")


@dataclass(frozen=True)
class github_rate_limit_recovery:
    kind: str
    wait_seconds: float
    recommendation_source: str
    status: int
    primary_domain: str
    route: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"primary", "secondary"}:
            raise ValueError("GitHub recovery kind must be primary or secondary.")
        if self.wait_seconds < 0:
            raise ValueError("GitHub recovery wait must not be negative.")
        if not self.recommendation_source.strip():
            raise ValueError("GitHub recovery recommendation source must not be empty.")
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


class github_api_governor:
    """Provider-scoped GitHub request pacing and secondary-limit state.

    The persisted state contains only timestamps/counters and a provider scope hash;
    no token, request body, or response body is written to disk.
    """

    def __init__(
        self,
        *,
        scope: str,
        policy: github_api_governor_policy | None = None,
        state_path: Path | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        rendered_scope = scope.strip()
        if not rendered_scope:
            raise ValueError("GitHub API governor scope must not be empty.")
        self._scope = rendered_scope
        self._policy = policy or github_api_governor_policy()
        self._clock = clock or time.time
        self._sleep = sleep or time.sleep
        self._state_path = state_path
        self._lock_path = (
            state_path.with_name(state_path.name + ".request.lock")
            if state_path is not None
            else None
        )
        lock_key = str(self._lock_path) if self._lock_path is not None else f"memory:{id(self)}"
        with _LOCAL_LOCKS_GUARD:
            self._local_request_lock = _LOCAL_LOCKS.setdefault(lock_key, threading.RLock())
        self._metrics = Counter()
        self._route_requests: dict[str, Counter[str]] = defaultdict(Counter)
        self._domain_requests: dict[str, Counter[str]] = defaultdict(Counter)
        self._progress: Callable[[str], None] | None = None
        self._pressure_action: Callable[[str, Mapping[str, float], Mapping[str, Any]], Mapping[str, Any]] | None = None
        self._pressure_pacing: Callable[[str, float, str, Mapping[str, float], Mapping[str, Any]], Mapping[str, Any]] | None = None
        self._pressure_recovery: Callable[[str, float, str, str, str | None, Mapping[str, float], Mapping[str, Any]], Mapping[str, Any]] | None = None
        self._pressure_action_result: Callable[[str, str, str | None, Mapping[str, float], Mapping[str, Any]], Mapping[str, Any]] | None = None
        self._pressure_action_id: str | None = None
        self._pressure_action_record: dict[str, Any] | None = None
        self._pressure_features: dict[str, float] = {}
        self._pressure_metadata: dict[str, Any] = {}
        self._provider_gate_client: github_provider_gate_client | None = None
        self._provider_gate_admission: github_provider_gate_admission | None = None
        self._provider_gate_attempt: int = 0
        self._provider_request_metadata: dict[str, Any] = {}
        self._state = self._load_state()

    @contextmanager
    def provider_request_scope(
        self,
        metadata: Mapping[str, Any] | None,
    ) -> Iterator[None]:
        previous = dict(self._provider_request_metadata)
        merged = dict(previous)
        merged.update(dict(metadata or {}))
        self._provider_request_metadata = merged
        try:
            yield
        finally:
            self._provider_request_metadata = previous

    @contextmanager
    def serialized_provider_access(self) -> Iterator[None]:
        """Serialize trusted GitHub traffic across threads and ACMM processes."""
        with self._local_request_lock:
            if self._lock_path is None or fcntl is None:
                yield
                return
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock_path.open("a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def serialized_git_operation(
        self,
        *,
        content_generating: bool,
        operation: str = "git.remote",
        owner: str | None = None,
        name: str | None = None,
    ) -> Iterator[None]:
        """Serialize and gate remote Git traffic without creating a second actuator."""
        with self.serialized_provider_access():
            gate_active = (
                self._provider_gate_client is not None
                and self._provider_gate_client.active()
            )
            admission = None
            if gate_active:
                repository = (
                    f"{owner}/{name}"
                    if owner and name
                    else "provider-repository"
                )
                admission = self._provider_gate_client.admit(
                    method=("POST" if content_generating else "GET"),
                    url=f"https://github.com/{repository}.git",
                    request_kind="git",
                    metadata={
                        **self._provider_request_metadata,
                        "route": operation,
                        "primary_domain": "controller",
                        "content_generating": bool(content_generating),
                        "baseline_mutation": bool(content_generating),
                    },
                )
                if admission is None:
                    raise github_provider_gate_error(
                        "Provider Gate became inactive during Git admission."
                    )
                self._metrics["provider_gate_admissions"] += 1
                self._metrics["pph_managed_requests"] += 1
            else:
                self.wait_for_provider_ready(content_generating=content_generating)
                self._wait_for_request_spacing()
                if content_generating:
                    self._wait_for_mutation_spacing()
                now = self._clock()
                self._state["last_request_at"] = now
                if content_generating:
                    self._state["last_mutation_at"] = now
                self._persist_state()
            try:
                yield
            except BaseException as exc:
                if admission is not None:
                    assert self._provider_gate_client is not None
                    self._provider_gate_client.feedback(
                        admission,
                        status=None,
                        headers={},
                        body="",
                        error=f"{exc.__class__.__name__}: {exc}",
                        attempt=0,
                        metadata={
                            **self._provider_request_metadata,
                            "route": operation,
                            "git_operation": True,
                        },
                    )
                    self._metrics["provider_gate_errors"] += 1
                raise
            else:
                if admission is not None:
                    assert self._provider_gate_client is not None
                    self._provider_gate_client.feedback(
                        admission,
                        status=200,
                        headers={},
                        body="",
                        attempt=0,
                        metadata={
                            **self._provider_request_metadata,
                            "route": operation,
                            "git_operation": True,
                        },
                    )
                    self._metrics["provider_gate_results"] += 1

    def provider_gate_active(self) -> bool:
        return bool(
            self._provider_gate_client is not None
            and self._provider_gate_client.active()
        )

    @property
    def policy(self) -> github_api_governor_policy:
        return self._policy

    def set_provider_gate_client(
        self,
        client: github_provider_gate_client | None,
    ) -> None:
        if self._provider_gate_admission is not None:
            raise RuntimeError(
                "Cannot replace GitHub Provider Gate client while a request is active."
            )
        self._provider_gate_client = client

    def set_progress_reporter(
        self,
        progress: Callable[[str], None] | None,
    ) -> None:
        self._progress = progress

    @contextmanager
    def provider_pressure_watchdog(
        self,
        *,
        action: Callable[[str, Mapping[str, float], Mapping[str, Any]], Mapping[str, Any]] | None,
        pacing: Callable[[str, float, str, Mapping[str, float], Mapping[str, Any]], Mapping[str, Any]] | None,
        recovery: Callable[[str, float, str, str, str | None, Mapping[str, float], Mapping[str, Any]], Mapping[str, Any]] | None = None,
        action_result: Callable[[str, str, str | None, Mapping[str, float], Mapping[str, Any]], Mapping[str, Any]] | None = None,
        action_id: str,
        features: Mapping[str, float],
        metadata: Mapping[str, Any] | None = None,
    ) -> Iterator[None]:
        previous = (
            self._pressure_action,
            self._pressure_pacing,
            self._pressure_recovery,
            self._pressure_action_result,
            self._pressure_action_id,
            dict(self._pressure_action_record) if self._pressure_action_record is not None else None,
            dict(self._pressure_features),
            dict(self._pressure_metadata),
        )
        self._pressure_action = action
        self._pressure_pacing = pacing
        self._pressure_recovery = recovery
        self._pressure_action_result = action_result
        self._pressure_action_id = str(action_id)
        self._pressure_action_record = None
        self._pressure_features = {str(k): float(v) for k, v in features.items() if float(v) > 0}
        self._pressure_metadata = dict(metadata or {})
        try:
            yield
        except KeyboardInterrupt:
            self._emit_pressure_action_result(
                "interrupted",
                {"exception_type": "KeyboardInterrupt"},
                suppress_errors=True,
            )
            raise
        except BaseException as exc:
            self._emit_pressure_action_result(
                "failure",
                {
                    "exception_type": exc.__class__.__name__,
                    "exception_detail": str(exc),
                },
                suppress_errors=True,
            )
            raise
        else:
            self._emit_pressure_action_result("success", {})
        finally:
            (
                self._pressure_action,
                self._pressure_pacing,
                self._pressure_recovery,
                self._pressure_action_result,
                self._pressure_action_id,
                prior_action_record,
                prior_features,
                prior_metadata,
            ) = previous
            self._pressure_action_record = prior_action_record
            self._pressure_features = prior_features
            self._pressure_metadata = prior_metadata

    def before_request(
        self,
        *,
        method: str,
        route: str,
        url: str | None = None,
        content_generating: bool,
        primary_domain: str = "controller",
        enforce_primary_headroom: bool = True,
        recovery_retry: bool = False,
        request_kind: str = "rest",
    ) -> None:
        domain = _primary_domain(primary_domain)
        method_upper = method.upper()
        mutation = method_upper in {"POST", "PATCH", "PUT", "DELETE"}
        direct_managed = (
            self._pressure_action is not None and self._pressure_action_id is not None
        )
        gate_active = False
        if self._provider_gate_client is not None:
            gate_active = self._provider_gate_client.active()

        self._refresh_state()
        if gate_active:
            if recovery_retry:
                if self._provider_gate_admission is None:
                    raise github_provider_gate_error(
                        "Provider Gate retry has no active admission."
                    )
            else:
                if self._provider_gate_admission is not None:
                    raise github_provider_gate_error(
                        "Provider Gate already has an active trusted-controller request."
                    )
                if not url:
                    raise github_provider_gate_error(
                        "Provider Gate managed request is missing its provider URL."
                    )
                admission = self._provider_gate_client.admit(
                    method=method_upper,
                    url=url,
                    request_kind=str(request_kind or "rest"),
                    metadata={
                        **self._provider_request_metadata,
                        "route": route,
                        "primary_domain": domain,
                        "content_generating": bool(content_generating),
                        "baseline_mutation": mutation,
                    },
                )
                if admission is None:
                    raise github_provider_gate_error(
                        "Provider Gate became inactive during managed admission."
                    )
                self._provider_gate_admission = admission
                self._provider_gate_attempt = 0
                self._metrics["provider_gate_admissions"] += 1
        else:
            # Provider-authoritative persisted cooldowns remain a fallback safety
            # mechanism outside the active Core gate.  Inside the gate, recovery
            # is already actuated synchronously by Core and must not be slept twice.
            self._wait_for_provider_clear(
                content_generating=content_generating, route=route
            )
            if self._policy.provider_authoritative_rate_limits:
                self._wait_for_primary_exhaustion(domain)

            if not direct_managed:
                if (
                    not self._policy.provider_authoritative_rate_limits
                    and enforce_primary_headroom
                ):
                    self._wait_for_primary_headroom(domain)
                if (
                    content_generating
                    and not self._policy.provider_authoritative_rate_limits
                ):
                    self._wait_for_content_budget()
                self._wait_for_request_spacing()
                if mutation:
                    self._wait_for_mutation_spacing()
            elif not recovery_retry:
                record = self._pressure_action(
                    self._pressure_action_id,
                    self._pressure_features,
                    {
                        **self._provider_request_metadata,
                        **self._pressure_metadata,
                        "route": route,
                        "method": method_upper,
                        "primary_domain": domain,
                        "request_kind": str(request_kind or "rest"),
                    },
                )
                self._pressure_action_record = (
                    dict(record) if isinstance(record, Mapping) else None
                )

        # These timestamps remain observational even when the Core gate owns
        # proactive pacing. They support evidence and fallback operation.
        self._state["last_request_at"] = self._clock()
        if mutation:
            self._state["last_mutation_at"] = self._clock()

        if content_generating:
            now = self._clock()
            self._prune_content_timestamps(now)
            timestamps = list(self._state.get("content_request_timestamps", ()))
            timestamps.append(now)
            self._state["content_request_timestamps"] = timestamps

        self._persist_state()

        self._metrics["requests"] += 1
        if mutation:
            self._metrics["mutations"] += 1
        if content_generating:
            self._metrics["content_requests"] += 1
        if gate_active:
            self._metrics["pph_managed_requests"] += 1
            if recovery_retry:
                self._metrics["pph_recovery_retry_requests"] += 1
        elif direct_managed:
            self._metrics["pph_managed_requests"] += 1
            if recovery_retry:
                self._metrics["pph_recovery_retry_requests"] += 1
        self._route_requests[route]["requests"] += 1
        self._domain_requests[domain]["requests"] += 1
        if mutation:
            self._route_requests[route]["mutations"] += 1
            self._domain_requests[domain]["mutations"] += 1
        if content_generating:
            self._route_requests[route]["content_requests"] += 1
            self._domain_requests[domain]["content_requests"] += 1

    def observe_response(
        self,
        *,
        route: str,
        status: int,
        headers: Mapping[str, str],
        content_generating: bool,
        primary_domain: str = "controller",
    ) -> None:
        domain = _primary_domain(primary_domain)
        self._metrics[f"status_{status}"] += 1
        self._route_requests[route][f"status_{status}"] += 1
        self._domain_requests[domain][f"status_{status}"] += 1
        self._refresh_state()
        self._record_primary_rate_snapshot(headers, domain)
        poll_interval = _positive_header_float(headers, "X-Poll-Interval")
        if poll_interval is not None:
            intervals = self._state.get("poll_intervals")
            if not isinstance(intervals, dict):
                intervals = {}
            intervals[route] = poll_interval
            self._state["poll_intervals"] = intervals
        if 200 <= status < 400:
            scope = str(self._state.get("secondary_block_scope", "content"))
            if content_generating or scope == "all":
                self._state["secondary_backoff_level"] = 0
        self._persist_state()

    def provider_request_error(
        self,
        detail: str,
    ) -> None:
        admission = self._provider_gate_admission
        if admission is None:
            return
        try:
            assert self._provider_gate_client is not None
            self._provider_gate_client.cancel(admission, detail)
        finally:
            self._provider_gate_admission = None
            self._provider_gate_attempt = 0
        self._metrics["provider_gate_errors"] += 1

    def rate_limit_recovery(
        self,
        *,
        status: int,
        headers: Mapping[str, str],
        detail: str,
        primary_domain: str = "controller",
        route: str | None = None,
        attempt: int = 0,
    ) -> github_rate_limit_recovery | None:
        """Classify provider recovery, using Core when the synchronous gate is active."""
        gate_admission = self._provider_gate_admission
        if gate_admission is not None:
            if self._provider_gate_client is None:
                raise github_provider_gate_error(
                    "Provider Gate admission exists without a gate client."
                )
            feedback = self._provider_gate_client.feedback(
                gate_admission,
                status=status,
                headers=headers,
                body=detail,
                attempt=int(attempt),
                metadata={
                    **self._provider_request_metadata,
                    "route": route,
                    "primary_domain": _primary_domain(primary_domain),
                },
            )
            if not feedback.retry:
                self._provider_gate_admission = None
                self._provider_gate_attempt = 0
                self._metrics["provider_gate_results"] += 1
                return None
            recovery_record = dict(feedback.recovery)
            wait_seconds = float(
                recovery_record.get("provider_wait_seconds", 0.0) or 0.0
            )
            kind = str(
                recovery_record.get("provider_recovery_kind") or "secondary"
            )
            source = str(
                recovery_record.get("recommendation_source")
                or "documented_fallback"
            )
            self._provider_gate_attempt = int(attempt) + 1
            self._metrics["provider_gate_recoveries"] += 1
            return github_rate_limit_recovery(
                kind=(kind if kind in {"primary", "secondary"} else "secondary"),
                wait_seconds=max(0.0, wait_seconds),
                recommendation_source=source,
                status=status,
                primary_domain=_primary_domain(primary_domain),
                route=route,
                metadata={
                    "gate_managed": True,
                    "gate_recovery_record": recovery_record,
                },
            )

        if status not in {403, 429}:
            return None

        domain = _primary_domain(primary_domain)
        self._refresh_state()
        now = self._clock()
        raw_retry_after = _positive_header_float(headers, "Retry-After")
        retry_after = raw_retry_after
        if retry_after is not None:
            retry_after += self._policy.retry_after_grace_seconds
        remaining = _header_value(headers, "X-RateLimit-Remaining")
        reset_at = _positive_header_float(headers, "X-RateLimit-Reset")

        if remaining == "0":
            delay = retry_after
            source = "retry_after" if delay is not None else "documented_fallback"
            if delay is None and reset_at is not None and reset_at > now:
                delay = reset_at - now + self._policy.primary_reset_grace_seconds
                source = "rate_reset"
            if delay is None:
                delay = 60.0
            self._metrics["primary_rate_limit_events"] += 1
            if route is not None:
                self._route_requests[route]["primary_rate_limit_events"] += 1
            self._metrics[f"primary_rate_limit_events_{domain}"] += 1
            self._state["last_primary_limit_at"] = now
            self._state["last_primary_limit_domain"] = domain
            self._state["last_rate_limit_kind"] = "primary"
            self._state["last_rate_limit_delay_seconds"] = float(delay)
            self._persist_state()
            return github_rate_limit_recovery(
                kind="primary",
                wait_seconds=max(0.0, float(delay)),
                recommendation_source=source,
                status=status,
                primary_domain=domain,
                route=route,
                metadata={
                    "raw_retry_after_seconds": raw_retry_after,
                    "retry_after_grace_seconds": self._policy.retry_after_grace_seconds,
                    "rate_reset": reset_at,
                },
            )

        rendered = detail.casefold()
        secondary = (
            retry_after is not None
            or status == 429
            or "secondary rate limit" in rendered
            or "temporarily blocked from content creation" in rendered
        )
        if not secondary:
            return None

        delay = retry_after
        source = "retry_after" if delay is not None else "documented_fallback"
        level = int(self._state.get("secondary_backoff_level", 0) or 0)
        if delay is None:
            index = min(level, len(self._policy.secondary_backoff_seconds) - 1)
            delay = self._policy.secondary_backoff_seconds[index]

        block_until = max(
            float(self._state.get("secondary_block_until", 0.0) or 0.0),
            now + float(delay),
        )
        self._state["secondary_block_until"] = block_until
        self._state["secondary_block_scope"] = "all"
        self._state["secondary_backoff_level"] = min(
            level + 1,
            len(self._policy.secondary_backoff_seconds) - 1,
        )
        self._state["last_secondary_limit_at"] = now
        self._state["last_rate_limit_kind"] = "secondary"
        self._state["last_rate_limit_delay_seconds"] = float(delay)
        self._persist_state()
        self._metrics["secondary_rate_limit_events"] += 1
        if route is not None:
            self._route_requests[route]["secondary_rate_limit_events"] += 1
        return github_rate_limit_recovery(
            kind="secondary",
            wait_seconds=max(0.0, block_until - now),
            recommendation_source=source,
            status=status,
            primary_domain=domain,
            route=route,
            metadata={
                "raw_retry_after_seconds": raw_retry_after,
                "retry_after_grace_seconds": self._policy.retry_after_grace_seconds,
                "secondary_backoff_level": level,
            },
        )

    def actuate_provider_recovery(
        self,
        recovery: github_rate_limit_recovery,
        *,
        attempt: int,
    ) -> Mapping[str, Any] | None:
        if bool(dict(recovery.metadata or {}).get("gate_managed", False)):
            # Core already actuated this recovery synchronously while handling
            # Provider Gate feedback. Returning here prevents a second sleep.
            self._metrics["pph_provider_recovery_events"] += 1
            self._metrics["pph_provider_recovery_seconds"] += float(
                recovery.wait_seconds
            )
            record = dict(recovery.metadata or {}).get("gate_recovery_record")
            return dict(record) if isinstance(record, Mapping) else None
        if self._pressure_recovery is None or self._pressure_action_id is None:
            return None
        action_record = self._pressure_action_record or {}
        decision_id = action_record.get("decision_id")
        record = self._pressure_recovery(
            recovery.kind,
            recovery.wait_seconds,
            recovery.recommendation_source,
            self._pressure_action_id,
            str(decision_id) if decision_id is not None else None,
            self._pressure_features,
            {
                **self._pressure_metadata,
                "route": recovery.route,
                "status": recovery.status,
                "primary_domain": recovery.primary_domain,
                "recovery_attempt": int(attempt),
                **dict(recovery.metadata or {}),
            },
        )
        self._metrics["pph_provider_recovery_events"] += 1
        self._metrics["pph_provider_recovery_seconds"] += float(recovery.wait_seconds)
        return dict(record) if isinstance(record, Mapping) else None

    def remember_provider_recovery(
        self,
        *,
        kind: str,
        wait_seconds: float,
    ) -> None:
        """Persist provider-authoritative cooldown state without actuating it.

        Core owns the active-run wait.  This persisted state protects fallback
        traffic if the execution is interrupted before the provider window clears.
        """
        if str(kind) != "secondary" or float(wait_seconds) <= 0:
            return
        self._refresh_state()
        now = self._clock()
        wait = max(0.0, float(wait_seconds))
        self._state["secondary_block_until"] = max(
            float(self._state.get("secondary_block_until", 0.0) or 0.0),
            now + wait,
        )
        self._state["secondary_block_scope"] = "all"
        self._state["last_secondary_limit_at"] = now
        self._state["last_rate_limit_kind"] = "secondary"
        self._state["last_rate_limit_delay_seconds"] = wait
        self._persist_state()

    def rate_limit_delay(
        self,
        *,
        status: int,
        headers: Mapping[str, str],
        detail: str,
        primary_domain: str = "controller",
        route: str | None = None,
    ) -> float | None:
        """Backward-compatible scalar view of rate_limit_recovery()."""
        recovery = self.rate_limit_recovery(
            status=status,
            headers=headers,
            detail=detail,
            primary_domain=primary_domain,
            route=route,
        )
        return None if recovery is None else recovery.wait_seconds

    def secondary_rate_limit_delay(
        self,
        *,
        status: int,
        headers: Mapping[str, str],
        detail: str,
    ) -> float | None:
        """Backward-compatible alias for older package tests/callers."""
        return self.rate_limit_delay(
            status=status,
            headers=headers,
            detail=detail,
        )


    def wait_for_poll(
        self,
        *,
        routes: tuple[str, ...],
        minimum_seconds: float,
    ) -> None:
        """Wait before a repeated GitHub poll, honoring X-Poll-Interval."""
        self._refresh_state()
        intervals = self._state.get("poll_intervals")
        interval_map = intervals if isinstance(intervals, Mapping) else {}
        recommended = max(
            (
                float(interval_map.get(route, 0.0) or 0.0)
                for route in routes
            ),
            default=0.0,
        )
        wait = max(float(minimum_seconds), recommended)
        if wait <= 0:
            return
        self._record_wait("poll_wait_seconds", wait)
        label = "GitHub poll interval"
        if recommended > float(minimum_seconds):
            label = "GitHub X-Poll-Interval"
        self._report_wait(label, wait)
        self._sleep(wait)

    def usage_snapshot(self) -> dict[str, Any]:
        self._refresh_state()
        now = self._clock()
        self._prune_content_timestamps(now)
        timestamps = tuple(
            float(value)
            for value in self._state.get("content_request_timestamps", ())
            if isinstance(value, (int, float))
        )
        routes = {
            route: dict(counter)
            for route, counter in sorted(self._route_requests.items())
        }
        credential_domains = {
            domain: dict(counter)
            for domain, counter in sorted(self._domain_requests.items())
        }
        primary_rates = self._primary_rates_snapshot()
        content_capacity = _content_capacity_snapshot(
            timestamps,
            now=now,
            minute_limit=self._policy.content_requests_per_minute,
            hour_limit=self._policy.content_requests_per_hour,
        )
        return {
            "schema_version": "0.1",
            "observed_at": now,
            "scope": self._scope,
            "policy": {
                "request_interval_seconds": self._policy.request_interval_seconds,
                "mutation_interval_seconds": self._policy.mutation_interval_seconds,
                "content_requests_per_minute": self._policy.content_requests_per_minute,
                "content_requests_per_hour": self._policy.content_requests_per_hour,
                "primary_remaining_floor": self._policy.primary_remaining_floor,
                "primary_reset_grace_seconds": self._policy.primary_reset_grace_seconds,
                "retry_after_grace_seconds": self._policy.retry_after_grace_seconds,
                "max_secondary_retries": self._policy.max_secondary_retries,
                "provider_authoritative_rate_limits": (
                    self._policy.provider_authoritative_rate_limits
                ),
                "secondary_backoff_seconds": list(
                    self._policy.secondary_backoff_seconds
                ),
            },
            "metrics": dict(self._metrics),
            "routes": routes,
            "credential_domains": credential_domains,
            "provider_window": {
                "content_requests_last_minute": sum(
                    1 for value in timestamps if value > now - 60.0
                ),
                "content_requests_last_hour": sum(
                    1 for value in timestamps if value > now - 3600.0
                ),
                "content_minute_capacity_wait_seconds": content_capacity[
                    "minute_wait_seconds"
                ],
                "content_hour_capacity_wait_seconds": content_capacity[
                    "hour_wait_seconds"
                ],
                "content_capacity_wait_seconds": content_capacity[
                    "wait_seconds"
                ],
                "secondary_block_until": float(
                    self._state.get("secondary_block_until", 0.0) or 0.0
                ),
                "secondary_block_scope": str(
                    self._state.get("secondary_block_scope", "content")
                ),
                "secondary_backoff_level": int(
                    self._state.get("secondary_backoff_level", 0) or 0
                ),
                "last_secondary_limit_at": float(
                    self._state.get("last_secondary_limit_at", 0.0) or 0.0
                ),
                "last_rate_limit_kind": self._state.get("last_rate_limit_kind"),
                "last_rate_limit_delay_seconds": float(
                    self._state.get("last_rate_limit_delay_seconds", 0.0) or 0.0
                ),
                "primary_rate": dict(primary_rates.get("controller", {})),
                "primary_rates": primary_rates,
                "poll_intervals": dict(self._state.get("poll_intervals", {})),
            },
        }

    def _record_primary_rate_snapshot(
        self,
        headers: Mapping[str, str],
        primary_domain: str,
    ) -> None:
        values: dict[str, str | float] = {}
        mapping = {
            "limit": "X-RateLimit-Limit",
            "remaining": "X-RateLimit-Remaining",
            "used": "X-RateLimit-Used",
            "reset": "X-RateLimit-Reset",
            "resource": "X-RateLimit-Resource",
        }
        for key, header in mapping.items():
            value = _header_value(headers, header)
            if value is not None:
                values[key] = value
        if values:
            values["observed_at"] = self._clock()
            primary_rates = self._state.get("primary_rates")
            if not isinstance(primary_rates, dict):
                primary_rates = {}
            primary_rates[primary_domain] = values
            self._state["primary_rates"] = primary_rates

    def _primary_rates_snapshot(self) -> dict[str, dict[str, Any]]:
        value = self._state.get("primary_rates")
        if not isinstance(value, Mapping):
            return {}
        return {
            str(domain): dict(snapshot)
            for domain, snapshot in value.items()
            if isinstance(snapshot, Mapping)
        }

    def _wait_for_primary_exhaustion(self, primary_domain: str) -> None:
        """Wait only when GitHub has authoritatively reported remaining=0."""
        while True:
            self._refresh_state()
            primary_rates = self._state.get("primary_rates")
            if not isinstance(primary_rates, Mapping):
                return
            snapshot = primary_rates.get(primary_domain)
            if not isinstance(snapshot, Mapping):
                return
            if str(snapshot.get("remaining", "")) != "0":
                return
            try:
                reset_at = float(str(snapshot.get("reset")))
            except (TypeError, ValueError):
                return
            now = self._clock()
            if reset_at <= now:
                updated = dict(primary_rates)
                updated.pop(primary_domain, None)
                self._state["primary_rates"] = updated
                self._persist_state()
                return
            wait = reset_at - now + self._policy.primary_reset_grace_seconds
            self._record_wait("primary_provider_wait_seconds", wait)
            self._report_wait(
                f"GitHub primary rate reset ({primary_domain})",
                wait,
            )
            self._sleep(wait)

    def _wait_for_primary_headroom(self, primary_domain: str) -> None:
        """Preserve primary REST headroom within one credential domain.

        Controller PAT traffic and GitHub App installation traffic have distinct
        primary rate-limit buckets. The governor therefore never lets one domain's
        response headers pace another domain. Shared secondary/content safety state
        remains provider-scoped.
        """
        floor = self._policy.primary_remaining_floor
        if floor <= 0:
            return
        while True:
            self._refresh_state()
            primary_rates = self._state.get("primary_rates")
            if not isinstance(primary_rates, Mapping):
                return
            snapshot = primary_rates.get(primary_domain)
            if not isinstance(snapshot, Mapping):
                return
            remaining_raw = snapshot.get("remaining")
            reset_raw = snapshot.get("reset")
            try:
                remaining = int(str(remaining_raw))
                reset_at = float(str(reset_raw))
            except (TypeError, ValueError):
                return

            now = self._clock()
            if reset_at <= now:
                updated = dict(primary_rates)
                updated.pop(primary_domain, None)
                self._state["primary_rates"] = updated
                self._persist_state()
                return
            if remaining > floor:
                return

            wait = reset_at - now + self._policy.primary_reset_grace_seconds
            if wait <= 0:
                updated = dict(primary_rates)
                updated.pop(primary_domain, None)
                self._state["primary_rates"] = updated
                self._persist_state()
                return
            self._record_wait("primary_budget_wait_seconds", wait)
            self._report_wait(
                f"GitHub fallback primary headroom ({primary_domain})",
                wait,
            )
            self._sleep(wait)

    def _wait_for_provider_clear(self, *, content_generating: bool, route: str | None = None) -> None:
        while True:
            now = self._clock()
            block_until = float(
                self._state.get("secondary_block_until", 0.0) or 0.0
            )
            scope = str(self._state.get("secondary_block_scope", "content"))
            if scope == "content" and not content_generating:
                return
            remaining = block_until - now
            if remaining <= 0:
                return
            self._record_wait("secondary_cooldown_wait_seconds", remaining)
            label = (
                "GitHub content cooldown"
                if scope == "content"
                else "GitHub provider cooldown"
            )
            self._emit_pressure_pacing(
                "provider_secondary_pressure",
                remaining,
                {"route": route, "scope": scope, "label": label},
            )
            self._report_wait(label, remaining)
            self._sleep(remaining)
            self._refresh_state()

    def _wait_for_content_budget(self) -> None:
        while True:
            self._refresh_state()
            now = self._clock()
            self._prune_content_timestamps(now)
            timestamps = sorted(
                float(value)
                for value in self._state.get("content_request_timestamps", ())
                if isinstance(value, (int, float))
            )
            capacity = _content_capacity_snapshot(
                timestamps,
                now=now,
                minute_limit=self._policy.content_requests_per_minute,
                hour_limit=self._policy.content_requests_per_hour,
            )
            wait = float(capacity["wait_seconds"])
            if wait <= 0:
                return
            self._record_wait("content_budget_wait_seconds", wait)
            self._report_wait("GitHub fallback content budget", wait)
            self._sleep(wait)

    def wait_for_forecast_capacity(
        self,
        *,
        forecast_content_requests: int,
        forecast_primary_requests: Mapping[str, int],
    ) -> dict[str, Any]:
        """Wait until the next materialization has conservative provider headroom.

        Primary-rate bounds come from the latest provider response headers whenever
        they are available. The local content ledger is a deliberately conservative
        fallback because GitHub does not expose secondary-limit status directly.
        """
        if forecast_content_requests < 0:
            raise ValueError("Forecast content requests must not be negative.")
        normalized_primary = {
            str(domain): int(value)
            for domain, value in forecast_primary_requests.items()
            if int(value) > 0
        }
        before = self.usage_snapshot()
        wait_before = float(self._metrics.get("wait_seconds", 0.0))

        self._refresh_state()
        self._wait_for_provider_clear(content_generating=True, route=None)

        content_limit = self._policy.content_requests_per_hour
        required_content = min(int(forecast_content_requests), content_limit)
        content_wait = 0.0
        if required_content > 0:
            self._refresh_state()
            now = self._clock()
            self._prune_content_timestamps(now)
            hour = sorted(
                float(value)
                for value in self._state.get("content_request_timestamps", ())
                if isinstance(value, (int, float)) and value > now - 3600.0
            )
            excess = len(hour) + required_content - content_limit
            if excess > 0:
                release_index = min(excess, len(hour)) - 1
                content_wait = max(0.0, hour[release_index] + 3600.0 - now + 0.05)
                if content_wait > 0:
                    self._record_wait(
                        "admission_content_budget_wait_seconds",
                        content_wait,
                    )
                    self._report_wait(
                        "GitHub scenario admission content budget",
                        content_wait,
                    )
                    self._sleep(content_wait)
                    self._refresh_state()

        primary_decisions: dict[str, dict[str, Any]] = {}
        primary_wait = 0.0
        now = self._clock()
        primary_rates = self._primary_rates_snapshot()
        waits: list[float] = []
        for domain, forecast in sorted(normalized_primary.items()):
            snapshot = primary_rates.get(domain)
            if not isinstance(snapshot, Mapping):
                primary_decisions[domain] = {
                    "source": "unobserved",
                    "forecast": forecast,
                }
                continue
            limit = _rate_integer(snapshot.get("limit"))
            remaining = _rate_integer(snapshot.get("remaining"))
            reset = _rate_float(snapshot.get("reset"))
            if limit is None or remaining is None or reset is None:
                primary_decisions[domain] = {
                    "source": "unobserved",
                    "forecast": forecast,
                }
                continue
            reserve = min(self._policy.primary_remaining_floor, max(0, limit - 1))
            usable_window = max(0, limit - reserve)
            admitted_forecast = min(forecast, usable_window)
            required_remaining = reserve + admitted_forecast
            blocked = remaining < required_remaining and reset > now
            wait = (reset - now + self._policy.primary_reset_grace_seconds) if blocked else 0.0
            if wait > 0:
                waits.append(wait)
            primary_decisions[domain] = {
                "source": "provider_headers",
                "resource": snapshot.get("resource"),
                "limit": limit,
                "remaining": remaining,
                "reset": reset,
                "reserve": reserve,
                "forecast": forecast,
                "admitted_forecast": admitted_forecast,
                "requires_in_slice_pacing": forecast > usable_window,
                "blocked_before_admission": blocked,
            }

        if waits:
            primary_wait = max(waits)
            self._record_wait("admission_primary_wait_seconds", primary_wait)
            self._report_wait("GitHub scenario admission primary budget", primary_wait)
            self._sleep(primary_wait)
            self._refresh_state()

        after = self.usage_snapshot()
        wait_after = float(self._metrics.get("wait_seconds", 0.0))
        return {
            "wait_seconds": max(0.0, wait_after - wait_before),
            "content": {
                "source": "configured_secondary_fallback",
                "hour_limit": content_limit,
                "forecast": int(forecast_content_requests),
                "admitted_forecast": required_content,
                "requires_in_slice_pacing": int(forecast_content_requests) > content_limit,
                "wait_seconds": content_wait,
            },
            "primary": primary_decisions,
            "primary_wait_seconds": primary_wait,
            "provider_window_before": before.get("provider_window", {}),
            "provider_window_after": after.get("provider_window", {}),
        }

    def wait_for_provider_ready(
        self,
        *,
        content_generating: bool,
    ) -> None:
        """Apply persisted provider-wide cooldown to non-REST GitHub traffic."""
        self._refresh_state()
        self._wait_for_provider_clear(content_generating=content_generating, route=None)

    def _wait_for_request_spacing(self) -> None:
        interval = self._policy.request_interval_seconds
        if interval <= 0:
            return
        now = self._clock()
        last = self._state.get("last_request_at")
        if not isinstance(last, (int, float)):
            return
        remaining = float(last) + interval - now
        if remaining > 0:
            self._record_wait("request_spacing_wait_seconds", remaining)
            self._emit_pressure_pacing(
                "governor_request_spacing",
                remaining,
                {"label": "GitHub request spacing"},
            )
            self._sleep(remaining)

    def _wait_for_mutation_spacing(self) -> None:
        interval = self._policy.mutation_interval_seconds
        if interval <= 0:
            return
        now = self._clock()
        last = self._state.get("last_mutation_at")
        if not isinstance(last, (int, float)):
            return
        remaining = float(last) + interval - now
        if remaining > 0:
            self._record_wait("mutation_spacing_wait_seconds", remaining)
            self._emit_pressure_pacing(
                "governor_mutation_spacing",
                remaining,
                {"label": "GitHub mutation spacing"},
            )
            self._sleep(remaining)

    def _emit_pressure_action_result(
        self,
        outcome: str,
        metadata: Mapping[str, Any] | None = None,
        *,
        suppress_errors: bool = False,
    ) -> None:
        if (
            self._pressure_action_result is None
            or self._pressure_action_id is None
            or self._pressure_action_record is None
        ):
            return
        decision_id = self._pressure_action_record.get("decision_id")
        try:
            self._pressure_action_result(
                outcome,
                self._pressure_action_id,
                str(decision_id) if decision_id is not None else None,
                self._pressure_features,
                {
                    **self._pressure_metadata,
                    "admission_decision": dict(self._pressure_action_record),
                    **dict(metadata or {}),
                },
            )
            self._metrics["pph_action_result_events"] += 1
            self._metrics[f"pph_action_result_{outcome}"] += 1
        except Exception:
            self._metrics["pph_action_result_errors"] += 1
            if not suppress_errors:
                raise

    def _emit_pressure_pacing(
        self,
        reason: str,
        seconds: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if (
            self._pressure_pacing is None
            or self._pressure_action_id is None
            or seconds <= 0
        ):
            return
        self._pressure_pacing(
            str(reason),
            float(seconds),
            self._pressure_action_id,
            self._pressure_features,
            {**self._pressure_metadata, **dict(metadata or {})},
        )

    def _report_wait(self, reason: str, seconds: float) -> None:
        if self._progress is None or seconds < 2.0:
            return
        self._progress(
            f"Pacing: {reason}, idling ~{_approximate_duration(seconds)}."
        )

    def _record_wait(self, field: str, seconds: float) -> None:
        self._metrics[field] += float(seconds)
        self._metrics["wait_seconds"] += float(seconds)

    def _load_state(self) -> dict[str, Any]:
        if self._state_path is None or not self._state_path.exists():
            return self._empty_state()
        try:
            value = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty_state()
        if not isinstance(value, dict):
            return self._empty_state()
        if value.get("scope") != self._scope:
            return self._empty_state()
        version = value.get("schema_version")
        if version == "0.1":
            legacy_primary = value.get("primary_rate")
            migrated = dict(value)
            migrated.pop("primary_rate", None)
            migrated["primary_rates"] = (
                {"controller": dict(legacy_primary)}
                if isinstance(legacy_primary, Mapping) and legacy_primary
                else {}
            )
            migrated["poll_intervals"] = {}
            migrated["schema_version"] = _STATE_SCHEMA_VERSION
            return migrated
        if version == "0.2":
            migrated = dict(value)
            migrated["poll_intervals"] = {}
            migrated["schema_version"] = _STATE_SCHEMA_VERSION
            return migrated
        if version != _STATE_SCHEMA_VERSION:
            return self._empty_state()
        primary_rates = value.get("primary_rates")
        if not isinstance(primary_rates, Mapping):
            value = dict(value)
            value["primary_rates"] = {}
        return value

    def _refresh_state(self) -> None:
        if self._state_path is None:
            return
        self._state = self._load_state()

    def _persist_state(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self._state_path)

    def _prune_content_timestamps(self, now: float) -> None:
        values = [
            float(value)
            for value in self._state.get("content_request_timestamps", ())
            if isinstance(value, (int, float)) and float(value) > now - 3600.0
        ]
        self._state["content_request_timestamps"] = values

    def _empty_state(self) -> dict[str, Any]:
        return {
            "schema_version": _STATE_SCHEMA_VERSION,
            "scope": self._scope,
            "scope_hash": hashlib.sha256(self._scope.encode("utf-8")).hexdigest(),
            "last_request_at": 0.0,
            "last_mutation_at": 0.0,
            "content_request_timestamps": [],
            "secondary_block_until": 0.0,
            "secondary_block_scope": "content",
            "secondary_backoff_level": 0,
            "last_secondary_limit_at": 0.0,
            "last_primary_limit_at": 0.0,
            "last_primary_limit_domain": "",
            "last_rate_limit_kind": None,
            "last_rate_limit_delay_seconds": 0.0,
            "primary_rates": {},
            "poll_intervals": {},
        }



def _content_capacity_snapshot(
    timestamps: tuple[float, ...] | list[float],
    *,
    now: float,
    minute_limit: int,
    hour_limit: int,
) -> dict[str, float]:
    ordered = sorted(float(value) for value in timestamps)
    minute = [value for value in ordered if value > now - 60.0]
    hour = [value for value in ordered if value > now - 3600.0]
    minute_wait = 0.0
    hour_wait = 0.0
    if len(minute) >= minute_limit:
        minute_wait = max(0.0, minute[0] + 60.0 - now + 0.05)
    if len(hour) >= hour_limit:
        hour_wait = max(0.0, hour[0] + 3600.0 - now + 0.05)
    return {
        "minute_wait_seconds": minute_wait,
        "hour_wait_seconds": hour_wait,
        "wait_seconds": max(minute_wait, hour_wait),
    }


def _approximate_duration(seconds: float) -> str:
    rounded = max(1, int(round(seconds)))
    rendered_seconds = f"{rounded}s"
    if rounded < 60:
        return rendered_seconds
    hours, remainder = divmod(rounded, 3600)
    minutes, seconds_part = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds_part:
        parts.append(f"{seconds_part}s")
    return f"{rendered_seconds} ({''.join(parts)})"

def _rate_integer(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _rate_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def default_github_api_governor_state_path(scope: str) -> Path:
    root = os.getenv("ACMM_GITHUB_PROVIDER_STATE_ROOT")
    if root:
        base = Path(root).expanduser()
    else:
        base = Path.home() / ".config" / "acmm" / "provider-state" / "github"
    digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:24]
    return base / f"{digest}.json"


def github_api_usage_delta(
    start: Mapping[str, Any],
    end: Mapping[str, Any],
) -> dict[str, Any]:
    start_metrics = start.get("metrics") if isinstance(start.get("metrics"), Mapping) else {}
    end_metrics = end.get("metrics") if isinstance(end.get("metrics"), Mapping) else {}
    keys = set(start_metrics) | set(end_metrics)
    metrics: dict[str, float | int] = {}
    for key in sorted(keys):
        before = start_metrics.get(key, 0)
        after = end_metrics.get(key, 0)
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            value = after - before
            metrics[str(key)] = value

    start_routes = start.get("routes") if isinstance(start.get("routes"), Mapping) else {}
    end_routes = end.get("routes") if isinstance(end.get("routes"), Mapping) else {}
    routes: dict[str, dict[str, float | int]] = {}
    for route in sorted(set(start_routes) | set(end_routes)):
        before_values = start_routes.get(route)
        after_values = end_routes.get(route)
        before_map = before_values if isinstance(before_values, Mapping) else {}
        after_map = after_values if isinstance(after_values, Mapping) else {}
        route_delta: dict[str, float | int] = {}
        for key in sorted(set(before_map) | set(after_map)):
            before = before_map.get(key, 0)
            after = after_map.get(key, 0)
            if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                value = after - before
                if value:
                    route_delta[str(key)] = value
        if route_delta:
            routes[str(route)] = route_delta

    start_domains = start.get("credential_domains") if isinstance(start.get("credential_domains"), Mapping) else {}
    end_domains = end.get("credential_domains") if isinstance(end.get("credential_domains"), Mapping) else {}
    credential_domains: dict[str, dict[str, float | int]] = {}
    for domain in sorted(set(start_domains) | set(end_domains)):
        before_values = start_domains.get(domain)
        after_values = end_domains.get(domain)
        before_map = before_values if isinstance(before_values, Mapping) else {}
        after_map = after_values if isinstance(after_values, Mapping) else {}
        domain_delta: dict[str, float | int] = {}
        for key in sorted(set(before_map) | set(after_map)):
            before = before_map.get(key, 0)
            after = after_map.get(key, 0)
            if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                value = after - before
                if value:
                    domain_delta[str(key)] = value
        if domain_delta:
            credential_domains[str(domain)] = domain_delta

    start_git = start.get("git_content_plane") if isinstance(start.get("git_content_plane"), Mapping) else {}
    end_git = end.get("git_content_plane") if isinstance(end.get("git_content_plane"), Mapping) else {}
    start_git_metrics = start_git.get("metrics") if isinstance(start_git.get("metrics"), Mapping) else {}
    end_git_metrics = end_git.get("metrics") if isinstance(end_git.get("metrics"), Mapping) else {}
    git_metrics: dict[str, float | int] = {}
    for key in sorted(set(start_git_metrics) | set(end_git_metrics)):
        before = start_git_metrics.get(key, 0)
        after = end_git_metrics.get(key, 0)
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            value = after - before
            if value:
                git_metrics[str(key)] = value

    return {
        "schema_version": "0.1",
        "metrics": metrics,
        "routes": routes,
        "credential_domains": credential_domains,
        "git_content_plane": {"metrics": git_metrics},
        "provider_window_after": end.get("provider_window", {}),
    }


def _primary_domain(value: str) -> str:
    rendered = str(value).strip()
    if not rendered:
        raise ValueError("GitHub primary-rate credential domain must not be empty.")
    return rendered


def _positive_header_float(headers: Mapping[str, str], name: str) -> float | None:
    value = _header_value(headers, name)
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    expected = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == expected:
            rendered = str(value).strip()
            return rendered or None
    return None
