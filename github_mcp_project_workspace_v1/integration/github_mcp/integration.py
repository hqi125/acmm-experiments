from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any, Mapping

from acmm.integration_api import (
    experiment_integration,
    experiment_integration_context,
    integration_check,
    integration_report,
    shared_integration_context,
    subject_integration,
    subject_integration_context,
    tool_result_interpretation_context,
)
from acmm_infra.common import doctor_check, doctor_report, infrastructure_error
from acmm_infra.process import command_runner


_REDACTED = "<redacted>"
_UNADMITTED_TOKEN = "acmm-runtime-admission-required"
_AGENT_ZERO_CATALOG_RETRY_DELAYS = (0.0, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0)


class github_mcp_tool_result_error_interpreter:
    def detects_error(
        self,
        context: tool_result_interpretation_context,
    ) -> bool:
        if not _is_github_mcp_tool_name(context.tool_name):
            return False

        value = context.output
        for _ in range(2):
            if not isinstance(value, str):
                break
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                break

        if not isinstance(value, str):
            return False
        return value.strip().casefold().startswith("failed to ")


def _is_github_mcp_tool_name(name: str) -> bool:
    value = name.casefold()
    return (
        value.startswith("github.")
        or value.startswith("github_")
        or value.startswith("mcp__github__")
    )


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
    admission = _github_mcp_runtime_admission(settings)
    binding = subject_integration(
        profile=profile,
        manager=manager,
        admission=admission,
    )

    return experiment_integration(
        shared_resource=_local_github_mcp_resource(settings),
        tool_result_error_interpreters=(
            github_mcp_tool_result_error_interpreter(),
        ),
        subjects={
            "hermes": binding,
            "open-webui": binding,
            "agent-zero": binding,
        },
    )


class _github_mcp_profile_integration:
    def __init__(self, settings: "_integration_settings") -> None:
        self._settings = settings

    def compose_profile(
        self,
        context: subject_integration_context,
        profile: object,
    ) -> object:
        token = _UNADMITTED_TOKEN
        if context.infrastructure_subject == "hermes":
            return self._hermes(profile, token)
        if context.infrastructure_subject == "open-webui":
            return self._open_webui(profile, token)
        if context.infrastructure_subject == "agent-zero":
            return self._agent_zero(profile, token)
        raise ValueError(
            "Unsupported infrastructure subject for GitHub MCP integration: "
            + context.infrastructure_subject
        )

    def _hermes(self, profile: object, token: str) -> object:
        key = f"mcp_servers.{self._settings.server_id}"
        value = _hermes_server_value(self._settings, token)
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
        isolation = replace(isolation, mcp_tool_default="allow")
        mcp_servers = _agent_zero_servers(self._settings, token)
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
        return _runtime_workspace_manager(
            manager=manager,
            infrastructure_subject=context.infrastructure_subject,
            settings=self._settings,
        )


@dataclass(frozen=True)
class _runtime_admission_handle:
    token: str = field(repr=False)
    revoke_installation_token: Any = field(repr=False)
    repository_id: int
    repository_full_name: str
    ledger_path: str


