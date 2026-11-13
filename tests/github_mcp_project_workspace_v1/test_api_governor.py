from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

import pytest

from acmm.experiment_package import (
    install_experiment_package,
    load_staged_experiment_runtime,
)
from acmm.secret_bindings import (
    bind_secret_file,
    experiment_secret_binding_key,
    initialize_secret_store,
)


ROOT = Path(__file__).resolve().parents[2] / "github_mcp_project_workspace_v1"
EXPERIMENT_ID = "github_mcp_project_workspace_v1"
CONTROLLER_TOKEN = "controller-secret-value"
APP_PRIVATE_KEY = "test-private-key-pem"


def _write_secret(path: Path, value: str) -> Path:
    path.write_text(value + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _load_runtime_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "source"
    shutil.copytree(
        ROOT,
        source,
        ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"),
    )

    bindings = tmp_path / "secret-bindings.yaml"
    monkeypatch.setenv("ACMM_SECRET_BINDINGS_FILE", str(bindings))
    monkeypatch.setenv("ACMM_SECRET_DIRECTORY", str(tmp_path / "secrets"))
    monkeypatch.setenv(
        "ACMM_GITHUB_PROVIDER_STATE_ROOT",
        str(tmp_path / "provider-state"),
    )
    initialize_secret_store()
    bind_secret_file(
        experiment_secret_binding_key(EXPERIMENT_ID, "controller_access_token"),
        _write_secret(tmp_path / "controller-token", CONTROLLER_TOKEN),
    )
    bind_secret_file(
        experiment_secret_binding_key(EXPERIMENT_ID, "github_app_private_key"),
        _write_secret(tmp_path / "github-app-private-key", "test-private-key-pem"),
    )

    package = install_experiment_package(source, tmp_path / "runtime-root")
    loaded = load_staged_experiment_runtime(package)
    diagnostic = loaded.runtime.diagnostics["github_fixture_controller"]
    controller_module = sys.modules[type(diagnostic._client).__module__]
    governor_module = sys.modules[controller_module.github_api_governor.__module__]
    return (
        governor_module.github_api_governor,
        governor_module.github_api_governor_policy,
        controller_module.github_controller_client,
    )


class _fake_clock:
    def __init__(self, start: float = 1000.0) -> None:
        self.value = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


def test_governor_persists_content_budget_across_instances(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    state = tmp_path / "github-governor.json"
    clock = _fake_clock()
    policy = github_api_governor_policy(
        request_interval_seconds=0.0,
        mutation_interval_seconds=0.0,
        content_requests_per_minute=10,
        content_requests_per_hour=2,
        max_secondary_retries=1,
        secondary_backoff_seconds=(5.0,),
        provider_authoritative_rate_limits=False,
    )

    first = github_api_governor(
        scope="https://api.github.com|octo",
        policy=policy,
        state_path=state,
        clock=clock.now,
        sleep=clock.sleep,
    )
    for _ in range(2):
        first.before_request(
            method="POST",
            route="repository.create",
            content_generating=True,
        )
        first.observe_response(
            route="repository.create",
            status=201,
            headers={},
            content_generating=True,
        )
        clock.value += 1.0

    second = github_api_governor(
        scope="https://api.github.com|octo",
        policy=policy,
        state_path=state,
        clock=clock.now,
        sleep=clock.sleep,
    )
    second.before_request(
        method="POST",
        route="repository.create",
        content_generating=True,
    )

    assert clock.sleeps
    assert clock.value >= 4600.0
    persisted = json.loads(state.read_text(encoding="utf-8"))
    assert persisted["scope"] == "https://api.github.com|octo"
    assert persisted["content_request_timestamps"] == [1001.0, 4600.05]


def test_controller_secondary_limit_wait_is_shared_provider_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        github_api_governor,
        github_api_governor_policy,
        github_controller_client,
    ) = _load_runtime_types(tmp_path, monkeypatch)
    clock = _fake_clock()
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
            content_requests_per_minute=60,
            content_requests_per_hour=360,
            max_secondary_retries=2,
            secondary_backoff_seconds=(5.0, 10.0),
        ),
        state_path=tmp_path / "state.json",
        clock=clock.now,
        sleep=clock.sleep,
    )
    messages: list[str] = []
    governor.set_progress_reporter(messages.append)
    calls = 0

    def transport(method, url, headers, payload):
        nonlocal calls
        del headers, payload
        calls += 1
        assert method == "POST"
        assert url.endswith("/user/repos")
        if calls == 1:
            return (
                403,
                {},
                json.dumps(
                    {
                        "message": (
                            "You have exceeded a secondary rate limit and have been "
                            "temporarily blocked from content creation."
                        )
                    }
                ).encode("utf-8"),
            )
        return (
            201,
            {},
            json.dumps(
                {
                    "id": 7,
                    "name": "demo",
                    "full_name": "octo/demo",
                    "private": True,
                    "owner": {"login": "octo"},
                }
            ).encode("utf-8"),
        )

    client = github_controller_client(
        "secret",
        transport=transport,
        redirect_transport=transport,
        governor=governor,
    )
    value = client.create_repository(
        name="demo",
        description="demo",
    )

    assert value["id"] == 7
    assert calls == 2
    assert clock.sleeps == [5.0]
    assert messages == ["Pacing: GitHub provider cooldown, idling ~5s."]
    snapshot = governor.usage_snapshot()
    assert snapshot["metrics"]["secondary_rate_limit_events"] == 1
    assert snapshot["metrics"]["requests"] == 2


