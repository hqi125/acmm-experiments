from __future__ import annotations

from dataclasses import dataclass
import base64
import json
from pathlib import Path
import shutil

import pytest

from acmm.experiment_package import (
    compose_staged_experiment_manager_integrations,
    compose_staged_experiment_profile_integrations,
    install_experiment_package,
    load_staged_experiment_integrations,
    load_staged_experiment_runtime,
    validate_staged_package_secrets,
)
from acmm.integration_api import shared_integration_context
from acmm.secret_bindings import (
    bind_secret_file,
    experiment_secret_binding_key,
    initialize_secret_store,
    secret_binding_key,
)
from acmm_infra.common import doctor_check, doctor_report
from acmm_infra.profiles.common import default_repo_root
from acmm_infra.subjects.agent_zero.profile import load_agent_zero_profile
from acmm_infra.subjects.hermes.profile import load_hermes_profile
from acmm_infra.subjects.open_webui.profile import load_open_webui_profile


ROOT = Path(__file__).resolve().parents[2] / "github_mcp_project_workspace_v1"
EXPERIMENT_ID = "github_mcp_project_workspace_v1"
SUBJECT_TOKEN = "subject-secret-value"
CONTROLLER_TOKEN = "controller-secret-value"
EXPECTED_CATALOG_SHA256 = (
    "d1474fb4709fc2d4d18821711f098582e30a712a08f718ee89487309ba6a818d"
)
EXPECTED_REPO_DIGEST = (
    "ghcr.io/github/github-mcp-server@sha256:"
    "250bc6ce70788207608ef74cef4397230ff2e8481218da74d6093e4bd9101132"
)
EXPECTED_TOOLSETS = (
    "context",
    "repos",
    "issues",
    "pull_requests",
    "users",
    "actions",
    "git",
    "labels",
)
EXPECTED_EXCLUSIONS = (
    "actions_run_trigger",
    "create_repository",
    "delete_repository",
    "fork_repository",
    "get_team_members",
    "get_teams",
    "list_issue_fields",
    "list_issue_types",
    "ui_get",
)
EXPECTED_TOOLS = (
    "actions_get",
    "actions_list",
    "add_comment_to_pending_review",
    "add_issue_comment",
    "add_reply_to_pull_request_comment",
    "create_branch",
    "create_or_update_file",
    "create_pull_request",
    "delete_file",
    "get_commit",
    "get_file_contents",
    "get_job_logs",
    "get_label",
    "get_latest_release",
    "get_me",
    "get_release_by_tag",
    "get_repository_tree",
    "get_tag",
    "issue_read",
    "issue_write",
    "label_write",
    "list_branches",
    "list_commits",
    "list_issues",
    "list_label",
    "list_pull_requests",
    "list_releases",
    "list_repository_collaborators",
    "list_tags",
    "merge_pull_request",
    "pull_request_read",
    "pull_request_review_write",
    "push_files",
    "search_code",
    "search_commits",
    "search_issues",
    "search_pull_requests",
    "search_repositories",
    "search_users",
    "sub_issue_write",
    "update_issue_comment",
    "update_pull_request",
    "update_pull_request_branch",
)


def _install_copy(tmp_path: Path):
    source = tmp_path / "source"
    shutil.copytree(
        ROOT,
        source,
        ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"),
    )
    return install_experiment_package(source, tmp_path / "runtime-root")


def _write_secret(path: Path, value: str) -> Path:
    path.write_text(value + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _bind_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    controller: bool = True,
    subject: bool = True,
) -> None:
    bindings = tmp_path / "secret-bindings.yaml"
    monkeypatch.setenv("ACMM_SECRET_BINDINGS_FILE", str(bindings))
    monkeypatch.setenv("ACMM_SECRET_DIRECTORY", str(tmp_path / "secrets"))
    initialize_secret_store()
    if controller:
        bind_secret_file(
            experiment_secret_binding_key(EXPERIMENT_ID, "controller_access_token"),
            _write_secret(tmp_path / "controller-token", CONTROLLER_TOKEN),
        )
    if subject:
        bind_secret_file(
            secret_binding_key(EXPERIMENT_ID, "github_mcp", "access_token"),
            _write_secret(tmp_path / "subject-token", SUBJECT_TOKEN),
        )