class _github_mcp_runtime_admission:
    def __init__(self, settings: "_integration_settings") -> None:
        self._settings = settings

    def admit(
        self,
        context: subject_integration_context,
        manager: object,
        payload: Mapping[str, Any],
    ) -> _runtime_admission_handle:
        del context
        token = _required_payload_text(payload, "access_token")
        repository_full_name = _required_payload_text(
            payload, "repository_full_name"
        )
        ledger_path = _required_payload_text(payload, "ledger_path")
        revoke_installation_token = payload.get("revoke_installation_token")
        if not callable(revoke_installation_token):
            raise ValueError(
                "Runtime GitHub MCP admission revocation callback is invalid."
            )
        repository_id = payload.get("repository_id")
        if not isinstance(repository_id, int) or isinstance(repository_id, bool) or repository_id <= 0:
            raise ValueError("Runtime GitHub MCP admission repository_id is invalid.")
        runtime_admit = getattr(manager, "runtime_admit", None)
        if not callable(runtime_admit):
            raise ValueError("GitHub MCP subject manager does not support runtime admission.")
        runtime_admit(token)
        _update_resource_ledger(
            ledger_path,
            repository_id,
            subject_bound=True,
        )
        return _runtime_admission_handle(
            token=token,
            revoke_installation_token=revoke_installation_token,
            repository_id=repository_id,
            repository_full_name=repository_full_name,
            ledger_path=ledger_path,
        )

    def revoke(
        self,
        context: subject_integration_context,
        manager: object,
        handle: _runtime_admission_handle,
    ) -> Mapping[str, Any]:
        del context
        if not isinstance(handle, _runtime_admission_handle):
            raise ValueError("GitHub MCP runtime admission handle is invalid.")
        errors: list[str] = []
        token_revoked = False
        subject_unbound = False
        # Remove the run credential from the subject first. Provider-directed
        # cooldowns may delay the remote revocation request, but they must not
        # extend the subject's local admission window.
        try:
            runtime_revoke = getattr(manager, "runtime_revoke", None)
            if not callable(runtime_revoke):
                raise ValueError(
                    "GitHub MCP subject manager does not support runtime revocation."
                )
            runtime_revoke(handle.token)
            subject_unbound = True
            _update_resource_ledger(
                handle.ledger_path,
                handle.repository_id,
                subject_unbound=True,
            )
        except Exception as exc:
            errors.append("subject unbind: " + (str(exc) or exc.__class__.__name__))

        try:
            handle.revoke_installation_token(handle.token)
            token_revoked = True
            _update_resource_ledger(
                handle.ledger_path,
                handle.repository_id,
                token_revoked=True,
            )
        except Exception as exc:
            errors.append("token revocation: " + (str(exc) or exc.__class__.__name__))

        if errors:
            raise RuntimeError(
                "GitHub MCP runtime revocation failed: " + "; ".join(errors)
            )
        return {
            "repository_id": handle.repository_id,
            "repository_full_name": handle.repository_full_name,
            "token_revoked": token_revoked,
            "subject_unbound": subject_unbound,
        }


