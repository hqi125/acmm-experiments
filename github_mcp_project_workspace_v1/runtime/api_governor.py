from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping


_STATE_SCHEMA_VERSION = "0.1"


@dataclass(frozen=True)
class github_api_governor_policy:
    mutation_interval_seconds: float = 1.0
    content_requests_per_minute: int = 60
    content_requests_per_hour: int = 360
    primary_remaining_floor: int = 1000
    primary_reset_grace_seconds: float = 2.0
    max_secondary_retries: int = 5
    secondary_backoff_seconds: tuple[float, ...] = (
        60.0,
        120.0,
        240.0,
        480.0,
        600.0,
    )

    def __post_init__(self) -> None:
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
        self._metrics = Counter()
        self._route_requests: dict[str, Counter[str]] = defaultdict(Counter)
        self._state = self._load_state()

    @property
    def policy(self) -> github_api_governor_policy:
        return self._policy

    def before_request(
        self,
        *,
        method: str,
        route: str,
        content_generating: bool,
    ) -> None:
        method_upper = method.upper()
        mutation = method_upper in {"POST", "PATCH", "PUT", "DELETE"}
        self._refresh_state()

        self._wait_for_provider_clear(content_generating=content_generating)
        self._wait_for_primary_headroom()
        if content_generating:
            self._wait_for_content_budget()

        if mutation:
            self._wait_for_mutation_spacing()
            self._state["last_mutation_at"] = self._clock()

        if content_generating:
            now = self._clock()
            self._prune_content_timestamps(now)
            timestamps = list(self._state.get("content_request_timestamps", ()))
            timestamps.append(now)
            self._state["content_request_timestamps"] = timestamps

        if mutation or content_generating:
            self._persist_state()

        self._metrics["requests"] += 1
        if mutation:
            self._metrics["mutations"] += 1
        if content_generating:
            self._metrics["content_requests"] += 1
        self._route_requests[route]["requests"] += 1
        if mutation:
            self._route_requests[route]["mutations"] += 1
        if content_generating:
            self._route_requests[route]["content_requests"] += 1

    def observe_response(
        self,
        *,
        route: str,
        status: int,
        headers: Mapping[str, str],
        content_generating: bool,
    ) -> None:
        self._metrics[f"status_{status}"] += 1
        self._route_requests[route][f"status_{status}"] += 1
        self._refresh_state()
        self._record_primary_rate_snapshot(headers)
        if 200 <= status < 400 and content_generating:
            self._state["secondary_backoff_level"] = 0
        self._persist_state()

    def secondary_rate_limit_delay(
        self,
        *,
        status: int,
        headers: Mapping[str, str],
        detail: str,
    ) -> float | None:
        if status not in {403, 429}:
            return None
        rendered = detail.casefold()
        if (
            "secondary rate limit" not in rendered
            and "temporarily blocked from content creation" not in rendered
        ):
            return None

        self._refresh_state()
        now = self._clock()
        retry_after = _header_value(headers, "Retry-After")
        delay: float | None = None
        if retry_after is not None:
            try:
                parsed = float(retry_after)
            except ValueError:
                parsed = 0.0
            if parsed > 0:
                delay = parsed

        if delay is None:
            remaining = _header_value(headers, "X-RateLimit-Remaining")
            reset = _header_value(headers, "X-RateLimit-Reset")
            if remaining == "0" and reset is not None:
                try:
                    reset_at = float(reset)
                except ValueError:
                    reset_at = 0.0
                if reset_at > now:
                    delay = reset_at - now

        level = int(self._state.get("secondary_backoff_level", 0) or 0)
        if delay is None:
            index = min(level, len(self._policy.secondary_backoff_seconds) - 1)
            delay = self._policy.secondary_backoff_seconds[index]

        block_until = max(
            float(self._state.get("secondary_block_until", 0.0) or 0.0),
            now + delay,
        )
        self._state["secondary_block_until"] = block_until
        self._state["secondary_block_scope"] = (
            "content"
            if "temporarily blocked from content creation" in rendered
            else "all"
        )
        self._state["secondary_backoff_level"] = min(
            level + 1,
            len(self._policy.secondary_backoff_seconds) - 1,
        )
        self._state["last_secondary_limit_at"] = now
        self._persist_state()
        self._metrics["secondary_rate_limit_events"] += 1
        return max(0.0, block_until - now)

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
        return {
            "schema_version": "0.1",
            "scope": self._scope,
            "policy": {
                "mutation_interval_seconds": self._policy.mutation_interval_seconds,
                "content_requests_per_minute": self._policy.content_requests_per_minute,
                "content_requests_per_hour": self._policy.content_requests_per_hour,
                "primary_remaining_floor": self._policy.primary_remaining_floor,
                "primary_reset_grace_seconds": self._policy.primary_reset_grace_seconds,
                "max_secondary_retries": self._policy.max_secondary_retries,
                "secondary_backoff_seconds": list(
                    self._policy.secondary_backoff_seconds
                ),
            },
            "metrics": dict(self._metrics),
            "routes": routes,
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
                "primary_rate": dict(
                    self._state.get("primary_rate", {})
                    if isinstance(self._state.get("primary_rate"), Mapping)
                    else {}
                ),
            },
        }

    def _record_primary_rate_snapshot(self, headers: Mapping[str, str]) -> None:
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
            self._state["primary_rate"] = values

    def _wait_for_primary_headroom(self) -> None:
        """Preserve user-wide primary REST capacity for subject MCP traffic.

        Controller and subject credentials intentionally authenticate as the same
        GitHub owner, so their user-authenticated REST requests share the same
        primary rate-limit pool. The latest response headers are therefore used
        as a conservative account-wide headroom signal before the controller
        consumes another request.
        """
        floor = self._policy.primary_remaining_floor
        if floor <= 0:
            return
        while True:
            self._refresh_state()
            snapshot = self._state.get("primary_rate")
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
                self._state["primary_rate"] = {}
                self._persist_state()
                return
            if remaining > floor:
                return

            wait = reset_at - now + self._policy.primary_reset_grace_seconds
            if wait <= 0:
                self._state["primary_rate"] = {}
                self._persist_state()
                return
            self._record_wait("primary_budget_wait_seconds", wait)
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
            self._sleep(wait)

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
        if value.get("schema_version") != _STATE_SCHEMA_VERSION:
            return self._empty_state()
        if value.get("scope") != self._scope:
            return self._empty_state()
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
            "last_mutation_at": 0.0,
            "content_request_timestamps": [],
            "secondary_block_until": 0.0,
            "secondary_block_scope": "content",
            "secondary_backoff_level": 0,
            "last_secondary_limit_at": 0.0,
            "primary_rate": {},
        }


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
        "git_content_plane": {"metrics": git_metrics},
        "provider_window_after": end.get("provider_window", {}),
    }


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    expected = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == expected:
            rendered = str(value).strip()
            return rendered or None
    return None
