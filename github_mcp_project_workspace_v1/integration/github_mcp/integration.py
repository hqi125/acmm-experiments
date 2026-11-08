from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any, Mapping

from acmm.integration_api import (
    experiment_integration,
    experiment_integration_context,
    integration_check,
    integration_report,
    shared_integration_context,
    subject_integration,
    subject_integration_context,
)
from acmm_infra.common import doctor_check, doctor_report, infrastructure_error
from acmm_infra.process import command_runner


_REDACTED = "<redacted>"


def build_integration(
    context: experiment_integration_context,
) -> experiment_integration:
    if context.preset != "local_pinned":
        raise ValueError(
            f"Unsupported GitHub MCP project-workspace preset: {context.preset!r}."
        )
    settings = _settings(context.configuration)
    profile = _github_mcp_profile_integration(settings)
    manager = _github_mcp_manager_integration(settings)

    return experiment_integration(
        shared_resource=_local_github_mcp_resource(settings),
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
        token = context.resolve_secret("access_token").strip()

        if context.infrastructure_subject == "hermes":
            return self._hermes(profile, token)
        if context.infrastructure_subject == "open-webui":
            return self._open_webui(profile, token)
        if context.infrastructure_subject == "agent-zero":
            return self._agent_zero(profile, token)

        raise ValueError(
            "GitHub MCP project-workspace integration does not support infrastructure "
            f"subject '{context.infrastructure_subject}'."
        )

    def _hermes(self, profile: object, token: str) -> object:
        key = f"mcp_servers.{self._settings.server_id}"
        value = json.dumps(
            {
                "url": self._settings.endpoint,
                "headers": _headers(token),
                "enabled": True,
                "timeout": 120,
                "connect_timeout": 30,
                "supports_parallel_tool_calls": False,
                "tools": {
                    "include": list(self._settings.expected_tools),
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
            f"mcp:{self._settings.server_id}:{tool}" for tool in self._settings.expected_tools
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
                        "headers": _headers(token),
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
        token = context.resolve_secret("access_token").strip()
        return _redacting_workspace_manager(
            manager=manager,
            infrastructure_subject=context.infrastructure_subject,
            settings=self._settings,
            token=token,
        )


class _redacting_workspace_manager:
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
        safe_progress = None
        if progress is not None:
            safe_progress = lambda message: progress(_redact(message, self._token))
        try:
            value = self._manager.apply(
                timeout_seconds=timeout_seconds,
                progress=safe_progress,
            )
        except Exception as exc:
            detail = str(_redact(str(exc), self._token))
            raise infrastructure_error(detail) from exc
        return _redact(value, self._token)

    def status(self):
        return _redact(self._manager.status(), self._token)

    def doctor(self):
        base = self._manager.doctor()
        catalog = self._catalog_check()
        report = doctor_report(checks=tuple(base.checks) + (catalog,))
        return _redact(report, self._token)

    def up(self, *, timeout_seconds: float = 120.0) -> None:
        self._manager.up(timeout_seconds=timeout_seconds)

    def down(self) -> None:
        self._manager.down()

    def _catalog_check(self) -> doctor_check:
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
            return False, "Hermes MCP test returned no diagnostic output."
        if not result.succeeded:
            return False, detail

        plain = _strip_ansi(detail)
        count_match = re.search(r"Tools discovered:\s*(\d+)", plain)
        if count_match is None:
            return False, "Hermes MCP test did not report a discovered-tool count."

        expected = set(self._settings.expected_tools)
        observed = {
            tool
            for tool in expected
            if re.search(rf"(?m)^\s*{re.escape(tool)}(?:\s|$)", plain)
        }
        discovered_count = int(count_match.group(1))
        if discovered_count != len(expected) or observed != expected:
            return (
                False,
                "Hermes discovered MCP tools "
                f"{sorted(observed)!r} with reported count {discovered_count}; "
                f"expected {sorted(expected)!r}.",
            )
        return (
            True,
            f"discovered exactly {len(observed)} expected GitHub MCP tools "
            f"(catalog sha256={_catalog_sha256(observed)})",
        )

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
        expected = set(self._settings.expected_tools)
        if observed != expected:
            return (
                False,
                "Open WebUI discovered MCP tools "
                f"{sorted(observed)!r}; expected {sorted(expected)!r}.",
            )
        return (
            True,
            f"discovered exactly {len(observed)} expected GitHub MCP tools "
            f"(catalog sha256={_catalog_sha256(observed)})",
        )

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
        expected = set(self._settings.expected_tools)
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
        return (
            True,
            f"discovered exactly {len(observed)} expected GitHub MCP tools "
            f"(catalog sha256={_catalog_sha256(observed)})",
        )


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _strip_ansi(value: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", value)


class _integration_settings:
    def __init__(
        self,
        *,
        endpoint: str,
        server_id: str,
        toolsets: tuple[str, ...],
        excluded_tools: tuple[str, ...],
        expected_tools: tuple[str, ...],
        expected_catalog_sha256: str,
        image: str,
        expected_repo_digest: str,
        container_name: str,
        host_port: int,
    ) -> None:
        self.endpoint = endpoint
        self.server_id = server_id
        self.toolsets = toolsets
        self.excluded_tools = excluded_tools
        self.expected_tools = expected_tools
        self.expected_catalog_sha256 = expected_catalog_sha256
        self.image = image
        self.expected_repo_digest = expected_repo_digest
        self.container_name = container_name
        self.host_port = host_port


def _settings(configuration: Mapping[str, Any]) -> _integration_settings:
    endpoint = _required_configuration_text(configuration, "endpoint")
    if not endpoint.startswith("http://host.docker.internal:"):
        raise ValueError("local_pinned endpoint must use host.docker.internal HTTP.")
    server_id = _required_configuration_text(configuration, "server_id")
    toolsets = _required_unique_text_list(configuration, "toolsets")
    excluded_tools = _required_unique_text_list(configuration, "excluded_tools")
    expected_tools = _required_unique_text_list(configuration, "expected_tools")
    if set(excluded_tools) & set(expected_tools):
        raise ValueError("excluded_tools and expected_tools must not overlap.")
    expected_catalog_sha256 = _required_configuration_text(
        configuration, "expected_catalog_sha256"
    ).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_catalog_sha256):
        raise ValueError("expected_catalog_sha256 must be 64 lowercase hex characters.")
    observed_catalog_sha256 = _catalog_sha256(expected_tools)
    if observed_catalog_sha256 != expected_catalog_sha256:
        raise ValueError(
            "expected_tools catalog digest does not match expected_catalog_sha256: "
            f"observed={observed_catalog_sha256}, expected={expected_catalog_sha256}."
        )
    service = configuration.get("local_service")
    if not isinstance(service, Mapping):
        raise ValueError("local_service must be a mapping.")
    image = _required_configuration_text(service, "image")
    expected_repo_digest = _required_configuration_text(
        service, "expected_repo_digest"
    )
    container_name = _required_configuration_text(service, "container_name")
    host_port = service.get("host_port")
    if (
        not isinstance(host_port, int)
        or isinstance(host_port, bool)
        or not (1 <= host_port <= 65535)
    ):
        raise ValueError("local_service.host_port must be a valid TCP port.")
    return _integration_settings(
        endpoint=endpoint,
        server_id=server_id,
        toolsets=toolsets,
        excluded_tools=excluded_tools,
        expected_tools=expected_tools,
        expected_catalog_sha256=expected_catalog_sha256,
        image=image,
        expected_repo_digest=expected_repo_digest,
        container_name=container_name,
        host_port=host_port,
    )


def _required_unique_text_list(
    configuration: Mapping[str, Any],
    field: str,
) -> tuple[str, ...]:
    raw = configuration.get(field)
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError(f"{field} must be a non-empty list of names.")
    values = tuple(str(value).strip() for value in raw)
    if any(not value for value in values) or len(set(values)) != len(values):
        raise ValueError(f"{field} must contain unique non-empty names.")
    return values


def _catalog_sha256(tools: tuple[str, ...] | set[str]) -> str:
    normalized = "".join(f"{tool}\n" for tool in sorted(set(tools)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class _local_github_mcp_resource:
    def __init__(self, settings: _integration_settings) -> None:
        self._settings = settings
        self._runner = command_runner()

    def apply(
        self,
        context: shared_integration_context,
        *,
        timeout_seconds: float = 120.0,
        progress=None,
    ):
        context.state_root.mkdir(parents=True, exist_ok=True)
        source = context.package_root / "integration/github_mcp/payloads/compose.yaml"
        shutil.copy2(source, context.state_root / "compose.yaml")
        env_path = context.state_root / ".env"
        env_path.write_text(
            "ACMM_GITHUB_MCP_IMAGE=" + self._settings.image + "\n"
            "ACMM_GITHUB_MCP_CONTAINER=" + self._settings.container_name + "\n"
            "ACMM_GITHUB_MCP_TOOLSETS=" + ",".join(self._settings.toolsets) + "\n"
            "ACMM_GITHUB_MCP_EXCLUDE_TOOLS="
            + ",".join(self._settings.excluded_tools)
            + "\n"
            "ACMM_GITHUB_MCP_HOST_PORT=" + str(self._settings.host_port) + "\n",
            encoding="utf-8",
        )

        initially_running = self.is_running(context)
        if self._image_present():
            if progress is not None:
                progress(f"image: already present ({self._settings.image})")
        else:
            if progress is not None:
                progress(f"image: pulling {self._settings.image}...")
            pull = self._compose(context, ["pull", "github-mcp"], timeout_seconds)
            if not pull.succeeded:
                raise ValueError(
                    pull.stderr.strip()
                    or pull.stdout.strip()
                    or "docker compose pull failed"
                )
            if progress is not None:
                progress(f"image: pull complete ({self._settings.image})")

        if initially_running:
            if progress is not None:
                progress("container: reconciling and preserving running state")
            result = self._compose(
                context,
                ["up", "-d", "--force-recreate", "github-mcp"],
                timeout_seconds,
            )
            if not result.succeeded:
                raise ValueError(
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "docker compose resource reconciliation failed"
                )
        else:
            if progress is not None:
                progress("container: reconciling ephemeral stopped state")
            self._remove_container_if_present()
            result = self._compose(
                context,
                ["config", "--quiet"],
                timeout_seconds,
            )
            if not result.succeeded:
                raise ValueError(
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "docker compose resource validation failed"
                )

        status = dict(self.status(context))
        repo_digests = status.get("repo_digests") or []
        if self._settings.expected_repo_digest not in repo_digests:
            raise ValueError(
                "Pinned GitHub MCP image digest mismatch: "
                f"observed={repo_digests!r}, "
                f"expected={self._settings.expected_repo_digest!r}."
            )
        if progress is not None:
            digests = status.get("repo_digests") or []
            if digests:
                progress(f"image digest: {digests[0]}")
            if status.get("running"):
                progress("container: running after reconciliation")
            elif status.get("container_present"):
                progress("container: stopped after reconciliation")
            else:
                progress("container: absent after reconciliation")
        return status

    def status(self, context: shared_integration_context):
        del context
        running = False
        container_present = False
        observed_image = None
        result = self._runner.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Running}}\t{{.Config.Image}}",
                self._settings.container_name,
            ],
            timeout_seconds=15,
        )
        if result.succeeded:
            container_present = True
            fields = result.stdout.strip().split("\t", 1)
            running = bool(fields) and fields[0].lower() == "true"
            observed_image = fields[1] if len(fields) == 2 else None

        repo_digests = self._repo_digests()
        return {
            "running": running,
            "container_present": container_present,
            "image": observed_image or self._settings.image,
            "image_present": self._image_present(),
            "repo_digests": repo_digests,
            "endpoint": self._settings.endpoint,
            "toolsets": list(self._settings.toolsets),
            "excluded_tools": list(self._settings.excluded_tools),
            "expected_tools": list(self._settings.expected_tools),
            "expected_catalog_sha256": self._settings.expected_catalog_sha256,
            "expected_repo_digest": self._settings.expected_repo_digest,
        }

    def is_running(self, context: shared_integration_context) -> bool:
        return bool(self.status(context).get("running"))

    def up(
        self,
        context: shared_integration_context,
        *,
        timeout_seconds: float = 120.0,
        progress=None,
    ) -> None:
        if progress is not None:
            progress("container: starting shared MCP service")
        result = self._compose(context, ["up", "-d", "github-mcp"], timeout_seconds)
        if not result.succeeded:
            raise ValueError(
                result.stderr.strip()
                or result.stdout.strip()
                or "docker compose up failed"
            )
        if not self.is_running(context):
            raise ValueError("GitHub MCP container did not remain running after startup.")

    def doctor(self, context: shared_integration_context) -> integration_report:
        status = self.status(context)
        return integration_report(
            checks=(
                integration_check(
                    "docker",
                    self._runner.run(["docker", "--version"], timeout_seconds=15).succeeded,
                    "Docker CLI available",
                ),
                integration_check(
                    "container_running",
                    status.get("running") is True,
                    f"container={self._settings.container_name}",
                ),
                integration_check(
                    "image",
                    status.get("image") == self._settings.image,
                    f"observed={status.get('image')!r}, expected={self._settings.image!r}",
                ),
                integration_check(
                    "image_digest",
                    self._settings.expected_repo_digest in (status.get("repo_digests") or []),
                    (
                        f"observed={status.get('repo_digests')!r}, "
                        f"expected={self._settings.expected_repo_digest!r}"
                    ),
                ),
            )
        )

    def down(self, context: shared_integration_context) -> None:
        if not (context.state_root / "compose.yaml").exists():
            self._remove_container_if_present()
            return
        result = self._compose(
            context,
            ["down", "--remove-orphans"],
            60.0,
        )
        if not result.succeeded:
            raise ValueError(
                result.stderr.strip()
                or result.stdout.strip()
                or "docker compose down failed"
            )
        self._remove_container_if_present()

    def remove(self, context: shared_integration_context) -> None:
        self.down(context)
        if context.state_root.exists():
            shutil.rmtree(context.state_root)

    def _remove_container_if_present(self) -> None:
        inspect = self._runner.run(
            ["docker", "container", "inspect", self._settings.container_name],
            timeout_seconds=15,
        )
        if not inspect.succeeded:
            return
        result = self._runner.run(
            ["docker", "rm", "-f", self._settings.container_name],
            timeout_seconds=30,
        )
        if not result.succeeded:
            raise ValueError(
                result.stderr.strip()
                or result.stdout.strip()
                or "docker container removal failed"
            )

    def _image_present(self) -> bool:
        return self._runner.run(
            ["docker", "image", "inspect", self._settings.image],
            timeout_seconds=15,
        ).succeeded

    def _repo_digests(self) -> list[str]:
        result = self._runner.run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                "{{json .RepoDigests}}",
                self._settings.image,
            ],
            timeout_seconds=15,
        )
        if not result.succeeded:
            return []
        try:
            parsed = json.loads(result.stdout.strip() or "[]")
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, str) and item]

    def _compose(
        self,
        context: shared_integration_context,
        args: list[str],
        timeout_seconds: float,
    ):
        return self._runner.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(context.state_root / ".env"),
                "-f",
                str(context.state_root / "compose.yaml"),
                *args,
            ],
            cwd=context.state_root,
            timeout_seconds=timeout_seconds,
        )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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
        "headers": {},
        "key": token,
        "config": {"enable": True},
        "info": {
            "id": settings.server_id,
            "name": "GitHub MCP",
            "description": "Pinned GitHub MCP project-workspace connection.",
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
