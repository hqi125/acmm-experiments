from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import time
from typing import Any, Mapping
from uuid import uuid4

from acmm.experiment_api import (
    observed_environment,
    prepared_environment,
    runtime_run_context,
    runtime_run_finalization,
    runtime_session_context,
    runtime_session_finalization,
)

from .controller import (
    github_controller_client,
    github_controller_error,
    github_fixture_base_file,
    github_repository_identity,
)
from .f1_a import github_f1_a_materializer, github_f1_a_spec
from .f1_a_runtime import github_f1_a_fixture
from .f1_b import github_f1_b_materializer, github_f1_b_spec
from .f1_b_runtime import github_f1_b_fixture


@dataclass
class github_disposable_session:
    owner: str
    active_repositories: dict[int, str] = field(default_factory=dict)
    quarantined_repositories: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class github_disposable_run_handle:
    identity: github_repository_identity
    fixture: Any
    fixture_handle: Any


class github_workspace_disposable_lifecycle:
    def __init__(
        self,
        controller: github_controller_client,
        subject_client: github_controller_client,
        *,
        experiment_id: str,
        run_name_prefix: str,
        expected_default_branch: str,
        fixture_base_version: str,
        fixture_base_files: tuple[github_fixture_base_file, ...],
        f1_a_spec: github_f1_a_spec,
        f1_b_spec: github_f1_b_spec,
        sleep=time.sleep,
    ) -> None:
        self._controller = controller
        self._subject_client = subject_client
        self._experiment_id = experiment_id
        self._run_name_prefix = run_name_prefix.strip()
        self._expected_default_branch = expected_default_branch
        self._fixture_base_version = fixture_base_version
        self._fixture_base_files = tuple(fixture_base_files)
        self._f1_a_spec = f1_a_spec
        self._f1_b_spec = f1_b_spec
        self._sleep = sleep

    def session_initialize(self, context: runtime_session_context) -> github_disposable_session:
        del context
        controller_login = _login(self._controller.current_user(), "controller")
        subject_login = _login(self._subject_client.current_user(), "subject")
        if controller_login != subject_login:
            raise github_controller_error(
                "Controller and subject credentials must authenticate as the same "
                "GitHub repository owner for disposable scientific runs."
            )
        return github_disposable_session(owner=controller_login)

    def run_prepare(
        self,
        session_handle: github_disposable_session,
        context: runtime_run_context,
        scenario: dict[str, Any],
        reset: dict[str, Any],
    ) -> prepared_environment:
        if not isinstance(session_handle, github_disposable_session):
            raise TypeError("Disposable GitHub session handle is invalid.")
        scenario_id = scenario.get("id")
        if scenario_id not in {
            "f1_a_regression_disposition",
            "f1_b_release_candidate_status",
        }:
            raise RuntimeError(
                f"Scenario '{scenario_id}' has not yet been migrated to the "
                "disposable-repository runtime lifecycle."
            )

        repository_name = self._repository_name(context)
        created = self._controller.create_repository(
            name=repository_name,
            description=(
                f"ACMM disposable scientific run for {self._experiment_id}: "
                f"{context.scenario_id} / {context.subject_id} / repetition "
                f"{context.repetition}"
            ),
            private=True,
            has_issues=True,
            auto_init=False,
        )
        owner, full_name, repository_id = _created_repository_coordinates(
            created,
            expected_owner=session_handle.owner,
            expected_name=repository_name,
        )
        session_handle.active_repositories[repository_id] = full_name

        try:
            controller_identity = self._controller.repository_identity(owner, repository_name)
            subject_identity = self._subject_client.repository_identity(owner, repository_name)
            _verify_disposable_identity(
                controller_identity,
                expected_full_name=full_name,
                expected_repository_id=repository_id,
                role="controller",
            )
            _verify_disposable_identity(
                subject_identity,
                expected_full_name=full_name,
                expected_repository_id=repository_id,
                role="subject",
            )

            dynamic_base = self._dynamic_fixture_base(
                full_name=full_name,
                repository_id=repository_id,
            )
            self._initialize_empty_repository(controller_identity, dynamic_base)

            identity = self._controller.repository_identity(owner, repository_name)
            _verify_disposable_identity(
                identity,
                expected_full_name=full_name,
                expected_repository_id=repository_id,
                role="controller",
            )
            if identity.default_branch != self._expected_default_branch:
                raise github_controller_error(
                    f"Disposable repository default branch is '{identity.default_branch}'; "
                    f"expected '{self._expected_default_branch}'."
                )

            if scenario_id == "f1_a_regression_disposition":
                materializer = github_f1_a_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f1_a_spec,
                )
                materializer.run()
                fixture = github_f1_a_fixture(
                    self._controller,
                    materializer,
                    self._f1_a_spec,
                )
                fixture_id = self._f1_a_spec.fixture_id
            else:
                materializer = github_f1_b_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f1_b_spec,
                )
                materializer.run()
                fixture = github_f1_b_fixture(
                    self._controller,
                    materializer,
                    self._f1_b_spec,
                )
                fixture_id = self._f1_b_spec.fixture_id

            prepared = fixture.prepare(scenario, reset)
            configuration = dict(prepared.provenance.get("configuration", {}))
            configuration.update(
                {
                    "repository_full_name": full_name,
                    "repository_id": repository_id,
                    "disposable_repository": True,
                }
            )
            return prepared_environment(
                handle=github_disposable_run_handle(
                    identity=identity,
                    fixture=fixture,
                    fixture_handle=prepared.handle,
                ),
                provenance={
                    "fixture": fixture_id,
                    "configuration": configuration,
                },
                evidence=prepared.evidence,
                task_bindings=prepared.task_bindings,
            )
        except Exception as exc:
            session_handle.quarantined_repositories[repository_id] = full_name
            raise github_controller_error(
                f"Disposable run repository {full_name} (repository id={repository_id}) "
                f"was quarantined after preparation failure: {exc}"
            ) from exc

    def run_observe(
        self,
        session_handle: github_disposable_session,
        context: runtime_run_context,
        scenario: dict[str, Any],
        handle: github_disposable_run_handle,
    ) -> observed_environment:
        del session_handle
        del context
        if not isinstance(handle, github_disposable_run_handle):
            raise TypeError("Disposable GitHub run handle is invalid.")
        return handle.fixture.observe(scenario, handle.fixture_handle)

    def run_finalize(
        self,
        session_handle: github_disposable_session,
        context: runtime_run_context,
        scenario: dict[str, Any],
        handle: github_disposable_run_handle,
        reset: dict[str, Any],
        outcome: runtime_run_finalization,
    ) -> Mapping[str, Any]:
        del context
        del scenario
        del reset
        if not isinstance(session_handle, github_disposable_session):
            raise TypeError("Disposable GitHub session handle is invalid.")
        if not isinstance(handle, github_disposable_run_handle):
            raise TypeError("Disposable GitHub run handle is invalid.")

        identity = handle.identity
        full_name = identity.full_name
        repository_id = identity.repository_id
        if not outcome.persisted:
            session_handle.quarantined_repositories[repository_id] = full_name
            return {
                "deleted": False,
                "quarantined": True,
                "repository": full_name,
                "repository_id": repository_id,
                "reason": (
                    "run evidence was not durably persisted"
                    if not outcome.interrupted
                    else "run execution was interrupted before durable persistence"
                ),
            }

        current = self._controller.repository_optional(identity.owner, identity.name)
        if current is None:
            raise github_controller_error(
                f"Disposable repository {full_name} disappeared before trusted finalization."
            )
        current_id = current.get("id")
        if current_id != repository_id:
            raise github_controller_error(
                f"Refusing deletion of {full_name}: repository id changed from "
                f"{repository_id} to {current_id}."
            )
        if current.get("private") is not True:
            raise github_controller_error(
                f"Refusing deletion workflow for {full_name}: repository is no longer private."
            )

        self._controller.delete_repository(identity.owner, identity.name)
        self._verify_deleted(identity.owner, identity.name)
        session_handle.active_repositories.pop(repository_id, None)
        session_handle.quarantined_repositories.pop(repository_id, None)
        return {
            "deleted": True,
            "quarantined": False,
            "repository": full_name,
            "repository_id": repository_id,
        }

    def session_finalize(
        self,
        session_handle: github_disposable_session,
        context: runtime_session_context,
        outcome: runtime_session_finalization,
    ) -> Mapping[str, Any]:
        del context
        if not isinstance(session_handle, github_disposable_session):
            raise TypeError("Disposable GitHub session handle is invalid.")
        return {
            "completed": outcome.completed,
            "interrupted": outcome.interrupted,
            "active_repository_count": len(session_handle.active_repositories),
            "quarantined_repository_count": len(session_handle.quarantined_repositories),
            "quarantined_repositories": tuple(
                sorted(session_handle.quarantined_repositories.values())
            ),
        }

    def _repository_name(self, context: runtime_run_context) -> str:
        scenario_aliases = {
            "f1_a_regression_disposition": "f1-a",
            "f1_b_release_candidate_status": "f1-b",
        }
        scenario = scenario_aliases.get(context.scenario_id, _slug(context.scenario_id))
        subject = _slug(context.subject_id.replace("_gpt_oss120b", ""))
        token = uuid4().hex[:8]
        raw = (
            f"{self._run_name_prefix}-{scenario}-{subject}-"
            f"r{context.repetition:02d}-a{context.attempt}-{token}"
        )
        return raw[:96].rstrip("-")

    def _dynamic_fixture_base(
        self,
        *,
        full_name: str,
        repository_id: int,
    ) -> tuple[github_fixture_base_file, ...]:
        result: list[github_fixture_base_file] = []
        marker_seen = False
        for item in self._fixture_base_files:
            if item.path == ".acmm/fixture-base.json":
                marker_seen = True
                content = json.dumps(
                    {
                        "schema_version": "0.1",
                        "fixture_base_version": self._fixture_base_version,
                        "experiment_id": self._experiment_id,
                        "repository_full_name": full_name,
                        "repository_id": repository_id,
                    },
                    indent=2,
                ) + "\n"
                result.append(github_fixture_base_file(path=item.path, content=content))
            else:
                result.append(item)
        if not marker_seen:
            raise github_controller_error(
                "Trusted fixture base does not declare .acmm/fixture-base.json."
            )
        return tuple(result)

    def _initialize_empty_repository(
        self,
        identity: github_repository_identity,
        files: tuple[github_fixture_base_file, ...],
    ) -> None:
        for index, item in enumerate(files):
            self._controller.create_or_update_file(
                identity.owner,
                identity.name,
                item.path,
                message=f"ACMM: initialize disposable fixture base ({item.path})",
                content=item.content,
                branch=(None if index == 0 else self._expected_default_branch),
            )
        for item in files:
            actual = self._controller.read_text_file(
                identity.owner,
                identity.name,
                item.path,
                ref=self._expected_default_branch,
            )
            if actual != item.content:
                raise github_controller_error(
                    f"Disposable fixture base file '{item.path}' failed exact verification."
                )

    def _verify_deleted(self, owner: str, name: str) -> None:
        for attempt in range(1, 6):
            controller_value = self._controller.repository_optional(owner, name)
            subject_value = self._subject_client.repository_optional(owner, name)
            if controller_value is None and subject_value is None:
                return
            if attempt < 5:
                self._sleep(0.5)
        raise github_controller_error(
            f"Deleted disposable repository {owner}/{name} remains visible after "
            "bounded verification."
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
            "scientific-run identity."
        )
    if value.get("private") is not True:
        raise github_controller_error(
            "Disposable scientific-run repository was not created private."
        )
    return owner, full_name, repository_id


def _verify_disposable_identity(
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


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "run"