def test_governor_keeps_delete_out_of_content_generation_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    clock = _fake_clock()
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
            content_requests_per_minute=1,
            content_requests_per_hour=1,
            max_secondary_retries=0,
            secondary_backoff_seconds=(5.0,),
            provider_authoritative_rate_limits=False,
        ),
        state_path=tmp_path / "state.json",
        clock=clock.now,
        sleep=clock.sleep,
    )

    governor.before_request(
        method="DELETE",
        route="repository.delete",
        content_generating=False,
    )
    governor.observe_response(
        route="repository.delete",
        status=204,
        headers={},
        content_generating=False,
    )

    snapshot = governor.usage_snapshot()
    assert snapshot["metrics"]["mutations"] == 1
    assert snapshot["metrics"].get("content_requests", 0) == 0
    assert snapshot["provider_window"]["content_requests_last_hour"] == 0


def test_governor_reserves_content_budget_before_response_and_tracks_primary_rate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    clock = _fake_clock()
    state = tmp_path / "state.json"
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
            content_requests_per_minute=5,
            content_requests_per_hour=5,
            max_secondary_retries=0,
            secondary_backoff_seconds=(5.0,),
            provider_authoritative_rate_limits=False,
        ),
        state_path=state,
        clock=clock.now,
        sleep=clock.sleep,
    )

    governor.before_request(
        method="POST",
        route="issue.comment",
        content_generating=True,
    )
    persisted = json.loads(state.read_text(encoding="utf-8"))
    assert persisted["content_request_timestamps"] == [1000.0]

    governor.observe_response(
        route="issue.comment",
        status=422,
        headers={
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "4988",
            "X-RateLimit-Used": "12",
            "X-RateLimit-Reset": "2000",
            "X-RateLimit-Resource": "core",
        },
        content_generating=True,
    )
    snapshot = governor.usage_snapshot()
    assert snapshot["provider_window"]["content_requests_last_hour"] == 1
    assert snapshot["provider_window"]["primary_rate"] == {
        "limit": "5000",
        "remaining": "4988",
        "used": "12",
        "reset": "2000",
        "resource": "core",
        "observed_at": 1000.0,
    }


