from __future__ import annotations

import json
from pathlib import Path
import re
from time import sleep as _sleep
from typing import Callable, Mapping
from uuid import uuid4

import yaml

from acmm.experiment_api import apparatus_action_progress, apparatus_action_result

from .api_governor import github_api_governor
from .github_app import github_app_client
from .controller import (
    github_api_error,
    github_controller_client,
    github_controller_error,
    github_fixture_base_file,
    github_repository_identity,
)


class github_api_governor_inspector:
    description = "Inspect the shared GitHub API governor budget/cooldown state."
    mutates_external_state = False

    def __init__(self, governor: github_api_governor) -> None:
        self._governor = governor

    def run(self) -> apparatus_action_result:
        snapshot = self._governor.usage_snapshot()
        window = snapshot.get("provider_window", {})
        primary_rates = (
            window.get("primary_rates")
            if isinstance(window.get("primary_rates"), Mapping)
            else {}
        )
        primary_detail = ", ".join(
            f"{domain}={snapshot.get('remaining', '?')}/{snapshot.get('limit', '?')}"
            for domain, snapshot in sorted(primary_rates.items())
            if isinstance(snapshot, Mapping)
        )
        detail = (
            "GitHub API governor state: "
            f"mode={'provider-authoritative' if snapshot.get('policy', {}).get('provider_authoritative_rate_limits') else 'static-fallback'}, "
            f"content-observed/minute={window.get('content_requests_last_minute', 0)}, "
            f"content-observed/hour={window.get('content_requests_last_hour', 0)}, "
            f"secondary_block_until={window.get('secondary_block_until', 0)}, "
            f"primary={primary_detail or 'unobserved'}"
        )
        return apparatus_action_result(
            changed=False,
            detail=detail,
            observations=snapshot,
        )