def _compose_profile(package, infrastructure_subject: str):
    repo = default_repo_root()
    if infrastructure_subject == "hermes":
        profile = load_hermes_profile(repo)
    elif infrastructure_subject == "open-webui":
        profile = load_open_webui_profile(repo)
    elif infrastructure_subject == "agent-zero":
        profile = load_agent_zero_profile(repo)
    else:
        raise AssertionError(infrastructure_subject)

    loaded = load_staged_experiment_integrations(package)
    return compose_staged_experiment_profile_integrations(
        package,
        infrastructure_subject,
        "gpt_oss_120b_cloud_v1",
        profile,
        loaded_integrations=loaded,
    )


def test_package_declares_frozen_scientific_shape(tmp_path: Path) -> None:
    package = _install_copy(tmp_path)

    assert package.schema_version == "0.3"
    assert len(package.contract["scenarios"]) == 12
    assert package.contract["run_protocol"]["repetitions"] == 8
    assert package.runtime is not None
    assert package.runtime.api_version == "0.1"
    assert [(item.secret_id, item.required) for item in package.secrets] == [
        ("controller_access_token", True),
    ]

    integration = package.integrations[0]
    assert integration.integration_id == "github_mcp"
    assert tuple(item.secret_id for item in integration.secrets) == ("access_token",)
    assert tuple(integration.configuration["toolsets"]) == EXPECTED_TOOLSETS
    assert tuple(integration.configuration["excluded_tools"]) == EXPECTED_EXCLUSIONS
    assert tuple(integration.configuration["expected_tools"]) == EXPECTED_TOOLS
    assert integration.configuration["expected_catalog_sha256"] == EXPECTED_CATALOG_SHA256
    assert integration.configuration["local_service"]["expected_repo_digest"] == EXPECTED_REPO_DIGEST


def test_package_secret_validation_requires_both_scopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _install_copy(tmp_path)

    _bind_secrets(tmp_path, monkeypatch, controller=False, subject=True)
    with pytest.raises(ValueError, match="controller_access_token"):
        validate_staged_package_secrets(package)

    _bind_secrets(tmp_path, monkeypatch, controller=True, subject=True)
    validate_staged_package_secrets(package)


def test_staged_integration_composes_same_43_tool_surface_for_all_subjects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)

    hermes = _compose_profile(package, "hermes")
    key, value = hermes.managed_config_overrides[-1]
    assert key == "mcp_servers.github"
    server = json.loads(value)
    assert server["url"] == "http://host.docker.internal:8083"
    assert server["headers"]["Authorization"] == f"Bearer {SUBJECT_TOKEN}"
    assert "include" not in server["tools"]
    assert server["tools"]["resources"] is False
    assert server["tools"]["prompts"] is False

    open_webui = _compose_profile(package, "open-webui")
    connections = json.loads(
        dict(open_webui.managed_environment_overrides)[
            "OPEN_WEBUI_TOOL_SERVER_CONNECTIONS"
        ]
    )
    assert len(connections) == 1
    assert connections[0]["url"] == "http://host.docker.internal:8083"
    assert connections[0]["key"] == SUBJECT_TOKEN

    agent_zero = _compose_profile(package, "agent-zero")
    assert agent_zero.experiment_isolation.mcp_tool_default == "allow"
    assert agent_zero.experiment_isolation.allowed_tools == ()


def test_local_resource_uses_toolsets_and_exclusions_not_tool_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    loaded = load_staged_experiment_integrations(package)
    resource = loaded[0].integration.shared_resource
    assert resource is not None
    runner = _fake_resource_runner()
    runner.repo_digest = EXPECTED_REPO_DIGEST
    resource._runner = runner
    component = package.integrations[0]
    context = shared_integration_context(
        experiment_id=package.experiment_id,
        integration_id=component.integration_id,
        preset=component.preset,
        configuration=component.configuration,
        package_sha256=package.package_sha256,
        package_root=package.root,
        runtime_root=tmp_path / "runtime-root",
        state_root=tmp_path / "resource-state",
        secret_ids=("access_token",),
    )

    status = resource.apply(context)
    env = (context.state_root / ".env").read_text(encoding="utf-8")
    assert "ACMM_GITHUB_MCP_TOOLSETS=" + ",".join(EXPECTED_TOOLSETS) in env
    assert "ACMM_GITHUB_MCP_EXCLUDE_TOOLS=" + ",".join(EXPECTED_EXCLUSIONS) in env
    assert "ACMM_GITHUB_MCP_TOOLS=" not in env
    assert SUBJECT_TOKEN not in env
    assert status["expected_catalog_sha256"] == EXPECTED_CATALOG_SHA256
    assert status["expected_repo_digest"] == EXPECTED_REPO_DIGEST