def test_governor_preserves_controller_primary_headroom(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    clock = _fake_clock(start=1000.0)
    state = tmp_path / "state.json"
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
            content_requests_per_minute=60,
            content_requests_per_hour=360,
            primary_remaining_floor=1000,
            primary_reset_grace_seconds=2.0,
            max_secondary_retries=0,
            secondary_backoff_seconds=(5.0,),
            provider_authoritative_rate_limits=False,
        ),
        state_path=state,
        clock=clock.now,
        sleep=clock.sleep,
    )

    governor.before_request(
        method="GET",
        route="repository.read",
        content_generating=False,
    )
    governor.observe_response(
        route="repository.read",
        status=200,
        headers={
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "950",
            "X-RateLimit-Used": "4050",
            "X-RateLimit-Reset": "1010",
            "X-RateLimit-Resource": "core",
        },
        content_generating=False,
    )

    governor.before_request(
        method="GET",
        route="repository.read",
        content_generating=False,
    )

    assert clock.sleeps == [12.0]
    snapshot = governor.usage_snapshot()
    assert snapshot["metrics"]["primary_budget_wait_seconds"] == 12.0
    assert snapshot["provider_window"]["primary_rate"] == {}
    assert snapshot["policy"]["primary_remaining_floor"] == 1000
    assert snapshot["policy"]["primary_reset_grace_seconds"] == 2.0


def test_governor_keeps_primary_rate_domains_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    clock = _fake_clock(start=1000.0)
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
            content_requests_per_minute=60,
            content_requests_per_hour=360,
            primary_remaining_floor=1000,
            primary_reset_grace_seconds=2.0,
            max_secondary_retries=0,
            secondary_backoff_seconds=(5.0,),
            provider_authoritative_rate_limits=False,
        ),
        state_path=tmp_path / "state.json",
        clock=clock.now,
        sleep=clock.sleep,
    )

    governor.before_request(
        method="GET",
        route="repository.read",
        content_generating=False,
        primary_domain="controller",
    )
    governor.observe_response(
        route="repository.read",
        status=200,
        headers={
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "950",
            "X-RateLimit-Used": "4050",
            "X-RateLimit-Reset": "1010",
            "X-RateLimit-Resource": "core",
        },
        content_generating=False,
        primary_domain="controller",
    )

    governor.before_request(
        method="GET",
        route="app.installation.read",
        content_generating=False,
        primary_domain="installation",
    )
    assert clock.sleeps == []

    governor.before_request(
        method="GET",
        route="repository.read",
        content_generating=False,
        primary_domain="controller",
    )
    assert clock.sleeps == [12.0]


def test_governor_migrates_v01_primary_snapshot_to_controller_domain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "scope": "https://api.github.com|octo",
                "scope_hash": "legacy",
                "last_mutation_at": 0.0,
                "content_request_timestamps": [900.0],
                "secondary_block_until": 0.0,
                "secondary_block_scope": "content",
                "secondary_backoff_level": 0,
                "last_secondary_limit_at": 0.0,
                "primary_rate": {
                    "limit": "5000",
                    "remaining": "4900",
                    "reset": "2000",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
            max_secondary_retries=0,
            secondary_backoff_seconds=(5.0,),
        ),
        state_path=state,
        clock=lambda: 1000.0,
        sleep=lambda _seconds: None,
    )

    snapshot = governor.usage_snapshot()
    assert snapshot["provider_window"]["primary_rates"] == {
        "controller": {
            "limit": "5000",
            "remaining": "4900",
            "reset": "2000",
        }
    }
    governor.observe_response(
        route="repository.read",
        status=200,
        headers={},
        content_generating=False,
        primary_domain="controller",
    )
    persisted = json.loads(state.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == "0.3"
    assert "primary_rate" not in persisted
    assert persisted["primary_rates"]["controller"]["remaining"] == "4900"


def test_provider_authoritative_mode_observes_content_without_static_budget_wait(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    clock = _fake_clock()
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
            content_requests_per_minute=1,
            content_requests_per_hour=2,
            provider_authoritative_rate_limits=True,
            secondary_backoff_seconds=(5.0,),
        ),
        state_path=tmp_path / "state.json",
        clock=clock.now,
        sleep=clock.sleep,
    )

    for _ in range(3):
        governor.before_request(
            method="POST",
            route="repository.create",
            content_generating=True,
        )
        governor.observe_response(
            route="repository.create",
            status=201,
            headers={},
            content_generating=True,
        )

    assert clock.sleeps == []
    snapshot = governor.usage_snapshot()
    assert snapshot["provider_window"]["content_requests_last_hour"] == 3
    assert snapshot["policy"]["provider_authoritative_rate_limits"] is True