class _runtime_workspace_manager:
    def __init__(
        self,
        *,
        manager: object,
        infrastructure_subject: str,
        settings: "_integration_settings",
    ) -> None:
        self._manager = manager
        self._infrastructure_subject = infrastructure_subject
        self._settings = settings
        self.profile = getattr(manager, "profile")
        self.deployment_root = getattr(manager, "deployment_root")
        self.docker = getattr(manager, "docker")

    def __getattr__(self, name: str) -> object:
        return getattr(self._manager, name)

    def apply(self, *, timeout_seconds: float = 120.0, progress=None):
        try:
            return self._manager.apply(
                timeout_seconds=timeout_seconds,
                progress=progress,
            )
        except Exception as exc:
            raise infrastructure_error(str(exc) or exc.__class__.__name__) from exc

    def status(self):
        return self._manager.status()

    def doctor(self):
        base = self._manager.doctor()
        admission = doctor_check(
            "integration:github_mcp_discovery",
            True,
            "static deployment is intentionally unadmitted; exact MCP catalog is "
            "verified after per-run credential admission",
        )
        return doctor_report(checks=tuple(base.checks) + (admission,))

    def up(self, *, timeout_seconds: float = 120.0) -> None:
        self._manager.up(timeout_seconds=timeout_seconds)

    def down(self) -> None:
        self._manager.down()

    def runtime_admit(self, token: str) -> None:
        self._set_runtime_token(token)
        ok, detail = self._catalog_check(token)
        if ok:
            return
        try:
            self._set_runtime_token(_UNADMITTED_TOKEN)
        except Exception:
            pass
        raise infrastructure_error(
            "GitHub MCP runtime admission catalog verification failed: "
            + str(_redact(detail, token))
        )

    def runtime_revoke(self, token: str) -> None:
        self._set_runtime_token(_UNADMITTED_TOKEN)

    def _set_runtime_token(self, token: str) -> None:
        if self._infrastructure_subject == "hermes":
            key = f"mcp_servers.{self._settings.server_id}"
            value = _hermes_server_value(self._settings, token)
            result = self.docker.exec(
                ["hermes", "config", "set", key, value, "--force"]
            )
            if not result.succeeded:
                detail = (result.stderr or result.stdout or "").strip()
                raise infrastructure_error(
                    "Hermes runtime MCP credential update failed: "
                    + str(_redact(detail, token))
                )
            return
        if self._infrastructure_subject == "open-webui":
            api = getattr(self._manager, "api")
            session = api.authenticate_no_auth_admin()
            admin_token = _required_text(session, "token", "Open WebUI admin session")
            api.import_config(
                admin_token,
                {
                    "tool_server.connections": [
                        _open_webui_connection(self._settings, token)
                    ]
                },
            )
            return
        if self._infrastructure_subject == "agent-zero":
            api = getattr(self._manager, "api")
            observed = api.get_settings()
            settings = observed.get("settings")
            if not isinstance(settings, dict):
                raise infrastructure_error(
                    "Agent Zero settings response did not contain a settings object."
                )
            desired = dict(settings)
            desired["mcp_servers"] = _agent_zero_servers(self._settings, token)
            updated = api.update_settings(desired)
            updated_settings = updated.get("settings")
            if (
                not isinstance(updated_settings, dict)
                or updated_settings.get("mcp_servers") != desired["mcp_servers"]
            ):
                raise infrastructure_error(
                    "Agent Zero runtime MCP credential update was not persisted."
                )
            return
        raise infrastructure_error(
            "Unsupported infrastructure subject for GitHub MCP runtime admission: "
            + self._infrastructure_subject
        )

    def _catalog_check(self, token: str) -> tuple[bool, str]:
        try:
            if self._infrastructure_subject == "hermes":
                return self._probe_hermes()
            if self._infrastructure_subject == "open-webui":
                return self._probe_open_webui(token)
            if self._infrastructure_subject == "agent-zero":
                return self._probe_agent_zero()
            return False, "unsupported infrastructure subject"
        except Exception as exc:
            return False, str(_redact(str(exc) or exc.__class__.__name__, token))

    def _probe_hermes(self) -> tuple[bool, str]:
        result = self.docker.exec(["hermes", "mcp", "test", self._settings.server_id])
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
            return False, (
                "Hermes discovered MCP tools "
                f"{sorted(observed)!r} with reported count {discovered_count}; "
                f"expected {sorted(expected)!r}."
            )
        return True, (
            f"discovered exactly {len(observed)} expected GitHub MCP tools "
            f"(catalog sha256={_catalog_sha256(observed)})"
        )

    def _probe_open_webui(self, token: str) -> tuple[bool, str]:
        api = getattr(self._manager, "api")
        session = api.authenticate_no_auth_admin()
        admin_token = _required_text(session, "token", "Open WebUI admin session")
        request = getattr(api, "_request_json")
        result = request(
            "POST",
            "/api/v1/configs/tool_servers/verify",
            payload=_open_webui_connection(self._settings, token),
            token=admin_token,
        )
        if result.get("status") is not True:
            return False, "Open WebUI MCP verification did not return status=true."
        observed = _open_webui_tool_names(result.get("specs"))
        expected = set(self._settings.expected_tools)
        if observed != expected:
            return False, (
                "Open WebUI discovered MCP tools "
                f"{sorted(observed)!r}; expected {sorted(expected)!r}."
            )
        return True, (
            f"discovered exactly {len(observed)} expected GitHub MCP tools "
            f"(catalog sha256={_catalog_sha256(observed)})"
        )

    def _probe_agent_zero(self) -> tuple[bool, str]:
        last_detail = "Agent Zero MCP catalog did not become ready."
        for delay in _AGENT_ZERO_CATALOG_RETRY_DELAYS:
            if delay > 0:
                time.sleep(delay)
            try:
                ok, detail = self._probe_agent_zero_once()
            except Exception as exc:
                ok = False
                detail = str(exc) or exc.__class__.__name__
            if ok:
                return True, detail
            last_detail = detail
        return False, last_detail

    def _probe_agent_zero_once(self) -> tuple[bool, str]:
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
            return False, (
                "Agent Zero discovered MCP tools "
                f"{sorted(observed)!r}; expected {sorted(expected)!r}."
            )
        return True, (
            f"discovered exactly {len(observed)} expected GitHub MCP tools "
            f"(catalog sha256={_catalog_sha256(observed)})"
        )


