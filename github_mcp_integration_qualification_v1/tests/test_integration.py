from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil

import pytest

from acmm.experiment_package import (
    compose_staged_experiment_integrations,
    compose_staged_experiment_manager_integrations,
    install_experiment_package,
    load_staged_experiment_integrations,
)
from acmm_infra.common import doctor_check, doctor_report
from acmm_infra.profiles.agent_zero import load_agent_zero_profile
from acmm_infra.profiles.common import default_repo_root
from acmm_infra.profiles.hermes import load_hermes_profile
from acmm_infra.profiles.open_webui import load_open_webui_profile


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "github_mcp_integration_qualification_v1"
TOKEN_ENV = "ACMM_GITHUB_MCP_TOKEN"
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
    return compose_staged_experiment_integrations(
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
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    package = _install_copy(tmp_path)

    hermes = _compose_profile(package, "hermes")
    key, value = hermes.managed_config_overrides[-1]
    assert key == "mcp_servers.github"
    server = json.loads(value)
    assert server["url"] == "https://api.githubcopilot.com/mcp/"
    assert server["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert server["headers"]["X-MCP-Tools"] == ",".join(EXPECTED_TOOLS)
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
    assert connection["headers"]["X-MCP-Tools"] == ",".join(EXPECTED_TOOLS)
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
    assert github["headers"]["X-MCP-Tools"] == ",".join(EXPECTED_TOOLS)
    assert agent_zero.experiment_isolation.mcp_tool_default == "block"
    for tool in EXPECTED_TOOLS:
        assert f"mcp:github:{tool}" in agent_zero.experiment_isolation.allowed_tools


def test_integration_requires_external_credential(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    package = _install_copy(tmp_path)

    with pytest.raises(ValueError, match=TOKEN_ENV):
        _compose_profile(package, "hermes")


def test_package_source_never_contains_credential_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
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
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
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
    assert TOKEN not in repr(wrapped.apply())
    assert "<redacted>" in repr(wrapped.apply())
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
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
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
        del timeout_seconds, progress
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
    def __init__(self, *, running: bool) -> None:
        self._running = running

    def container_running(self) -> bool:
        return self._running

    def exec(self, args):
        del args
        raise AssertionError("unexpected docker exec")


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
