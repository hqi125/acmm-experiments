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


_STATE_SCHEMA_VERSION = "0.3"

try:
    import fcntl
except ImportError:  # pragma: no cover - Experiment 2 runs under Linux/WSL.
    fcntl = None

_LOCAL_LOCKS_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[str, threading.RLock] = {}


@dataclass(frozen=True)
class github_api_governor_policy:
    request_interval_seconds: float = 0.25
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
        self._state = self._load_state()

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
    ) -> Iterator[None]:
        """Serialize a remote Git operation with REST/App traffic and cooldowns."""
        with self.serialized_provider_access():
            self.wait_for_provider_ready(content_generating=content_generating)
            yield

    @property
    def policy(self) -> github_api_governor_policy:
        return self._policy

    def set_progress_reporter(
        self,
        progress: Callable[[str], None] | None,
    ) -> None:
        self._progress = progress

    def before_request(
        self,
        *,
        method: str,
        route: str,
        content_generating: bool,
        primary_domain: str = "controller",
        enforce_primary_headroom: bool = True,
    ) -> None:
        domain = _primary_domain(primary_domain)
        method_upper = method.upper()
        mutation = method_upper in {"POST", "PATCH", "PUT", "DELETE"}
        self._refresh_state()

        self._wait_for_provider_clear(content_generating=content_generating)
        if self._policy.provider_authoritative_rate_limits:
            # A provider-reported remaining=0 is authoritative even for
            # cleanup-critical requests that bypass the legacy headroom reserve.
            self._wait_for_primary_exhaustion(domain)
        elif enforce_primary_headroom:
            self._wait_for_primary_headroom(domain)
        if content_generating and not self._policy.provider_authoritative_rate_limits:
            self._wait_for_content_budget()

        self._wait_for_request_spacing()
        self._state["last_request_at"] = self._clock()
        if mutation:
            self._wait_for_mutation_spacing()
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

    def rate_limit_delay(
        self,
        *,
        status: int,
        headers: Mapping[str, str],
        detail: str,
        primary_domain: str = "controller",
    ) -> float | None:
        """Record a provider-directed GitHub rate-limit wait.

        GitHub response headers are authoritative for primary-rate exhaustion.
        Secondary limits have no queryable remaining counter, so Retry-After is
        honored when present and GitHub's documented one-minute/exponential
        fallback is used only after GitHub has explicitly returned a secondary
        rate-limit response.
        """
        if status not in {403, 429}:
            return None

        domain = _primary_domain(primary_domain)
        self._refresh_state()
        now = self._clock()
        retry_after = _positive_header_float(headers, "Retry-After")
        if retry_after is not None:
            retry_after += self._policy.retry_after_grace_seconds
        remaining = _header_value(headers, "X-RateLimit-Remaining")
        reset_at = _positive_header_float(headers, "X-RateLimit-Reset")

        # GitHub defines remaining=0 as primary-rate exhaustion. This takes
        # precedence over textual secondary-limit heuristics.
        if remaining == "0":
            delay = retry_after
            if delay is None and reset_at is not None and reset_at > now:
                delay = reset_at - now + self._policy.primary_reset_grace_seconds
            if delay is None:
                delay = 60.0
            self._metrics["primary_rate_limit_events"] += 1
            self._metrics[f"primary_rate_limit_events_{domain}"] += 1
            self._state["last_primary_limit_at"] = now
            self._state["last_primary_limit_domain"] = domain
            self._state["last_rate_limit_kind"] = "primary"
            self._state["last_rate_limit_delay_seconds"] = float(delay)
            self._persist_state()
            return max(0.0, float(delay))

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
        level = int(self._state.get("secondary_backoff_level", 0) or 0)
        if delay is None:
            index = min(level, len(self._policy.secondary_backoff_seconds) - 1)
            delay = self._policy.secondary_backoff_seconds[index]

        block_until = max(
            float(self._state.get("secondary_block_until", 0.0) or 0.0),
            now + float(delay),
        )
        self._state["secondary_block_until"] = block_until
        # GitHub explicitly recommends stopping requests while secondary-limited.
        # Even a content-creation block therefore pauses the entire trusted API plane.
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
        return max(0.0, block_until - now)

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
        return {
            "schema_version": "0.1",
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

    def _wait_for_provider_clear(self, *, content_generating: bool) -> None:
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
            minute = [value for value in timestamps if value > now - 60.0]
            hour = [value for value in timestamps if value > now - 3600.0]
            waits: list[float] = []
            if len(minute) >= self._policy.content_requests_per_minute:
                waits.append(minute[0] + 60.0 - now + 0.05)
            if len(hour) >= self._policy.content_requests_per_hour:
                waits.append(hour[0] + 3600.0 - now + 0.05)
            wait = max((value for value in waits if value > 0), default=0.0)
            if wait <= 0:
                return
            self._record_wait("content_budget_wait_seconds", wait)
            self._report_wait("GitHub fallback content budget", wait)
            self._sleep(wait)

    def wait_for_provider_ready(
        self,
        *,
        content_generating: bool,
    ) -> None:
        """Apply persisted provider-wide cooldown to non-REST GitHub traffic."""
        self._refresh_state()
        self._wait_for_provider_clear(content_generating=content_generating)

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
            self._sleep(remaining)

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



def _approximate_duration(seconds: float) -> str:
    rounded = max(1, int(round(seconds)))
    if rounded < 60:
        return f"{rounded}s"
    minutes, remaining = divmod(rounded, 60)
    if minutes < 60:
        return f"{minutes}m {remaining:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"

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