class github_fixture_base_initializer:
    description = "Initialize or verify the pinned engineering reference fixture base."
    mutates_external_state = True

    def __init__(
        self,
        client: github_controller_client,
        *,
        repository_name: str,
        expected_repository_full_name: str,
        expected_repository_id: int,
        expected_default_branch: str,
        require_private: bool,
        fixture_base_version: str,
        fixture_base_files: tuple[github_fixture_base_file, ...],
    ) -> None:
        if not fixture_base_files:
            raise ValueError("Trusted fixture base must contain at least one file.")
        self._client = client
        self._repository_name = repository_name
        self._expected_repository_full_name = expected_repository_full_name
        self._expected_repository_id = expected_repository_id
        self._expected_default_branch = expected_default_branch
        self._require_private = require_private
        self._fixture_base_version = fixture_base_version
        self._fixture_base_files = tuple(fixture_base_files)

    def run(self) -> apparatus_action_result:
        identity = self._resolve_safe_identity()
        initialized = self._repository_has_branch(identity)
        if initialized:
            self._verify_fixture_base(identity)
            head_sha = self._head_sha(identity)
            return apparatus_action_result(
                changed=False,
                detail=(
                    f"trusted fixture base v{self._fixture_base_version} is already "
                    "initialized and matches package-owned seed content"
                ),
                observations=self._observations(identity, head_sha),
            )

        self._require_clean_empty_repository(identity)
        with self._client.git_publish_batch(identity.owner, identity.name):
            for index, item in enumerate(self._fixture_base_files):
                self._client.create_or_update_file(
                    identity.owner,
                    identity.name,
                    item.path,
                    message=(
                        f"ACMM: initialize fixture base v{self._fixture_base_version} "
                        f"({item.path})"
                    ),
                    content=item.content,
                    branch=(None if index == 0 else self._expected_default_branch),
                )

        self._verify_fixture_base(identity)
        head_sha = self._head_sha(identity)
        return apparatus_action_result(
            changed=True,
            detail=(
                f"initialized trusted fixture base v{self._fixture_base_version} "
                f"on '{self._expected_default_branch}'"
            ),
            observations=self._observations(identity, head_sha),
        )

    def _resolve_safe_identity(self) -> github_repository_identity:
        identity = self._client.resolve_repository(self._repository_name)
        if (
            identity.full_name != self._expected_repository_full_name
            or identity.repository_id != self._expected_repository_id
        ):
            raise github_controller_error(
                f"Resolved repository {identity.full_name} "
                f"(repository id={identity.repository_id}); expected "
                f"{self._expected_repository_full_name} "
                f"(repository id={self._expected_repository_id})."
            )
        if self._require_private and not identity.private:
            raise github_controller_error("Pinned fixture repository is not private.")
        if not identity.issues_enabled:
            raise github_controller_error("Pinned fixture repository has Issues disabled.")
        if not identity.push_allowed:
            raise github_controller_error(
                "Controller credential does not have push access to the fixture repository."
            )
        if identity.default_branch != self._expected_default_branch:
            raise github_controller_error(
                f"Pinned fixture repository default branch is '{identity.default_branch}'; "
                f"expected '{self._expected_default_branch}'."
            )
        return identity

    def _repository_has_branch(self, identity: github_repository_identity) -> bool:
        try:
            self._client.ref(
                identity.owner,
                identity.name,
                f"heads/{self._expected_default_branch}",
            )
            return True
        except github_api_error as exc:
            if exc.status == 409 and "empty" in exc.detail.lower():
                return False
            raise

    def _require_clean_empty_repository(
        self,
        identity: github_repository_identity,
    ) -> None:
        issues = self._client.list_issues(
            identity.owner,
            identity.name,
            state="all",
            per_page=100,
        )
        pulls = self._client.list_pull_requests(
            identity.owner,
            identity.name,
            state="all",
            per_page=100,
        )
        if issues or pulls:
            raise github_controller_error(
                "Empty Git repository contains pre-existing issue or pull-request state; "
                "refusing trusted fixture-base initialization."
            )

    def _verify_fixture_base(self, identity: github_repository_identity) -> None:
        for item in self._fixture_base_files:
            actual = self._client.read_text_file(
                identity.owner,
                identity.name,
                item.path,
                ref=self._expected_default_branch,
            )
            if actual != item.content:
                raise github_controller_error(
                    f"Trusted fixture base file '{item.path}' does not match "
                    "package-owned seed content."
                )

    def _head_sha(self, identity: github_repository_identity) -> str:
        value = self._client.ref(
            identity.owner,
            identity.name,
            f"heads/{self._expected_default_branch}",
        )
        obj = value.get("object")
        sha = obj.get("sha") if isinstance(obj, dict) else None
        if not isinstance(sha, str) or not sha:
            raise github_controller_error(
                "Default-branch reference response does not contain a commit SHA."
            )
        return sha

    def _observations(
        self,
        identity: github_repository_identity,
        head_sha: str,
    ) -> dict[str, object]:
        return {
            "repository": identity.full_name,
            "repository_id": identity.repository_id,
            "default_branch": self._expected_default_branch,
            "fixture_base_version": self._fixture_base_version,
            "head_sha": head_sha,
        }

_QUARANTINE_FAILURE_PATTERNS = (
    re.compile(
        r"Disposable (?:run|scenario) repository (?P<repository>[^ ]+) "
        r"\(repository id=(?P<repository_id>[0-9]+)\) was quarantined"
    ),
    re.compile(
        r"remote cleanup failed for disposable (?:run|scenario) repository "
        r"(?P<repository>[^ ]+) "
        r"\(repository id=(?P<repository_id>[0-9]+)\)"
    ),
)