def test_local_resource_apply_rejects_unqualified_image_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    resource = load_staged_experiment_integrations(package)[0].integration.shared_resource
    assert resource is not None
    resource._runner = _fake_resource_runner()
    component = package.integrations[0]
    context = shared_integration_context(
        experiment_id=package.experiment_id,
        integration_id=component.integration_id,
        preset=component.preset,
        configuration=component.configuration,
        package_sha256=package.package_sha256,
        package_root=package.root,
        runtime_root=tmp_path / "runtime-root",
        state_root=tmp_path / "resource-state",
        secret_ids=("access_token",),
    )

    with pytest.raises(ValueError, match="image digest mismatch"):
        resource.apply(context)

def test_shared_resource_doctor_enforces_qualified_image_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    resource = load_staged_experiment_integrations(package)[0].integration.shared_resource
    assert resource is not None
    runner = _fake_resource_runner()
    runner.container_present = True
    runner.running = True
    resource._runner = runner
    component = package.integrations[0]
    context = shared_integration_context(
        experiment_id=package.experiment_id,
        integration_id=component.integration_id,
        preset=component.preset,
        configuration=component.configuration,
        package_sha256=package.package_sha256,
        package_root=package.root,
        runtime_root=tmp_path / "runtime-root",
        state_root=tmp_path / "resource-state",
        secret_ids=("access_token",),
    )

    report = resource.doctor(context)
    assert report.is_ready is False
    assert next(item for item in report.checks if item.name == "image_digest").ok is False

    runner.repo_digest = EXPECTED_REPO_DIGEST
    report = resource.doctor(context)
    assert report.is_ready is True
    assert next(item for item in report.checks if item.name == "image_digest").ok is True


def test_manager_discovery_accepts_exact_agent_zero_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    manager = _fake_manager(
        docker=_fake_docker(running=True),
        token=SUBJECT_TOKEN,
        api=_fake_agent_zero_api(EXPECTED_TOOLS),
    )
    wrapped = compose_staged_experiment_manager_integrations(
        package,
        "agent-zero",
        "gpt_oss_120b_cloud_v1",
        manager,
        loaded_integrations=load_staged_experiment_integrations(package),
    )

    report = wrapped.doctor()
    check = report.checks[-1]
    assert report.is_ready is True
    assert check.name == "integration:github_mcp_discovery"
    assert check.ok is True
    assert "exactly 43 expected" in check.detail
    assert EXPECTED_CATALOG_SHA256 in check.detail


def test_package_source_never_contains_bound_secret_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    load_staged_experiment_integrations(package)

    for path in package.root.rglob("*"):
        if not path.is_file() or "tests" in path.relative_to(package.root).parts:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        assert SUBJECT_TOKEN not in content
        assert CONTROLLER_TOKEN not in content


@dataclass(frozen=True)
class _fake_command_result:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class _fake_resource_runner:
    def __init__(self) -> None:
        self.image_present = True
        self.container_present = False
        self.running = False
        self.repo_digest = "ghcr.io/github/github-mcp-server@sha256:wrong"

    def run(self, args, **kwargs):
        del kwargs
        call = tuple(str(value) for value in args)
        if call[:2] == ("docker", "inspect"):
            if not self.container_present:
                return _fake_command_result(returncode=1, stderr="not found")
            return _fake_command_result(
                stdout=(
                    ("true" if self.running else "false")
                    + "\tghcr.io/github/github-mcp-server:v2.0.3\n"
                )
            )
        if call[:3] == ("docker", "container", "inspect"):
            return _fake_command_result(returncode=1, stderr="not found")
        if call[:3] == ("docker", "image", "inspect"):
            if not self.image_present:
                return _fake_command_result(returncode=1, stderr="missing")
            if "--format" in call:
                return _fake_command_result(stdout=json.dumps([self.repo_digest]) + "\n")
            return _fake_command_result(stdout="{}")
        if call[:2] == ("docker", "compose"):
            return _fake_command_result()
        if call[:2] == ("docker", "--version"):
            return _fake_command_result(stdout="Docker version test")
        raise AssertionError(f"unexpected command: {call!r}")


