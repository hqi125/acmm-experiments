from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
import json
import os
import re
from typing import Any, Mapping

from acmm.integration_api import (
    experiment_integration,
    experiment_integration_context,
    subject_integration,
    subject_integration_context,
)
from acmm_infra.common import doctor_check, doctor_report


_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_SERVER_ID = re.compile(r"^[a-z0-9_]+$")
_REDACTED = "<redacted>"


def build_integration(
    context: experiment_integration_context,
) -> experiment_integration:
    settings = _settings(context.configuration)
    profile = _github_mcp_profile_integration(settings)
    manager = _github_mcp_manager_integration(settings)

    return experiment_integration(
        subjects={
            "hermes": subject_integration(profile=profile, manager=manager),
            "open-webui": subject_integration(profile=profile, manager=manager),
            "agent-zero": subject_integration(profile=profile, manager=manager),
        }
    )


class _github_mcp_profile_integration:
    def __init__(self, settings: "_integration_settings") -> None:
        self._settings = settings

    def compose_profile(
        self,
        context: subject_integration_context,
        profile: object,
    ) -> object:
        token = _credential(self._settings)

        if context.infrastructure_subject == "hermes":
            return self._hermes(profile, token)
        if context.infrastructure_subject == "open-webui":
            return self._open_webui(profile, token)
        if context.infrastructure_subject == "agent-zero":
            return self._agent_zero(profile, token)

        raise ValueError(
            "GitHub MCP qualification integration does not support infrastructure "
            f"subject '{context.infrastructure_subject}'."
        )

    def _hermes(self, profile: object, token: str) -> object:
        key = f"mcp_servers.{self._settings.server_id}"
        value = json.dumps(
            {
                "url": self._settings.endpoint,
                "headers": _headers(token, self._settings.tools),
                "enabled": True,
                "timeout": 120,
                "connect_timeout": 30,
                "supports_parallel_tool_calls": False,
                "tools": {
                    "include": list(self._settings.tools),
                    "resources": False,
                    "prompts": False,
                },
            },
            separators=(",", ":"),
        )
        overrides = tuple(getattr(profile, "managed_config_overrides", ()))
        return replace(
            profile,
            managed_config_overrides=_append_unique_pair(overrides, key, value),
        )

    def _open_webui(self, profile: object, token: str) -> object:
        isolation = getattr(profile, "experiment_isolation")
        isolation = replace(isolation, external_tool_servers_enabled=True)
        connection = _open_webui_connection(self._settings, token)
        environment = tuple(getattr(profile, "managed_environment_overrides", ()))
        environment = _append_unique_pair(
            environment,
            "OPEN_WEBUI_TOOL_SERVER_CONNECTIONS",
            json.dumps([connection], separators=(",", ":")),
        )
        config = tuple(getattr(profile, "managed_config_overrides", ()))
        config = _append_unique_pair(
            config,
            "tool_server.connections",
            [connection],
        )
        return replace(
            profile,
            experiment_isolation=isolation,
            managed_environment_overrides=environment,
            managed_config_overrides=config,
        )

    def _agent_zero(self, profile: object, token: str) -> object:
        isolation = getattr(profile, "experiment_isolation")
        allowed = tuple(isolation.allowed_tools)
        expected = tuple(
            f"mcp:{self._settings.server_id}:{tool}" for tool in self._settings.tools
        )
        isolation = replace(
            isolation,
            mcp_tool_default="block",
            allowed_tools=_append_unique_values(allowed, expected),
        )
        mcp_servers = json.dumps(
            {
                "mcpServers": {
                    self._settings.server_id: {
                        "type": "streamable-http",
                        "url": self._settings.endpoint,
                        "headers": _headers(token, self._settings.tools),
                        "init_timeout": 60,
                        "tool_timeout": 120,
                        "verify": True,
                    }
                }
            },
            separators=(",", ":"),
        )
        environment = tuple(getattr(profile, "managed_environment_overrides", ()))
        environment = _append_unique_pair(
            environment,
            "AGENT_ZERO_MCP_SERVERS",
            mcp_servers,
        )
        settings = tuple(getattr(profile, "managed_settings_overrides", ()))
        settings = _append_unique_pair(settings, "mcp_servers", mcp_servers)
        return replace(
            profile,
            experiment_isolation=isolation,
            managed_environment_overrides=environment,
            managed_settings_overrides=settings,
        )


class _github_mcp_manager_integration:
    def __init__(self, settings: "_integration_settings") -> None:
        self._settings = settings

    def compose_manager(
        self,
        context: subject_integration_context,
        manager: object,
    ) -> object:
        token = _credential(self._settings)
        return _redacting_qualification_manager(
            manager=manager,
            infrastructure_subject=context.infrastructure_subject,
            settings=self._settings,
            token=token,
        )


