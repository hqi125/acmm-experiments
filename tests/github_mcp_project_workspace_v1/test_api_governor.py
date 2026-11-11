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
    secret_binding_key,
)


ROOT = Path(__file__).resolve().parents[2] / "github_mcp_project_workspace_v1"
EXPERIMENT_ID = "github_mcp_project_workspace_v1"
CONTROLLER_TOKEN = "controller-secret-value"
SUBJECT_TOKEN = "subject-secret-value"


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
        secret_binding_key(EXPERIMENT_ID, "github_mcp", "access_token"),
        _write_secret(tmp_path / "subject-token", SUBJECT_TOKEN),
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
        mutation_interval_seconds=0.0,
        content_requests_per_minute=10,
        content_requests_per_hour=2,
        max_secondary_retries=1,
        secondary_backoff_seconds=(5.0,),
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
            mutation_interval_seconds=0.0,
            content_requests_per_minute=1,
            content_requests_per_hour=1,
            max_secondary_retries=0,
            secondary_backoff_seconds=(5.0,),
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
            mutation_interval_seconds=0.0,
            content_requests_per_minute=5,
            content_requests_per_hour=5,
            max_secondary_retries=0,
            secondary_backoff_seconds=(5.0,),
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


def test_governor_preserves_primary_headroom_for_same_owner_subject_traffic(
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
            mutation_interval_seconds=0.0,
            content_requests_per_minute=60,
            content_requests_per_hour=360,
            primary_remaining_floor=1000,
            primary_reset_grace_seconds=2.0,
            max_secondary_retries=0,
            secondary_backoff_seconds=(5.0,),
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
            "provider_window": {},
            "git_content_plane": {"metrics": {"pushes": 2, "file_reads": 4}},
        },
        {
            "metrics": {"requests": 13},
            "routes": {},
            "provider_window": {},
            "git_content_plane": {"metrics": {"pushes": 5, "file_reads": 9}},
        },
    )

    assert delta["metrics"]["requests"] == 3
    assert delta["git_content_plane"]["metrics"] == {
        "file_reads": 5,
        "pushes": 3,
    }