def _hermes_server_value(settings: "_integration_settings", token: str) -> str:
    return json.dumps(
        {
            "url": settings.endpoint,
            "headers": _headers(token),
            "enabled": True,
            "timeout": 120,
            "connect_timeout": 30,
            "supports_parallel_tool_calls": False,
            "tools": {"resources": False, "prompts": False},
        },
        separators=(",", ":"),
    )


def _agent_zero_servers(settings: "_integration_settings", token: str) -> str:
    return json.dumps(
        {
            "mcpServers": {
                settings.server_id: {
                    "type": "streamable-http",
                    "url": settings.endpoint,
                    "headers": _headers(token),
                    "init_timeout": 60,
                    "tool_timeout": 120,
                    "verify": True,
                }
            }
        },
        separators=(",", ":"),
    )


def _required_payload_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Runtime GitHub MCP admission field '{key}' is invalid.")
    return value.strip()


def _update_resource_ledger(
    ledger_path: str,
    repository_id: int,
    **changes: Any,
) -> None:
    path = Path(ledger_path)
    value = json.loads(path.read_text(encoding="utf-8"))
    repositories = value.get("repositories")
    if not isinstance(repositories, list):
        raise RuntimeError("GitHub runtime resource ledger is invalid.")
    for item in repositories:
        if not isinstance(item, dict) or item.get("repository_id") != repository_id:
            continue
        for key, change in changes.items():
            if key not in item:
                raise RuntimeError(
                    f"GitHub runtime resource ledger field '{key}' is unavailable."
                )
            item[key] = change
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("wb") as handle:
            handle.write((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        return
    raise RuntimeError(
        f"GitHub runtime resource ledger does not contain repository id {repository_id}."
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
        github_api_base: str,
        image: str,
        container_name: str,
        host_port: int,
        build_context: str,
        build_dockerfile: str,
        upstream_repository: str,
        upstream_version: str,
        upstream_commit: str,
        governor_version: str,
        request_interval: str,
        mutation_interval: str,
        retry_after_grace: str,
        primary_reset_grace: str,
        secondary_backoff: str,
    ) -> None:
        self.endpoint = endpoint
        self.server_id = server_id
        self.toolsets = toolsets
        self.excluded_tools = excluded_tools
        self.expected_tools = expected_tools
        self.expected_catalog_sha256 = expected_catalog_sha256
        self.github_api_base = github_api_base
        self.image = image
        self.container_name = container_name
        self.host_port = host_port
        self.build_context = build_context
        self.build_dockerfile = build_dockerfile
        self.upstream_repository = upstream_repository
        self.upstream_version = upstream_version
        self.upstream_commit = upstream_commit
        self.governor_version = governor_version
        self.request_interval = request_interval
        self.mutation_interval = mutation_interval
        self.retry_after_grace = retry_after_grace
        self.primary_reset_grace = primary_reset_grace
        self.secondary_backoff = secondary_backoff


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
    github_api_base = _required_configuration_text(configuration, "github_api_base")
    if not github_api_base.startswith("https://"):
        raise ValueError("github_api_base must use HTTPS.")
    service = configuration.get("local_service")
    if not isinstance(service, Mapping):
        raise ValueError("local_service must be a mapping.")
    image = _required_configuration_text(service, "image")
    container_name = _required_configuration_text(service, "container_name")
    build_context = _required_configuration_text(service, "build_context")
    build_dockerfile = _required_configuration_text(service, "build_dockerfile")
    upstream_repository = _required_configuration_text(service, "upstream_repository")
    upstream_version = _required_configuration_text(service, "upstream_version")
    upstream_commit = _required_configuration_text(service, "upstream_commit").lower()
    if not re.fullmatch(r"[0-9a-f]{40}", upstream_commit):
        raise ValueError("local_service.upstream_commit must be a full lowercase SHA-1.")
    governor_version = _required_configuration_text(service, "governor_version")
    request_interval = _required_configuration_text(service, "request_interval")
    mutation_interval = _required_configuration_text(service, "mutation_interval")
    retry_after_grace = _required_configuration_text(service, "retry_after_grace")
    primary_reset_grace = _required_configuration_text(service, "primary_reset_grace")
    secondary_backoff = _required_configuration_text(service, "secondary_backoff")
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
        github_api_base=github_api_base,
        image=image,
        container_name=container_name,
        host_port=host_port,
        build_context=build_context,
        build_dockerfile=build_dockerfile,
        upstream_repository=upstream_repository,
        upstream_version=upstream_version,
        upstream_commit=upstream_commit,
        governor_version=governor_version,
        request_interval=request_interval,
        mutation_interval=mutation_interval,
        retry_after_grace=retry_after_grace,
        primary_reset_grace=primary_reset_grace,
        secondary_backoff=secondary_backoff,
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
    _UPSTREAM_VERSION_LABEL = "io.acmm.github-mcp.upstream-version"
    _UPSTREAM_COMMIT_LABEL = "io.acmm.github-mcp.upstream-commit"
    _GOVERNOR_VERSION_LABEL = "io.acmm.github-mcp.governor-version"

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
        governor_state_root = context.state_root / "mcp-governor-state"
        governor_state_root.mkdir(parents=True, exist_ok=True)
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
            "ACMM_GITHUB_MCP_HOST_PORT=" + str(self._settings.host_port) + "\n"
            "ACMM_GITHUB_MCP_REQUEST_INTERVAL=" + self._settings.request_interval + "\n"
            "ACMM_GITHUB_MCP_MUTATION_INTERVAL=" + self._settings.mutation_interval + "\n"
            "ACMM_GITHUB_MCP_RETRY_AFTER_GRACE=" + self._settings.retry_after_grace + "\n"
            "ACMM_GITHUB_MCP_PRIMARY_RESET_GRACE=" + self._settings.primary_reset_grace + "\n"
            "ACMM_GITHUB_MCP_SECONDARY_BACKOFF=" + self._settings.secondary_backoff + "\n",
            encoding="utf-8",
        )

        initially_running = self.is_running(context)
        if self._image_identity_matches():
            if progress is not None:
                progress(
                    "image: governed GitHub MCP build already qualified "
                    f"({self._settings.image})"
                )
        else:
            if progress is not None:
                progress(
                    "image: building governed GitHub MCP server from "
                    f"{self._settings.upstream_version} "
                    f"({self._settings.upstream_commit[:12]})..."
                )
            self._build_image(
                context,
                timeout_seconds=max(timeout_seconds, 900.0),
            )
            if not self._image_identity_matches():
                raise ValueError(
                    "Governed GitHub MCP image build completed without the expected "
                    "source/governor identity labels."
                )
            if progress is not None:
                progress(f"image: governed build complete ({self._settings.image})")

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
        if status.get("image_identity_ok") is not True:
            raise ValueError(
                "Governed GitHub MCP image identity mismatch: "
                f"observed={status.get('image_labels')!r}."
            )
        if progress is not None:
            progress(
                "image identity: "
                f"upstream={self._settings.upstream_version}@"
                f"{self._settings.upstream_commit[:12]}, "
                f"governor={self._settings.governor_version}"
            )
            if status.get("running"):
                progress("container: running after reconciliation")
            elif status.get("container_present"):
                progress("container: stopped after reconciliation")
            else:
                progress("container: absent after reconciliation")
        return status

    def status(self, context: shared_integration_context):
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
            observed = result.stdout.strip().split("\t", 1)
            running = bool(observed) and observed[0].lower() == "true"
            observed_image = observed[1] if len(observed) == 2 else None

        labels = self._image_labels()
        governor_state = self._governor_state(context)
        return {
            "running": running,
            "container_present": container_present,
            "image": observed_image or self._settings.image,
            "image_present": self._image_present(),
            "image_labels": labels,
            "image_identity_ok": self._labels_match(labels),
            "endpoint": self._settings.endpoint,
            "toolsets": list(self._settings.toolsets),
            "excluded_tools": list(self._settings.excluded_tools),
            "expected_tools": list(self._settings.expected_tools),
            "expected_catalog_sha256": self._settings.expected_catalog_sha256,
            "upstream_version": self._settings.upstream_version,
            "upstream_commit": self._settings.upstream_commit,
            "governor_version": self._settings.governor_version,
            "governor_policy": {
                "request_interval": self._settings.request_interval,
                "mutation_interval": self._settings.mutation_interval,
                "retry_after_grace": self._settings.retry_after_grace,
                "primary_reset_grace": self._settings.primary_reset_grace,
                "secondary_backoff": self._settings.secondary_backoff,
            },
            "governor_state": governor_state,
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
            progress("container: starting shared governed MCP service")
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
        labels = status.get("image_labels") or {}
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
                    "image_identity",
                    status.get("image_identity_ok") is True,
                    (
                        f"upstream={labels.get(self._UPSTREAM_VERSION_LABEL)!r}@"
                        f"{labels.get(self._UPSTREAM_COMMIT_LABEL)!r}, "
                        f"governor={labels.get(self._GOVERNOR_VERSION_LABEL)!r}"
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

    def _image_labels(self) -> dict[str, str]:
        result = self._runner.run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                "{{json .Config.Labels}}",
                self._settings.image,
            ],
            timeout_seconds=15,
        )
        if not result.succeeded:
            return {}
        try:
            parsed = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, Mapping):
            return {}
        return {
            str(key): str(value)
            for key, value in parsed.items()
            if isinstance(key, str) and isinstance(value, str)
        }

    def _labels_match(self, labels: Mapping[str, str]) -> bool:
        return (
            labels.get(self._UPSTREAM_VERSION_LABEL) == self._settings.upstream_version
            and labels.get(self._UPSTREAM_COMMIT_LABEL) == self._settings.upstream_commit
            and labels.get(self._GOVERNOR_VERSION_LABEL) == self._settings.governor_version
        )

    def _image_identity_matches(self) -> bool:
        return self._image_present() and self._labels_match(self._image_labels())

    def _build_image(
        self,
        context: shared_integration_context,
        *,
        timeout_seconds: float,
    ) -> None:
        build_context = (context.package_root / self._settings.build_context).resolve()
        dockerfile = (context.package_root / self._settings.build_dockerfile).resolve()
        package_root = context.package_root.resolve()
        if package_root not in build_context.parents:
            raise ValueError("GitHub MCP build context escapes the Experiment Package root.")
        if package_root not in dockerfile.parents:
            raise ValueError("GitHub MCP Dockerfile escapes the Experiment Package root.")
        if not build_context.is_dir() or not dockerfile.is_file():
            raise ValueError("Governed GitHub MCP build payload is incomplete.")
        result = self._runner.run(
            [
                "docker",
                "build",
                "--pull",
                "--build-arg",
                "UPSTREAM_REPOSITORY=" + self._settings.upstream_repository,
                "--build-arg",
                "UPSTREAM_VERSION=" + self._settings.upstream_version,
                "--build-arg",
                "UPSTREAM_COMMIT=" + self._settings.upstream_commit,
                "--build-arg",
                "GOVERNOR_VERSION=" + self._settings.governor_version,
                "-t",
                self._settings.image,
                "-f",
                str(dockerfile),
                str(build_context),
            ],
            cwd=context.package_root,
            timeout_seconds=timeout_seconds,
        )
        if not result.succeeded:
            raise ValueError(
                result.stderr.strip()
                or result.stdout.strip()
                or "governed GitHub MCP image build failed"
            )

    def _governor_state(self, context: shared_integration_context) -> Mapping[str, Any]:
        path = context.state_root / "mcp-governor-state/governor.json"
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, Mapping) else {}

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