def test_provider_authoritative_mode_waits_only_when_primary_remaining_is_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    clock = _fake_clock(start=1000.0)
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
            primary_remaining_floor=1000,
            primary_reset_grace_seconds=2.0,
            provider_authoritative_rate_limits=True,
            secondary_backoff_seconds=(5.0,),
        ),
        state_path=tmp_path / "state.json",
        clock=clock.now,
        sleep=clock.sleep,
    )

    governor.observe_response(
        route="repository.read",
        status=200,
        headers={
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "950",
            "X-RateLimit-Reset": "1010",
        },
        content_generating=False,
    )
    governor.before_request(
        method="GET",
        route="repository.read",
        content_generating=False,
    )
    assert clock.sleeps == []

    governor.observe_response(
        route="repository.read",
        status=403,
        headers={
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1010",
        },
        content_generating=False,
    )
    delay = governor.rate_limit_delay(
        status=403,
        headers={
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1010",
        },
        detail="API rate limit exceeded",
    )
    assert delay == 12.0
    governor.before_request(
        method="GET",
        route="repository.read",
        content_generating=False,
    )
    assert clock.sleeps == [12.0]
    snapshot = governor.usage_snapshot()
    assert snapshot["metrics"]["primary_rate_limit_events"] == 1


def test_provider_authoritative_controller_stops_after_bounded_secondary_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        github_api_governor,
        github_api_governor_policy,
        github_controller_client,
    ) = _load_runtime_types(tmp_path, monkeypatch)
    clock = _fake_clock()
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
            max_secondary_retries=2,
            provider_authoritative_rate_limits=True,
            secondary_backoff_seconds=(1.0, 2.0, 4.0),
        ),
        state_path=tmp_path / "state.json",
        clock=clock.now,
        sleep=clock.sleep,
    )
    calls = 0

    def transport(method, url, headers, payload):
        nonlocal calls
        del headers, payload
        calls += 1
        assert method == "POST"
        assert url.endswith("/user/repos")
        return (
            403,
            {},
            json.dumps(
                {
                    "message": (
                        "You have exceeded a secondary rate limit and have been "
                        "temporarily blocked from content creation."
                    )
                }
            ).encode("utf-8"),
        )

    client = github_controller_client(
        "secret",
        transport=transport,
        redirect_transport=transport,
        governor=governor,
    )
    with pytest.raises(Exception, match="rate-limit recovery exhausted"):
        client.create_repository(name="demo", description="demo")

    assert calls == 3
    assert clock.sleeps == [1.0, 2.0]
    snapshot = governor.usage_snapshot()
    assert snapshot["metrics"]["secondary_rate_limit_events"] == 3


def test_governor_applies_retry_after_grace_and_provider_wide_cooldown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    clock = _fake_clock()
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
            retry_after_grace_seconds=3.0,
            max_secondary_retries=1,
            secondary_backoff_seconds=(60.0,),
        ),
        state_path=tmp_path / "state.json",
        clock=clock.now,
        sleep=clock.sleep,
    )
    delay = governor.rate_limit_delay(
        status=403,
        headers={"Retry-After": "60"},
        detail="secondary rate limit",
    )
    assert delay == 63.0
    governor.before_request(
        method="GET",
        route="repository.read",
        content_generating=False,
    )
    assert clock.sleeps == [63.0]