class github_quarantined_repository_cleanup:
    description = (
        "Delete exact-identity residual disposable repositories recorded by one "
        "persisted execution."
    )
    mutates_external_state = True

    def __init__(
        self,
        client: github_controller_client,
        *,
        experiment_id: str,
        run_name_prefix: str,
    ) -> None:
        if not experiment_id.strip():
            raise ValueError("Experiment id must not be empty for quarantine cleanup.")
        if not run_name_prefix.strip():
            raise ValueError("Disposable run prefix must not be empty for quarantine cleanup.")
        self._client = client
        self._experiment_id = experiment_id.strip()
        self._run_name_prefix = run_name_prefix.strip()

    def cleanup(
        self,
        execution_path: str,
        *,
        preview: bool = False,
    ) -> apparatus_action_result:
        return self._cleanup(execution_path, preview=preview, report=None)

    def cleanup_with_progress(
        self,
        execution_path: str,
        report: Callable[[apparatus_action_progress], None],
        *,
        preview: bool = False,
    ) -> apparatus_action_result:
        return self._cleanup(execution_path, preview=preview, report=report)

    def _cleanup(
        self,
        execution_path: str,
        *,
        preview: bool,
        report: Callable[[apparatus_action_progress], None] | None,
    ) -> apparatus_action_result:
        session_dir, manifest = self._load_execution(execution_path)
        targets = self._collect_targets(session_dir)
        if not targets:
            return apparatus_action_result(
                changed=False,
                detail="execution records no residual disposable repositories",
                observations={
                    "execution_id": manifest["execution"]["id"],
                    "target_count": 0,
                    "deleted_count": 0,
                    "already_absent_count": 0,
                },
            )

        deleted = 0
        absent = 0
        verified: list[str] = []
        delete_targets: list[tuple[int, str, str, str]] = []
        total = len(targets)
        for index, (repository_id, full_name) in enumerate(targets, start=1):
            _emit(
                report,
                index,
                total,
                (
                    f"verifying residual repository {full_name} "
                    f"(repository id={repository_id})"
                ),
            )
            owner, name = self._split_repository(full_name)
            self._require_disposable_name(name)
            current = self._client.repository_optional(owner, name)
            if current is None:
                absent += 1
                verified.append(f"{full_name}#{repository_id}:already-absent")
                continue

            current_id = current.get("id")
            if current_id != repository_id:
                raise github_controller_error(
                    f"Refusing cleanup of {full_name}: repository id changed from "
                    f"{repository_id} to {current_id}."
                )
            if current.get("private") is not True:
                raise github_controller_error(
                    f"Refusing cleanup of {full_name}: repository is no longer private."
                )
            self._verify_optional_fixture_marker(owner, name, full_name, repository_id)
            delete_targets.append((repository_id, full_name, owner, name))
            if preview:
                verified.append(f"{full_name}#{repository_id}:verified")

        if not preview:
            for repository_id, full_name, owner, name in delete_targets:
                _emit(
                    report,
                    None,
                    None,
                    f"deleting verified residual repository {full_name}",
                )
                self._client.delete_repository(owner, name)
                if self._client.repository_optional(owner, name) is not None:
                    raise github_controller_error(
                        f"Repository {full_name} still exists after cleanup deletion."
                    )
                deleted += 1
                verified.append(f"{full_name}#{repository_id}:deleted")

        detail = (
            f"verified {len(targets)} residual disposable repository target(s)"
            if preview
            else f"deleted {deleted} residual disposable repository target(s)"
        )
        return apparatus_action_result(
            changed=(deleted > 0),
            detail=detail,
            observations={
                "execution_id": manifest["execution"]["id"],
                "target_count": len(targets),
                "deleted_count": deleted,
                "already_absent_count": absent,
                "repositories": tuple(verified),
            },
        )

    def _load_execution(
        self,
        execution_path: str,
    ) -> tuple[Path, Mapping[str, object]]:
        path = Path(execution_path).expanduser().resolve()
        manifest_path = path if path.is_file() else path / "experiment_execution.yaml"
        if not manifest_path.is_file():
            raise github_controller_error(
                f"Execution manifest does not exist: {manifest_path}"
            )
        try:
            value = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise github_controller_error(
                f"Could not read execution manifest '{manifest_path}': {exc}"
            ) from exc
        if not isinstance(value, Mapping):
            raise github_controller_error("Execution manifest must contain a mapping.")
        execution = value.get("execution")
        if not isinstance(execution, Mapping):
            raise github_controller_error("Execution manifest is missing execution metadata.")
        if execution.get("experiment_id") != self._experiment_id:
            raise github_controller_error(
                "Execution belongs to a different experiment; refusing apparatus cleanup."
            )
        execution_id = execution.get("id")
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise github_controller_error("Execution manifest does not contain a valid id.")
        return manifest_path.parent, value

    def _collect_targets(self, session_dir: Path) -> tuple[tuple[int, str], ...]:
        by_id: dict[int, str] = {}
        run_root = session_dir / "runs"
        if not run_root.is_dir():
            return ()

        for record_path in sorted(run_root.glob("*/run_record.yaml")):
            value = _safe_yaml_mapping(record_path)
            execution = value.get("execution")
            if not isinstance(execution, Mapping):
                continue
            failure = execution.get("failure")
            if not isinstance(failure, Mapping):
                continue
            message = failure.get("message")
            if not isinstance(message, str):
                continue
            for pattern in _QUARANTINE_FAILURE_PATTERNS:
                for match in pattern.finditer(message):
                    self._remember_target(
                        by_id,
                        int(match.group("repository_id")),
                        match.group("repository"),
                    )

        for finalization_path in sorted(run_root.glob("*/environment_finalization.yaml")):
            value = _safe_yaml_mapping(finalization_path)
            result = value.get("result")
            if not isinstance(result, Mapping) or result.get("quarantined") is not True:
                continue
            repository = result.get("repository")
            repository_id = result.get("repository_id")
            if isinstance(repository, str) and isinstance(repository_id, int):
                self._remember_target(by_id, repository_id, repository)

        return tuple(sorted((repository_id, name) for repository_id, name in by_id.items()))

    @staticmethod
    def _remember_target(by_id: dict[int, str], repository_id: int, full_name: str) -> None:
        if repository_id <= 0 or "/" not in full_name:
            raise github_controller_error("Execution contains an invalid quarantine identity.")
        existing = by_id.get(repository_id)
        if existing is not None and existing != full_name:
            raise github_controller_error(
                f"Execution maps repository id {repository_id} to conflicting names."
            )
        by_id[repository_id] = full_name

    @staticmethod
    def _split_repository(full_name: str) -> tuple[str, str]:
        owner, separator, name = full_name.partition("/")
        if not separator or not owner or not name or "/" in name:
            raise github_controller_error(
                f"Quarantined repository identity '{full_name}' is invalid."
            )
        return owner, name

    def _require_disposable_name(self, name: str) -> None:
        prefix = self._run_name_prefix + "-"
        if not name.startswith(prefix):
            raise github_controller_error(
                f"Refusing cleanup of repository '{name}': it is outside the "
                f"disposable namespace '{prefix}*'."
            )

    def _verify_optional_fixture_marker(
        self,
        owner: str,
        name: str,
        full_name: str,
        repository_id: int,
    ) -> None:
        marker = self._client.contents_optional(
            owner,
            name,
            ".acmm/fixture-base.json",
            ref=None,
        )
        if marker is None:
            return
        identity = self._client.repository_identity(owner, name)
        try:
            payload = json.loads(
                self._client.read_text_file(
                    owner,
                    name,
                    ".acmm/fixture-base.json",
                    ref=identity.default_branch,
                )
            )
        except (ValueError, json.JSONDecodeError) as exc:
            raise github_controller_error(
                f"Disposable fixture marker in {full_name} is invalid."
            ) from exc
        if not isinstance(payload, Mapping):
            raise github_controller_error(
                f"Disposable fixture marker in {full_name} is not an object."
            )
        if (
            payload.get("experiment_id") != self._experiment_id
            or payload.get("repository_full_name") != full_name
            or payload.get("repository_id") != repository_id
        ):
            raise github_controller_error(
                f"Disposable fixture marker in {full_name} does not match the "
                "execution quarantine identity."
            )