@dataclass(frozen=True)
class _fake_profile:
    llm_baseline_id: str = "gpt_oss_120b_cloud_v1"


class _fake_manager:
    def __init__(self, *, docker: object, token: str, api: object) -> None:
        self.profile = _fake_profile()
        self.deployment_root = Path("/tmp/acmm-fake-deployment")
        self.docker = docker
        self.api = api
        self._token = token

    def apply(self, *, timeout_seconds: float = 120.0, progress=None):
        del timeout_seconds, progress
        return {"credential": self._token}

    def status(self):
        return {"credential": self._token}

    def doctor(self):
        return doctor_report(checks=(doctor_check("base", True, "ready"),))

    def up(self, *, timeout_seconds: float = 120.0) -> None:
        del timeout_seconds

    def down(self) -> None:
        return None


class _fake_docker:
    def __init__(self, *, running: bool) -> None:
        self._running = running

    def container_running(self) -> bool:
        return self._running


class _fake_agent_zero_api:
    def __init__(self, tools: tuple[str, ...]) -> None:
        self._tools = tools

    def _request_json(self, method: str, path: str, *, payload):
        assert (method, path, payload) == (
            "POST",
            "/api/mcp_server_get_detail",
            {"server_name": "github"},
        )
        return {
            "success": True,
            "detail": {
                "connected": True,
                "tools": [{"name": tool} for tool in self._tools],
            },
        }


def test_runtime_declares_controller_diagnostic_and_all_frozen_fixture_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)

    loaded = load_staged_experiment_runtime(package)

    assert set(loaded.runtime.diagnostics) == {"github_fixture_controller"}
    assert set(loaded.runtime.apparatus_actions) == {"initialize"}
    assert set(loaded.runtime.evaluators) == {"github_workspace"}
    assert set(loaded.runtime.fixtures) == {
        "github_workspace_f1_a",
        "github_workspace_f1_b",
        "github_workspace_f2_a",
        "github_workspace_f2_b",
        "github_workspace_f3_a",
        "github_workspace_f3_b",
        "github_workspace_f4_a",
        "github_workspace_f4_b",
        "github_workspace_f5_a",
        "github_workspace_f5_b",
        "github_workspace_f6_a",
        "github_workspace_f6_b",
    }


def test_controller_diagnostic_checks_repository_identity_and_read_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    loaded = load_staged_experiment_runtime(package)
    diagnostic = loaded.runtime.diagnostics["github_fixture_controller"]
    diagnostic._client._transport = _fake_controller_transport()

    report = diagnostic.doctor()

    assert report.is_ready
    checks = {item.name: item for item in report.checks}
    assert checks["credential_separation"].ok
    assert checks["controller_identity"].detail == "authenticated as fixture-owner"
    assert checks["repository_identity"].detail == (
        "resolved pinned repository Dufferin125/acmm-mcp-arena-experiment-2 "
        "(repository id=1447536932)"
    )
    assert checks["repository_private"].ok
    assert checks["issues_enabled"].ok
    assert checks["controller_push_access"].ok
    assert checks["repository_default_branch"].ok
    assert checks["repository_initialized"].ok
    assert checks["default_branch_read"].ok
    assert checks["repository_contents_read"].ok
    assert checks["fixture_base_integrity"].ok
    assert checks["issues_read"].ok
    assert checks["pull_requests_read"].ok
    assert checks["actions_workflows_read"].ok
    assert checks["actions_runs_read"].ok


def test_controller_diagnostic_rejects_same_named_repository_with_wrong_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    loaded = load_staged_experiment_runtime(package)
    diagnostic = loaded.runtime.diagnostics["github_fixture_controller"]
    diagnostic._client._transport = _fake_controller_transport(
        repository_id=999999,
    )

    report = diagnostic.doctor()

    assert report.is_ready is False
    checks = {item.name: item for item in report.checks}
    assert checks["repository_identity"].ok is False
    assert "expected Dufferin125/acmm-mcp-arena-experiment-2" in (
        checks["repository_identity"].detail
    )
    assert "repository_initialized" not in checks