def test_governor_honors_x_poll_interval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    clock = _fake_clock()
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
        ),
        state_path=tmp_path / "state.json",
        clock=clock.now,
        sleep=clock.sleep,
    )
    governor.observe_response(
        route="workflow_run.read",
        status=200,
        headers={"X-Poll-Interval": "7"},
        content_generating=False,
    )
    governor.wait_for_poll(routes=("workflow_run.read",), minimum_seconds=2.0)
    assert clock.sleeps == [7.0]


def test_governor_applies_conservative_spacing_between_all_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    clock = _fake_clock()
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.25,
            mutation_interval_seconds=0.0,
        ),
        state_path=tmp_path / "state.json",
        clock=clock.now,
        sleep=clock.sleep,
    )
    governor.before_request(method="GET", route="repository.read", content_generating=False)
    governor.observe_response(route="repository.read", status=200, headers={}, content_generating=False)
    governor.before_request(method="GET", route="repository.read", content_generating=False)
    assert clock.sleeps == [0.25]

def test_controller_route_telemetry_splits_major_read_families(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, github_controller_client = _load_runtime_types(tmp_path, monkeypatch)
    controller_module = sys.modules[github_controller_client.__module__]
    route = controller_module._request_route_name

    assert route("GET", "/user/repos?per_page=100") == "repository.list"
    assert route("GET", "/repos/octo/demo") == "repository.read"
    assert route("GET", "/repos/octo/demo/contents/README.md?ref=main") == "contents.read"
    assert route("GET", "/repos/octo/demo/git/ref/heads/main") == "git_ref.read"
    assert route("GET", "/repos/octo/demo/pulls?state=all") == "pull_request.list"
    assert route("GET", "/repos/octo/demo/pulls/3") == "pull_request.read"
    assert route("GET", "/repos/octo/demo/issues/4/comments") == "issue_comment.list"
    assert route("GET", "/repos/octo/demo/actions/runs?per_page=100") == "workflow_run.list"
    assert route("GET", "/repos/octo/demo/actions/runs/7/jobs") == "workflow_run.jobs"
    assert route("GET", "/repos/octo/demo/actions/jobs/8/logs") == "workflow_job.logs"


def test_api_usage_delta_includes_git_content_plane_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, _policy, _client = _load_runtime_types(tmp_path, monkeypatch)
    module = sys.modules[github_api_governor.__module__]
    delta = module.github_api_usage_delta(
        {
            "metrics": {"requests": 10},
            "routes": {},
            "credential_domains": {"controller": {"requests": 10}},
            "provider_window": {},
            "git_content_plane": {"metrics": {"pushes": 2, "file_reads": 4}},
        },
        {
            "metrics": {"requests": 13},
            "routes": {},
            "credential_domains": {
                "controller": {"requests": 12},
                "installation": {"requests": 1},
            },
            "provider_window": {},
            "git_content_plane": {"metrics": {"pushes": 5, "file_reads": 9}},
        },
    )

    assert delta["metrics"]["requests"] == 3
    assert delta["credential_domains"] == {
        "controller": {"requests": 2},
        "installation": {"requests": 1},
    }
    assert delta["git_content_plane"]["metrics"] == {
        "file_reads": 5,
        "pushes": 3,
    }


def test_governor_serializes_provider_access_across_instances(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    state = tmp_path / "state.json"
    policy = github_api_governor_policy(
        request_interval_seconds=0.0,
        mutation_interval_seconds=0.0,
    )
    first = github_api_governor(
        scope="https://api.github.com|octo",
        policy=policy,
        state_path=state,
    )
    second = github_api_governor(
        scope="https://api.github.com|octo",
        policy=policy,
        state_path=state,
    )
    acquired = threading.Event()

    def enter_second() -> None:
        with second.serialized_provider_access():
            acquired.set()

    with first.serialized_provider_access():
        worker = threading.Thread(target=enter_second)
        worker.start()
        assert acquired.wait(0.05) is False

    assert acquired.wait(1.0) is True
    worker.join(timeout=1.0)
    assert worker.is_alive() is False


def test_controller_repeated_get_uses_authenticated_conditional_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        github_api_governor,
        github_api_governor_policy,
        github_controller_client,
    ) = _load_runtime_types(tmp_path, monkeypatch)
    clock = _fake_clock()
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
        ),
        state_path=tmp_path / "state.json",
        clock=clock.now,
        sleep=clock.sleep,
    )
    calls: list[dict[str, str]] = []
    body = json.dumps(
        {
            "id": 7,
            "name": "demo",
            "full_name": "octo/demo",
            "private": True,
            "default_branch": "main",
            "has_issues": True,
            "owner": {"login": "octo"},
            "permissions": {"push": True},
        }
    ).encode("utf-8")

    def transport(method, url, headers, payload):
        del url, payload
        assert method == "GET"
        calls.append(dict(headers))
        if len(calls) == 1:
            return 200, {"ETag": '"repo-v1"'}, body
        assert headers.get("If-None-Match") == '"repo-v1"'
        return 304, {"ETag": '"repo-v1"'}, b""

    client = github_controller_client(
        "secret",
        transport=transport,
        redirect_transport=transport,
        governor=governor,
    )
    first = client.repository("octo", "demo")
    second = client.repository("octo", "demo")

    assert first == second
    assert len(calls) == 2