class _redacting_qualification_manager:
    def __init__(
        self,
        *,
        manager: object,
        infrastructure_subject: str,
        settings: "_integration_settings",
        token: str,
    ) -> None:
        self._manager = manager
        self._infrastructure_subject = infrastructure_subject
        self._settings = settings
        self._token = token
        self.profile = getattr(manager, "profile")
        self.deployment_root = getattr(manager, "deployment_root")
        self.docker = getattr(manager, "docker")

    def __getattr__(self, name: str) -> object:
        return getattr(self._manager, name)

    def apply(self, *, timeout_seconds: float = 120.0, progress=None):
        value = self._manager.apply(
            timeout_seconds=timeout_seconds,
            progress=progress,
        )
        return _redact(value, self._token)

    def status(self):
        return _redact(self._manager.status(), self._token)

    def doctor(self):
        base = self._manager.doctor()
        qualification = self._qualification_check()
        report = doctor_report(checks=tuple(base.checks) + (qualification,))
        return _redact(report, self._token)

    def up(self, *, timeout_seconds: float = 120.0) -> None:
        self._manager.up(timeout_seconds=timeout_seconds)

    def down(self) -> None:
        self._manager.down()

    def _qualification_check(self) -> doctor_check:
        if not self.docker.container_running():
            return doctor_check(
                "integration:github_mcp_discovery",
                False,
                "runtime is stopped; native MCP discovery was not attempted",
            )

        try:
            if self._infrastructure_subject == "hermes":
                ok, detail = self._probe_hermes()
            elif self._infrastructure_subject == "open-webui":
                ok, detail = self._probe_open_webui()
            elif self._infrastructure_subject == "agent-zero":
                ok, detail = self._probe_agent_zero()
            else:
                ok = False
                detail = (
                    "unsupported infrastructure subject: "
                    + self._infrastructure_subject
                )
        except Exception as exc:
            ok = False
            detail = f"native discovery probe failed: {exc}"

        return doctor_check(
            "integration:github_mcp_discovery",
            ok,
            str(_redact(detail, self._token)),
        )

    def _probe_hermes(self) -> tuple[bool, str]:
        result = self.docker.exec(
            ["hermes", "mcp", "test", self._settings.server_id]
        )
        detail = (result.stdout or result.stderr or "").strip()
        if not detail:
            detail = "Hermes MCP test returned no diagnostic output."
        return bool(result.succeeded), detail

    def _probe_open_webui(self) -> tuple[bool, str]:
        api = getattr(self._manager, "api")
        session = api.authenticate_no_auth_admin()
        token = _required_text(session, "token", "Open WebUI admin session")
        request = getattr(api, "_request_json")
        result = request(
            "POST",
            "/api/v1/configs/tool_servers/verify",
            payload=_open_webui_connection(self._settings, self._token),
            token=token,
        )
        if result.get("status") is not True:
            return False, "Open WebUI MCP verification did not return status=true."
        observed = _open_webui_tool_names(result.get("specs"))
        expected = set(self._settings.tools)
        if observed != expected:
            return (
                False,
                "Open WebUI discovered MCP tools "
                f"{sorted(observed)!r}; expected {sorted(expected)!r}.",
            )
        return True, f"discovered exactly {len(observed)} expected GitHub MCP tools"

    def _probe_agent_zero(self) -> tuple[bool, str]:
        api = getattr(self._manager, "api")
        request = getattr(api, "_request_json")
        result = request(
            "POST",
            "/api/mcp_server_get_detail",
            payload={"server_name": self._settings.server_id},
        )
        if result.get("success") is not True:
            return False, str(result.get("error") or "Agent Zero MCP detail probe failed.")
        detail = result.get("detail")
        if not isinstance(detail, Mapping):
            return False, "Agent Zero MCP detail probe returned no detail mapping."

        observed = _agent_zero_tool_names(detail)
        expected = set(self._settings.tools)
        error = detail.get("error")
        connected = detail.get("connected")
        if error:
            return False, f"Agent Zero MCP server reported error: {error}"
        if connected is False:
            return False, "Agent Zero MCP server is not connected."
        if observed != expected:
            return (
                False,
                "Agent Zero discovered MCP tools "
                f"{sorted(observed)!r}; expected {sorted(expected)!r}.",
            )
        return True, f"discovered exactly {len(observed)} expected GitHub MCP tools"


class _integration_settings:
    def __init__(
        self,
        *,
        endpoint: str,
        credential_env: str,
        server_id: str,
        tools: tuple[str, ...],
    ) -> None:
        self.endpoint = endpoint
        self.credential_env = credential_env
        self.server_id = server_id
        self.tools = tools