def test_controller_diagnostic_reports_empty_repository_as_initialization_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    loaded = load_staged_experiment_runtime(package)
    diagnostic = loaded.runtime.diagnostics["github_fixture_controller"]
    diagnostic._client._transport = _empty_repository_transport()

    report = diagnostic.doctor()

    assert report.is_ready is False
    checks = {item.name: item for item in report.checks}
    assert checks["repository_identity"].ok
    assert checks["repository_default_branch"].ok
    assert checks["repository_initialized"].ok is False
    assert checks["repository_initialized"].detail == (
        "repository is empty; initialize the trusted fixture base "
        "before scientific execution"
    )
    assert "default_branch_read" not in checks
    assert "repository_contents_read" not in checks
    assert checks["issues_read"].ok
    assert checks["pull_requests_read"].ok
    assert checks["actions_workflows_read"].ok
    assert checks["actions_runs_read"].ok



def test_controller_client_mutation_primitives_are_namespaced_and_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    loaded = load_staged_experiment_runtime(package)
    diagnostic = loaded.runtime.diagnostics["github_fixture_controller"]
    recorder = _fake_controller_transport()
    diagnostic._client._transport = recorder
    client = diagnostic._client

    created = client.create_ref(
        "fixture-owner",
        "acmm-mcp-arena-experiment-2",
        "acmm/execution/f1-a/repair",
        "abc123",
    )
    assert created["ref"] == "refs/heads/acmm/execution/f1-a/repair"
    client.update_ref(
        "fixture-owner",
        "acmm-mcp-arena-experiment-2",
        "acmm/execution/f1-a/repair",
        "def456",
    )
    client.delete_ref(
        "fixture-owner",
        "acmm-mcp-arena-experiment-2",
        "acmm/execution/f1-a/repair",
    )
    issue = client.create_issue(
        "fixture-owner",
        "acmm-mcp-arena-experiment-2",
        title="fixture issue",
        body="[acmm-fixture]",
        labels=("fixture",),
    )
    assert issue["number"] == 17
    pull = client.create_pull_request(
        "fixture-owner",
        "acmm-mcp-arena-experiment-2",
        title="fixture PR",
        head="acmm/execution/f1-a/repair",
        base="main",
        body="[acmm-fixture]",
    )
    assert pull["number"] == 23

    assert recorder.methods == ["POST", "PATCH", "DELETE", "POST", "POST"]


class _empty_repository_transport:
    repository_id = 1447536932
    repository_full_name = "Dufferin125/acmm-mcp-arena-experiment-2"

    def __call__(self, method, url, headers, payload):
        from urllib.parse import urlparse

        del headers, payload
        parsed = urlparse(url)
        path = parsed.path

        if method == "GET" and path == "/user":
            body = {"login": "fixture-owner"}
            return 200, {}, json.dumps(body).encode("utf-8")
        if method == "GET" and path == "/user/repos":
            body = [
                {
                    "id": self.repository_id,
                    "name": "acmm-mcp-arena-experiment-2",
                    "full_name": self.repository_full_name,
                    "private": True,
                    "default_branch": "main",
                    "has_issues": True,
                    "owner": {"login": "Dufferin125"},
                    "permissions": {"push": True},
                }
            ]
            return 200, {}, json.dumps(body).encode("utf-8")
        if method == "GET" and "/git/ref/heads/main" in path:
            return (
                409,
                {},
                json.dumps({"message": "Git Repository is empty."}).encode("utf-8"),
            )
        if method == "GET" and path.endswith("/issues"):
            body = []
        elif method == "GET" and path.endswith("/pulls"):
            body = []
        elif method == "GET" and path.endswith("/actions/workflows"):
            body = {"total_count": 0, "workflows": []}
        elif method == "GET" and path.endswith("/actions/runs"):
            body = {"total_count": 0, "workflow_runs": []}
        else:
            raise AssertionError(f"unexpected request: {method} {url}")
        return 200, {}, json.dumps(body).encode("utf-8")