def _safe_yaml_mapping(path: Path) -> Mapping[str, object]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise github_controller_error(f"Could not read '{path}': {exc}") from exc
    if not isinstance(value, Mapping):
        raise github_controller_error(f"'{path}' must contain a mapping.")
    return value


class github_disposable_repository_lifecycle_qualifier:
    description = (
        "Qualify disposable repository GitHub App attach/token/write/revoke/delete behavior."
    )
    mutates_external_state = True

    def __init__(
        self,
        controller_client: github_controller_client,
        app_client: github_app_client,
        *,
        api_base: str,
        experiment_id: str,
        probe_name_prefix: str,
        marker_path: str = ".acmm/lifecycle-probe.json",
        sleep: Callable[[float], None] = _sleep,
    ) -> None:
        if not probe_name_prefix.strip():
            raise ValueError("Disposable repository probe prefix must not be empty.")
        self._client = controller_client
        self._app_client = app_client
        self._api_base = api_base
        self._experiment_id = experiment_id
        self._probe_name_prefix = probe_name_prefix.strip()
        self._marker_path = marker_path
        self._sleep = sleep
        self._name_factory: Callable[[], str] = (
            lambda: f"{self._probe_name_prefix}-{uuid4().hex[:12]}"
        )

    def run(self) -> apparatus_action_result:
        return self._run(None)

    def run_with_progress(
        self,
        report: Callable[[apparatus_action_progress], None],
    ) -> apparatus_action_result:
        return self._run(report)

    def _run(
        self,
        report: Callable[[apparatus_action_progress], None] | None,
    ) -> apparatus_action_result:
        total = 9
        _emit(report, 1, total, "verifying controller identity")
        controller_login = _login(self._client.current_user(), "controller")
        repository_name = self._name_factory()
        description = (
            f"ACMM disposable repository lifecycle probe for {self._experiment_id}"
        )
        created: tuple[str, str, int] | None = None
        token: str | None = None
        attached = False
        deletion_started = False
        try:
            _emit(report, 2, total, f"creating private probe repository '{repository_name}'")
            response = self._client.create_repository(
                name=repository_name,
                description=description,
                private=True,
                has_issues=True,
                auto_init=False,
            )
            owner, full_name, repository_id = _created_repository_coordinates(
                response,
                expected_owner=controller_login,
                expected_name=repository_name,
            )
            created = (owner, repository_name, repository_id)

            _emit(report, 3, total, "attaching repository to the selected GitHub App installation")
            self._client.add_repository_to_app_installation(
                installation_id=self._app_client.installation_id,
                repository_id=repository_id,
            )
            attached = True

            _emit(report, 4, total, "minting one-repository GitHub App installation token")
            issued = self._app_client.mint_repository_token(
                repository_id=repository_id,
                expected_repository_full_name=full_name,
            )
            token = issued.token
            subject_client = github_controller_client(
                token,
                api_base=self._api_base,
                transport=self._client._transport,
                mutation_interval_seconds=2.0,
                governor=self._client._governor,
                primary_domain="installation",
            )
            subject_identity = subject_client.repository_identity(owner, repository_name)
            _verify_probe_identity(
                subject_identity,
                expected_full_name=full_name,
                expected_repository_id=repository_id,
                role="subject App token",
                require_push_access=False,
            )

            marker = json.dumps(
                {
                    "schema_version": "0.2",
                    "kind": "disposable_repository_lifecycle_probe",
                    "experiment_id": self._experiment_id,
                    "repository_full_name": full_name,
                    "repository_id": repository_id,
                    "credential_model": "github_app_installation_token",
                },
                indent=2,
                sort_keys=True,
            ) + "\n"
            _emit(report, 5, total, "writing the first marker commit with the App installation token")
            subject_client.create_or_update_file(
                owner,
                repository_name,
                self._marker_path,
                message="ACMM: qualify disposable repository App access",
                content=marker,
                branch=None,
            )

            _emit(report, 6, total, "reading the subject-written marker with the controller credential")
            refreshed = self._client.repository_identity(owner, repository_name)
            _verify_probe_identity(
                refreshed,
                expected_full_name=full_name,
                expected_repository_id=repository_id,
                role="controller",
            )
            actual_marker = self._client.read_text_file(
                owner,
                repository_name,
                self._marker_path,
                ref=refreshed.default_branch,
            )
            if actual_marker != marker:
                raise github_controller_error(
                    "Disposable repository lifecycle marker did not round-trip exactly."
                )

            _emit(report, 7, total, "revoking the one-repository installation token")
            self._app_client.revoke(token)
            token = None

            _emit(report, 8, total, "detaching and deleting the exact probe repository")
            self._client.remove_repository_from_app_installation(
                installation_id=self._app_client.installation_id,
                repository_id=repository_id,
            )
            attached = False
            deletion_started = True
            self._delete_exact(owner, repository_name, repository_id)

            _emit(report, 9, total, "verifying repository deletion")
            self._verify_deleted(owner, repository_name)
            return apparatus_action_result(
                changed=True,
                detail=(
                    "qualified disposable repository create/App-attach/token/write/"
                    "revoke/detach/delete lifecycle"
                ),
                observations={
                    "controller_login": controller_login,
                    "credential_model": "github_app_installation_token",
                    "repository": full_name,
                    "repository_id": repository_id,
                    "subject_contents_write": issued.permissions.get("contents") == "write",
                    "subject_write_verified": True,
                    "marker_path": self._marker_path,
                    "token_revoked": True,
                    "installation_detached": True,
                    "deleted": True,
                },
            )
        except Exception as exc:
            cleanup_errors: list[str] = []
            if token is not None:
                try:
                    self._app_client.revoke(token)
                except Exception as cleanup_exc:
                    cleanup_errors.append(f"token revocation: {cleanup_exc}")
            if created is not None and attached:
                try:
                    self._client.remove_repository_from_app_installation(
                        installation_id=self._app_client.installation_id,
                        repository_id=created[2],
                    )
                except Exception as cleanup_exc:
                    cleanup_errors.append(f"App detachment: {cleanup_exc}")
            if created is not None and not deletion_started:
                try:
                    self._delete_exact(*created)
                    self._verify_deleted(created[0], created[1])
                except Exception as cleanup_exc:
                    cleanup_errors.append(f"repository cleanup: {cleanup_exc}")
            if cleanup_errors:
                raise github_controller_error(
                    f"{exc} Safe cleanup also failed: " + "; ".join(cleanup_errors)
                ) from exc
            raise

    def _delete_exact(
        self,
        owner: str,
        name: str,
        repository_id: int,
    ) -> None:
        existing = self._client.repository_optional(owner, name)
        if existing is None:
            return
        current_id = existing.get("id")
        if current_id != repository_id:
            raise github_controller_error(
                f"Refusing deletion of {owner}/{name}: repository id changed from "
                f"{repository_id} to {current_id}."
            )
        self._client.delete_repository(owner, name)

    def _verify_deleted(self, owner: str, name: str) -> None:
        for attempt in range(1, 6):
            if self._client.repository_optional(owner, name) is None:
                return
            if attempt < 5:
                self._client.wait_for_poll(2.0, "repository.read")
        raise github_controller_error(
            f"Deleted probe repository {owner}/{name} remains visible after bounded verification."
        )


