from __future__ import annotations

import json
from time import sleep as _sleep
from typing import Callable, Mapping
from uuid import uuid4

from acmm.experiment_api import apparatus_action_progress, apparatus_action_result

from .controller import (
    github_api_error,
    github_controller_client,
    github_controller_error,
    github_fixture_base_file,
    github_repository_identity,
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

class github_disposable_repository_lifecycle_qualifier:
    description = (
        "Qualify private disposable repository create/access/write/delete behavior."
    )
    mutates_external_state = True

    def __init__(
        self,
        controller_client: github_controller_client,
        subject_client: github_controller_client,
        *,
        credentials_distinct: bool,
        experiment_id: str,
        probe_name_prefix: str,
        marker_path: str = ".acmm/lifecycle-probe.json",
        sleep: Callable[[float], None] = _sleep,
    ) -> None:
        if not probe_name_prefix.strip():
            raise ValueError("Disposable repository probe prefix must not be empty.")
        self._client = controller_client
        self._subject_client = subject_client
        self._credentials_distinct = credentials_distinct
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
        total = 7
        _emit(report, 1, total, "verifying controller/subject credential identities")
        if not self._credentials_distinct:
            raise github_controller_error(
                "Controller and subject credentials must remain distinct for the "
                "disposable-repository lifecycle probe."
            )
        controller_login = _login(self._client.current_user(), "controller")
        subject_login = _login(self._subject_client.current_user(), "subject")
        if controller_login != subject_login:
            raise github_controller_error(
                "Controller and subject credentials authenticate as different GitHub "
                "accounts; disposable run repositories require one shared owner."
            )

        repository_name = self._name_factory()
        description = (
            f"ACMM disposable repository lifecycle probe for {self._experiment_id}"
        )
        created: tuple[str, str, int] | None = None
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

            _emit(report, 3, total, "verifying controller and subject access to the new repository")
            controller_identity = self._client.repository_identity(owner, repository_name)
            subject_identity = self._subject_client.repository_identity(owner, repository_name)
            _verify_probe_identity(
                controller_identity,
                expected_full_name=full_name,
                expected_repository_id=repository_id,
                role="controller",
            )
            _verify_probe_identity(
                subject_identity,
                expected_full_name=full_name,
                expected_repository_id=repository_id,
                role="subject",
            )

            marker = json.dumps(
                {
                    "schema_version": "0.1",
                    "kind": "disposable_repository_lifecycle_probe",
                    "experiment_id": self._experiment_id,
                    "repository_full_name": full_name,
                    "repository_id": repository_id,
                },
                indent=2,
                sort_keys=True,
            ) + "\n"
            _emit(report, 4, total, "writing the first marker commit with the subject credential")
            self._subject_client.create_or_update_file(
                owner,
                repository_name,
                self._marker_path,
                message="ACMM: qualify disposable repository subject access",
                content=marker,
                branch=None,
            )

            _emit(report, 5, total, "reading the subject-written marker with the controller credential")
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

            _emit(report, 6, total, "deleting the exact probe repository with the controller credential")
            deletion_started = True
            self._delete_exact(owner, repository_name, repository_id)

            _emit(report, 7, total, "verifying repository deletion from both credentials")
            self._verify_deleted(owner, repository_name)
            return apparatus_action_result(
                changed=True,
                detail=(
                    "qualified disposable repository create/access/write/delete lifecycle"
                ),
                observations={
                    "controller_login": controller_login,
                    "subject_login": subject_login,
                    "repository": full_name,
                    "repository_id": repository_id,
                    "subject_push_access": subject_identity.push_allowed,
                    "marker_path": self._marker_path,
                    "deleted": True,
                },
            )
        except Exception as exc:
            cleanup_error: Exception | None = None
            if created is not None and not deletion_started:
                try:
                    self._delete_exact(*created)
                    self._verify_deleted(created[0], created[1])
                except Exception as cleanup_exc:
                    cleanup_error = cleanup_exc
            if cleanup_error is not None:
                raise github_controller_error(
                    f"{exc} Safe cleanup of the created probe repository also failed: "
                    f"{cleanup_error}"
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
            controller_value = self._client.repository_optional(owner, name)
            subject_value = self._subject_client.repository_optional(owner, name)
            if controller_value is None and subject_value is None:
                return
            if attempt < 5:
                self._sleep(0.5)
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
    if not identity.push_allowed:
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