def test_forecast_admission_uses_provider_primary_headers_before_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    clock = _fake_clock(start=1000.0)
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
            content_requests_per_minute=60,
            content_requests_per_hour=360,
            primary_remaining_floor=100,
            primary_reset_grace_seconds=3.0,
        ),
        state_path=tmp_path / "governor.json",
        clock=clock.now,
        sleep=clock.sleep,
    )
    governor.observe_response(
        route="repository.read",
        status=200,
        headers={
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "120",
            "X-RateLimit-Used": "4880",
            "X-RateLimit-Reset": "1010",
            "X-RateLimit-Resource": "core",
        },
        content_generating=False,
        primary_domain="controller",
    )

    admission = governor.wait_for_forecast_capacity(
        forecast_content_requests=0,
        forecast_primary_requests={"controller": 50},
    )

    assert clock.sleeps == [13.0]
    assert admission["primary"]["controller"]["source"] == "provider_headers"
    assert admission["primary"]["controller"]["limit"] == 5000
    assert admission["primary"]["controller"]["blocked_before_admission"] is True
    assert admission["primary_wait_seconds"] == 13.0


def test_forecast_admission_uses_persisted_content_ledger_as_secondary_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_api_governor, github_api_governor_policy, _ = _load_runtime_types(
        tmp_path, monkeypatch
    )
    clock = _fake_clock(start=1000.0)
    governor = github_api_governor(
        scope="https://api.github.com|octo",
        policy=github_api_governor_policy(
            request_interval_seconds=0.0,
            mutation_interval_seconds=0.0,
            content_requests_per_minute=60,
            content_requests_per_hour=3,
            primary_remaining_floor=0,
        ),
        state_path=tmp_path / "governor.json",
        clock=clock.now,
        sleep=clock.sleep,
    )
    for _ in range(2):
        governor.before_request(
            method="POST",
            route="issue.create",
            content_generating=True,
        )
        governor.observe_response(
            route="issue.create",
            status=201,
            headers={},
            content_generating=True,
        )
        clock.value += 1.0

    admission = governor.wait_for_forecast_capacity(
        forecast_content_requests=2,
        forecast_primary_requests={},
    )

    assert admission["content"]["source"] == "configured_secondary_fallback"
    assert admission["content"]["hour_limit"] == 3
    assert admission["content"]["wait_seconds"] > 3500
    assert clock.sleeps[-1] > 3500