class _initializable_empty_repository_transport:
    repository_id = 1447536932
    repository_full_name = "Dufferin125/acmm-mcp-arena-experiment-2"

    def __init__(self) -> None:
        self.initialized = False
        self.files: dict[str, str] = {}
        self.head_sha = "fixture-head-0"
        self.put_paths: list[str] = []

    def __call__(self, method, url, headers, payload):
        from urllib.parse import urlparse

        del headers
        parsed = urlparse(url)
        path = parsed.path

        if method == "GET" and path == "/user":
            return 200, {}, json.dumps({"login": "fixture-owner"}).encode("utf-8")
        if method == "GET" and path == "/user/repos":
            body = [{
                "id": self.repository_id,
                "name": "acmm-mcp-arena-experiment-2",
                "full_name": self.repository_full_name,
                "private": True,
                "default_branch": "main",
                "has_issues": True,
                "owner": {"login": "Dufferin125"},
                "permissions": {"push": True},
            }]
            return 200, {}, json.dumps(body).encode("utf-8")
        if method == "GET" and "/git/ref/heads/main" in path:
            if not self.initialized:
                return 409, {}, json.dumps({"message": "Git Repository is empty."}).encode("utf-8")
            body = {"ref": "refs/heads/main", "object": {"sha": self.head_sha}}
            return 200, {}, json.dumps(body).encode("utf-8")
        if method == "GET" and path.endswith("/issues"):
            return 200, {}, b"[]"
        if method == "GET" and path.endswith("/pulls"):
            return 200, {}, b"[]"
        if method == "GET" and path.endswith("/actions/workflows"):
            return 200, {}, json.dumps({"total_count": 0, "workflows": []}).encode("utf-8")
        if method == "GET" and path.endswith("/actions/runs"):
            return 200, {}, json.dumps({"total_count": 0, "workflow_runs": []}).encode("utf-8")
        if method == "GET" and path.endswith("/contents"):
            if not self.initialized:
                return 404, {}, json.dumps({"message": "This repository is empty."}).encode("utf-8")
            body = [{"name": key.rsplit("/", 1)[-1], "path": key, "type": "file"} for key in sorted(self.files)]
            return 200, {}, json.dumps(body).encode("utf-8")
        if method == "GET" and "/contents/" in path:
            relative = path.split("/contents/", 1)[1]
            if relative not in self.files:
                return 404, {}, json.dumps({"message": "Not Found"}).encode("utf-8")
            content = self.files[relative]
            body = {
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            }
            return 200, {}, json.dumps(body).encode("utf-8")
        if method == "PUT" and "/contents/" in path:
            value = json.loads(payload.decode("utf-8"))
            relative = path.split("/contents/", 1)[1]
            self.files[relative] = base64.b64decode(value["content"]).decode("utf-8")
            self.initialized = True
            self.head_sha = f"fixture-head-{len(self.files)}"
            self.put_paths.append(path)
            body = {
                "content": {"path": relative, "sha": f"blob-{len(self.files)}"},
                "commit": {"sha": self.head_sha},
            }
            return 201, {}, json.dumps(body).encode("utf-8")
        raise AssertionError(f"unexpected request: {method} {url}")