def _created_repository_coordinates(
    value: Mapping[str, object],
    *,
    expected_owner: str,
    expected_name: str,
) -> tuple[str, str, int]:
    repository_id = value.get("id")
    full_name = value.get("full_name")
    owner_value = value.get("owner")
    owner = owner_value.get("login") if isinstance(owner_value, Mapping) else None
    name = value.get("name")
    expected_full_name = f"{expected_owner}/{expected_name}"
    if (
        not isinstance(repository_id, int)
        or repository_id <= 0
        or owner != expected_owner
        or name != expected_name
        or full_name != expected_full_name
    ):
        raise github_controller_error(
            "GitHub create-repository response does not match the requested disposable "
            "probe identity."
        )
    return owner, full_name, repository_id


def _verify_probe_identity(
    identity: github_repository_identity,
    *,
    expected_full_name: str,
    expected_repository_id: int,
    role: str,
    require_push_access: bool = True,
) -> None:
    if (
        identity.full_name != expected_full_name
        or identity.repository_id != expected_repository_id
    ):
        raise github_controller_error(
            f"{role.capitalize()} resolved an unexpected disposable repository identity."
        )
    if not identity.private:
        raise github_controller_error(
            f"Disposable repository is not private for the {role} credential."
        )
    if not identity.issues_enabled:
        raise github_controller_error(
            f"Disposable repository has Issues disabled for the {role} credential."
        )
    if require_push_access and not identity.push_allowed:
        raise github_controller_error(
            f"{role.capitalize()} credential does not have push access to the "
            "disposable repository."
        )


def _login(value: Mapping[str, object], role: str) -> str:
    login = value.get("login")
    if not isinstance(login, str) or not login.strip():
        raise github_controller_error(
            f"Authenticated {role} GitHub user response does not contain login."
        )
    return login.strip()


def _emit(
    report: Callable[[apparatus_action_progress], None] | None,
    step: int,
    total: int,
    message: str,
) -> None:
    if report is not None:
        report(apparatus_action_progress(message=message, step=step, total=total))