def _settings(configuration: Mapping[str, Any]) -> _integration_settings:
    endpoint = _required_configuration_text(configuration, "endpoint")
    if not endpoint.startswith("https://"):
        raise ValueError("GitHub MCP endpoint must use HTTPS.")

    credential_env = _required_configuration_text(configuration, "credential_env")
    if _ENV_NAME.fullmatch(credential_env) is None:
        raise ValueError("credential_env must be a safe uppercase environment name.")

    server_id = _required_configuration_text(configuration, "server_id")
    if _SERVER_ID.fullmatch(server_id) is None:
        raise ValueError("server_id must match [a-z0-9_]+.")

    raw_tools = configuration.get("tools")
    if not isinstance(raw_tools, (list, tuple)) or not raw_tools:
        raise ValueError("tools must be a non-empty list of MCP tool names.")

    tools: list[str] = []
    for value in raw_tools:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("tools must contain only non-empty strings.")
        tool = value.strip()
        if tool in tools:
            raise ValueError(f"Duplicate MCP tool name: '{tool}'.")
        tools.append(tool)

    return _integration_settings(
        endpoint=endpoint,
        credential_env=credential_env,
        server_id=server_id,
        tools=tuple(tools),
    )


def _credential(settings: _integration_settings) -> str:
    value = os.environ.get(settings.credential_env, "")
    if not value.strip():
        raise ValueError(
            f"Required integration credential environment variable "
            f"'{settings.credential_env}' is unset or empty."
        )
    return value.strip()


def _headers(token: str, tools: tuple[str, ...]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-MCP-Tools": ",".join(tools),
    }


def _open_webui_connection(
    settings: _integration_settings,
    token: str,
) -> dict[str, Any]:
    return {
        "url": settings.endpoint,
        "path": "",
        "type": "mcp",
        "auth_type": "bearer",
        "forward_cookies": False,
        "headers": {"X-MCP-Tools": ",".join(settings.tools)},
        "key": token,
        "config": {"enable": True},
        "info": {
            "id": settings.server_id,
            "name": "GitHub MCP",
            "description": "Official GitHub MCP Server qualification connection.",
        },
    }


def _open_webui_tool_names(specs: Any) -> set[str]:
    names: set[str] = set()
    if not isinstance(specs, list):
        return names
    for spec in specs:
        if not isinstance(spec, Mapping):
            continue
        name = spec.get("name")
        if not isinstance(name, str):
            function = spec.get("function")
            if isinstance(function, Mapping):
                name = function.get("name")
        if isinstance(name, str) and name:
            names.add(_strip_tool_prefix(name, "github_"))
    return names


def _agent_zero_tool_names(detail: Mapping[str, Any]) -> set[str]:
    tools = detail.get("tools")
    if not isinstance(tools, list):
        return set()
    names: set[str] = set()
    for tool in tools:
        if isinstance(tool, str) and tool:
            names.add(_strip_tool_prefix(tool, "github."))
            continue
        if not isinstance(tool, Mapping):
            continue
        name = tool.get("name")
        if isinstance(name, str) and name:
            names.add(_strip_tool_prefix(name, "github."))
    return names


def _strip_tool_prefix(name: str, prefix: str) -> str:
    return name[len(prefix):] if name.startswith(prefix) else name


def _required_configuration_text(
    configuration: Mapping[str, Any],
    field: str,
) -> str:
    value = configuration.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Integration configuration '{field}' must be non-empty text.")
    return value.strip()


def _append_unique_pair(
    values: tuple[tuple[str, Any], ...],
    key: str,
    value: Any,
) -> tuple[tuple[str, Any], ...]:
    if any(existing_key == key for existing_key, _ in values):
        raise ValueError(f"Integration managed configuration key already exists: '{key}'.")
    return values + ((key, value),)


def _append_unique_values(
    existing: tuple[str, ...],
    additions: tuple[str, ...],
) -> tuple[str, ...]:
    values = list(existing)
    for value in additions:
        if value not in values:
            values.append(value)
    return tuple(values)


def _required_text(value: Mapping[str, Any], key: str, context: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{context} did not provide '{key}'.")
    return result


def _redact(value: Any, secret: str) -> Any:
    if isinstance(value, str):
        return value.replace(secret, _REDACTED)
    if isinstance(value, dict):
        return {key: _redact(item, secret) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, secret) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item, secret) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        replacements = {
            item.name: _redact(getattr(value, item.name), secret)
            for item in fields(value)
        }
        return replace(value, **replacements)
    return value


__all__ = ["build_integration"]