class _fake_controller_transport:
    def __init__(
        self,
        *,
        repository_id: int = 1447536932,
        repository_full_name: str = "Dufferin125/acmm-mcp-arena-experiment-2",
        fixture_base_valid: bool = True,
    ) -> None:
        self.methods: list[str] = []
        self.repository_id = repository_id
        self.repository_full_name = repository_full_name
        self.fixture_base_valid = fixture_base_valid

    def __call__(self, method, url, headers, payload):
        from urllib.parse import urlparse

        del headers
        self.methods.append(method)
        parsed = urlparse(url)
        path = parsed.path
        body = {}
        status = 200

        if method == "GET" and path == "/user":
            body = {"login": "fixture-owner"}
        elif method == "GET" and path == "/user/repos":
            body = [
                {
                    "id": self.repository_id,
                    "name": "acmm-mcp-arena-experiment-2",
                    "full_name": self.repository_full_name,
                    "private": True,
                    "default_branch": "main",
                    "has_issues": True,
                    "owner": {"login": "Dufferin125"},
                    "permissions": {"push": True},
                }
            ]
        elif method == "GET" and "/git/ref/heads/main" in path:
            body = {"ref": "refs/heads/main", "object": {"sha": "abc123"}}
        elif method == "GET" and path.endswith("/contents"):
            body = [{"name": "README.md", "type": "file"}]
        elif method == "GET" and "/contents/" in path:
            relative = path.split("/contents/", 1)[1]
            fixture_path = ROOT / "assets" / "fixture_base" / (
                "fixture-base.json" if relative == ".acmm/fixture-base.json" else "README.md"
            )
            content = fixture_path.read_text(encoding="utf-8")
            if not self.fixture_base_valid and relative == ".acmm/fixture-base.json":
                content = content.replace('"fixture_base_version": "0.1"', '"fixture_base_version": "broken"')
            body = {
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            }
        elif method == "GET" and path.endswith("/issues"):
            body = []
        elif method == "GET" and path.endswith("/pulls"):
            body = []
        elif method == "GET" and path.endswith("/actions/workflows"):
            body = {"total_count": 0, "workflows": []}
        elif method == "GET" and path.endswith("/actions/runs"):
            body = {"total_count": 0, "workflow_runs": []}
        elif method == "POST" and path.endswith("/git/refs"):
            status = 201
            value = json.loads(payload.decode("utf-8"))
            body = {"ref": value["ref"], "object": {"sha": value["sha"]}}
        elif method == "PATCH" and "/git/refs/heads/" in path:
            body = {"ref": "refs/heads/acmm/execution/f1-a/repair"}
        elif method == "DELETE" and "/git/refs/heads/" in path:
            return 204, {}, b""
        elif method == "POST" and path.endswith("/issues"):
            status = 201
            body = {"number": 17}
        elif method == "POST" and path.endswith("/pulls"):
            status = 201
            body = {"number": 23}
        else:
            raise AssertionError(f"unexpected request: {method} {url}")

        return status, {}, json.dumps(body).encode("utf-8")



def test_fixture_base_initializer_materializes_empty_repository_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    loaded = load_staged_experiment_runtime(package)
    diagnostic = loaded.runtime.diagnostics["github_fixture_controller"]
    action = loaded.runtime.apparatus_actions["initialize"]
    transport = _initializable_empty_repository_transport()
    diagnostic._client._transport = transport

    first = action.run()
    assert first.changed is True
    assert first.observations["repository_id"] == 1447536932
    assert first.observations["default_branch"] == "main"
    assert first.observations["fixture_base_version"] == "0.1"
    assert first.observations["head_sha"] == "fixture-head-2"
    assert transport.put_paths == [
        "/repos/Dufferin125/acmm-mcp-arena-experiment-2/contents/README.md",
        "/repos/Dufferin125/acmm-mcp-arena-experiment-2/contents/.acmm/fixture-base.json",
    ]

    second = action.run()
    assert second.changed is False
    assert second.observations["head_sha"] == "fixture-head-2"
    assert len(transport.put_paths) == 2

    report = diagnostic.doctor()
    assert report.is_ready
    checks = {item.name: item for item in report.checks}
    assert checks["fixture_base_integrity"].ok


def test_fixture_base_initializer_refuses_untrusted_nonempty_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    loaded = load_staged_experiment_runtime(package)
    diagnostic = loaded.runtime.diagnostics["github_fixture_controller"]
    action = loaded.runtime.apparatus_actions["initialize"]
    transport = _fake_controller_transport(fixture_base_valid=False)
    diagnostic._client._transport = transport

    with pytest.raises(RuntimeError, match="Trusted fixture base file"):
        action.run()
    assert "PUT" not in transport.methods


def test_fixture_namespace_is_execution_scoped_and_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    _bind_secrets(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    loaded = load_staged_experiment_runtime(package)
    diagnostic = loaded.runtime.diagnostics["github_fixture_controller"]
    controller_module = sys.modules[type(diagnostic._client).__module__]

    namespace = controller_module.github_fixture_namespace(
        execution_id="Execution 123",
        scenario_id="f1_a_regression_disposition",
    )

    assert namespace.branch("Repair Head") == (
        "acmm/execution-123/f1-a-regression-disposition/repair-head"
    )
    assert namespace.marker("acmm-fixture") == (
        "[acmm-fixture:execution=Execution 123;"
        "scenario=f1_a_regression_disposition]"
    )
