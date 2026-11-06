from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil

import pytest

from acmm.experiment_package import (
    compose_staged_experiment_profile_integrations,
    compose_staged_experiment_manager_integrations,
    install_experiment_package,
    load_staged_experiment_integrations,
)
from acmm.secret_bindings import bind_secret_file, secret_binding_key
from acmm.integration_api import shared_integration_context
from acmm_infra.common import doctor_check, doctor_report
from acmm_infra.subjects.agent_zero.profile import load_agent_zero_profile
from acmm_infra.profiles.common import default_repo_root
from acmm_infra.subjects.hermes.profile import load_hermes_profile
from acmm_infra.subjects.open_webui.profile import load_open_webui_profile


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "github_mcp_integration_qualification_v1"
TOKEN = "qualification-" + "secret-" + "value"
EXPECTED_TOOLS = ("issue_read", "issue_write", "add_issue_comment")


def _install_copy(tmp_path: Path):
    source = tmp_path / "source"
    shutil.copytree(
        ROOT,
        source,
        ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"),
    )
    return install_experiment_package(
        source,
        tmp_path / "runtime-root",
    )


def _bind_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = tmp_path / "github-token"
    secret.write_text(TOKEN + "\n", encoding="utf-8")
    secret.chmod(0o600)
    bindings = tmp_path / "secret-bindings.yaml"
    monkeypatch.setenv("ACMM_SECRET_BINDINGS_FILE", str(bindings))
    bind_secret_file(
        secret_binding_key(EXPERIMENT_ID, "github_mcp", "access_token"),
        secret,
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


def test_staged_integration_composes_native_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_token(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)

    hermes = _compose_profile(package, "hermes")
    key, value = hermes.managed_config_overrides[-1]
    assert key == "mcp_servers.github"
    server = json.loads(value)
    assert server["url"] == "http://host.docker.internal:8082"
    assert server["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert tuple(server["tools"]["include"]) == EXPECTED_TOOLS
    assert server["tools"]["resources"] is False
    assert server["tools"]["prompts"] is False

    open_webui = _compose_profile(package, "open-webui")
    assert open_webui.experiment_isolation.external_tool_servers_enabled is True
    env = dict(open_webui.managed_environment_overrides)
    connections = json.loads(env["OPEN_WEBUI_TOOL_SERVER_CONNECTIONS"])
    assert len(connections) == 1
    connection = connections[0]
    assert connection["type"] == "mcp"
    assert connection["auth_type"] == "bearer"
    assert connection["key"] == TOKEN
    assert connection["info"]["id"] == "github"
    persistent = dict(open_webui.managed_config_overrides)
    assert persistent["tool_server.connections"] == [connection]

    agent_zero = _compose_profile(package, "agent-zero")
    env = dict(agent_zero.managed_environment_overrides)
    settings = dict(agent_zero.managed_settings_overrides)
    assert env["AGENT_ZERO_MCP_SERVERS"] == settings["mcp_servers"]
    servers = json.loads(env["AGENT_ZERO_MCP_SERVERS"])
    github = servers["mcpServers"]["github"]
    assert github["type"] == "streamable-http"
    assert github["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert agent_zero.experiment_isolation.mcp_tool_default == "block"
    for tool in EXPECTED_TOOLS:
        assert f"mcp:github:{tool}" in agent_zero.experiment_isolation.allowed_tools


def test_integration_requires_external_credential(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACMM_SECRET_BINDINGS_FILE", str(tmp_path / "missing.yaml"))
    package = _install_copy(tmp_path)

    with pytest.raises(ValueError, match="No local secret binding"):
        _compose_profile(package, "hermes")


def test_package_source_never_contains_credential_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_token(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    load_staged_experiment_integrations(package)

    for path in package.root.rglob("*"):
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        assert TOKEN not in content


def test_manager_wrapper_redacts_secret_from_returned_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_token(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    loaded = load_staged_experiment_integrations(package)
    docker = _fake_docker(running=False)
    manager = _fake_manager(docker=docker, token=TOKEN)

    wrapped = compose_staged_experiment_manager_integrations(
        package,
        "hermes",
        "gpt_oss_120b_cloud_v1",
        manager,
        loaded_integrations=loaded,
    )

    assert wrapped.deployment_root == manager.deployment_root
    assert wrapped.docker is manager.docker
    messages = []
    assert TOKEN not in repr(wrapped.apply(progress=messages.append))
    assert "<redacted>" in repr(wrapped.apply())
    assert messages == ["configured credential=<redacted>"]
    assert TOKEN not in repr(wrapped.status())
    report = wrapped.doctor()
    assert TOKEN not in repr(report)
    assert report.checks[-1].name == "integration:github_mcp_discovery"
    assert report.checks[-1].ok is False
    assert "runtime is stopped" in report.checks[-1].detail


def test_manager_wrapper_uses_agent_zero_native_detail_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_token(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    loaded = load_staged_experiment_integrations(package)
    api = _fake_agent_zero_api(EXPECTED_TOOLS)
    manager = _fake_manager(
        docker=_fake_docker(running=True),
        token=TOKEN,
        api=api,
    )

    wrapped = compose_staged_experiment_manager_integrations(
        package,
        "agent-zero",
        "gpt_oss_120b_cloud_v1",
        manager,
        loaded_integrations=loaded,
    )
    report = wrapped.doctor()

    assert report.is_ready is True
    assert api.calls == [
        (
            "POST",
            "/api/mcp_server_get_detail",
            {"server_name": "github"},
        )
    ]
    assert report.checks[-1].ok is True



def test_manager_wrapper_verifies_hermes_exact_tool_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_token(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    output = (
        "Testing 'github'...\n"
        "Connected (12ms)\n"
        "Tools discovered: 3\n\n"
        "  issue_read  Read issue\n"
        "  issue_write  Write issue\n"
        "  add_issue_comment  Add comment\n"
    )
    manager = _fake_manager(
        docker=_fake_docker(
            running=True,
            exec_result=_fake_command_result(stdout=output),
        ),
        token=TOKEN,
    )

    wrapped = compose_staged_experiment_manager_integrations(
        package,
        "hermes",
        "gpt_oss_120b_cloud_v1",
        manager,
        loaded_integrations=load_staged_experiment_integrations(package),
    )
    report = wrapped.doctor()

    assert report.is_ready is True
    assert report.checks[-1].name == "integration:github_mcp_discovery"
    assert report.checks[-1].ok is True
    assert "exactly 3 expected" in report.checks[-1].detail


def test_manager_wrapper_rejects_hermes_wrong_tool_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_token(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    output = (
        "Testing 'github'...\n"
        "Connected (12ms)\n"
        "Tools discovered: 2\n\n"
        "  issue_read  Read issue\n"
        "  issue_write  Write issue\n"
    )
    manager = _fake_manager(
        docker=_fake_docker(
            running=True,
            exec_result=_fake_command_result(stdout=output),
        ),
        token=TOKEN,
    )

    wrapped = compose_staged_experiment_manager_integrations(
        package,
        "hermes",
        "gpt_oss_120b_cloud_v1",
        manager,
        loaded_integrations=load_staged_experiment_integrations(package),
    )
    report = wrapped.doctor()

    assert report.is_ready is False
    assert report.checks[-1].ok is False
    assert "reported count 2" in report.checks[-1].detail



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
        self.container_present = True
        self.running = False
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, **kwargs):
        del kwargs
        call = tuple(str(value) for value in args)
        self.calls.append(call)

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
            if self.container_present:
                return _fake_command_result(stdout="{}")
            return _fake_command_result(returncode=1, stderr="not found")
        if call[:3] == ("docker", "rm", "-f"):
            self.container_present = False
            self.running = False
            return _fake_command_result()
        if call[:3] == ("docker", "image", "inspect"):
            if not self.image_present:
                return _fake_command_result(returncode=1, stderr="missing")
            if "--format" in call:
                return _fake_command_result(
                    stdout=(
                        '["ghcr.io/github/github-mcp-server@sha256:testdigest"]\n'
                    )
                )
            return _fake_command_result(stdout="{}")
        if call[:2] == ("docker", "compose"):
            if "up" in call:
                self.container_present = True
                self.running = True
            elif "down" in call:
                self.container_present = False
                self.running = False
            return _fake_command_result()
        if call[:2] == ("docker", "--version"):
            return _fake_command_result(stdout="Docker version test")
        raise AssertionError(f"unexpected command: {call!r}")

def test_local_shared_resource_uses_ephemeral_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_token(tmp_path, monkeypatch)
    package = _install_copy(tmp_path)
    loaded = load_staged_experiment_integrations(package)
    resource = loaded[0].integration.shared_resource
    assert resource is not None

    runner = _fake_resource_runner()
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
    assert status["image_present"] is True
    assert status["container_present"] is False
    assert status["running"] is False

    resource.up(context)
    assert resource.status(context)["container_present"] is True
    assert resource.status(context)["running"] is True

    resource.down(context)
    final = resource.status(context)
    assert final["container_present"] is False
    assert final["running"] is False

    commands = [" ".join(call) for call in runner.calls]
    assert any("config --quiet" in command for command in commands)
    assert any("down --remove-orphans" in command for command in commands)
    assert not any(" create " in f" {command} " for command in commands)
    assert not any(" stop " in f" {command} " for command in commands)


@dataclass(frozen=True)
class _fake_profile:
    llm_baseline_id: str = "gpt_oss_120b_cloud_v1"


class _fake_manager:
    def __init__(
        self,
        *,
        docker: "_fake_docker",
        token: str,
        api: object | None = None,
    ) -> None:
        self.profile = _fake_profile()
        self.deployment_root = Path("/tmp/acmm-fake-deployment")
        self.docker = docker
        self.api = api
        self._token = token

    def apply(self, *, timeout_seconds: float = 120.0, progress=None):
        del timeout_seconds
        if progress is not None:
            progress(f"configured credential={self._token}")
        return {"secret": self._token, "nested": [f"Bearer {self._token}"]}

    def status(self):
        return {"connection": f"Authorization: Bearer {self._token}"}

    def doctor(self):
        return doctor_report(
            checks=(doctor_check("base", True, f"credential={self._token}"),)
        )

    def up(self, *, timeout_seconds: float = 120.0) -> None:
        del timeout_seconds

    def down(self) -> None:
        return None


class _fake_docker:
    def __init__(
        self,
        *,
        running: bool,
        exec_result: _fake_command_result | None = None,
    ) -> None:
        self._running = running
        self._exec_result = exec_result

    def container_running(self) -> bool:
        return self._running

    def exec(self, args):
        del args
        if self._exec_result is None:
            raise AssertionError("unexpected docker exec")
        return self._exec_result


class _fake_agent_zero_api:
    def __init__(self, tools: tuple[str, ...]) -> None:
        self._tools = tools
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def _request_json(self, method: str, path: str, *, payload):
        self.calls.append((method, path, payload))
        return {
            "success": True,
            "detail": {
                "connected": True,
                "tools": [{"name": tool} for tool in self._tools],
            },
        }
