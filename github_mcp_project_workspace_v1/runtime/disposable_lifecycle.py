from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any, Mapping
from uuid import uuid4
import zipfile

from acmm.experiment_api import (
    observed_environment,
    prepared_environment,
    runtime_materialization_context,
    runtime_materialization_finalization,
    runtime_run_context,
    runtime_subject_admission_request,
    runtime_run_finalization,
    runtime_session_context,
    runtime_session_finalization,
)

from .api_governor import github_api_usage_delta
from .github_app import github_app_client
from .resource_ledger import github_resource_ledger
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
from .f2 import (
    github_f2_a_materializer,
    github_f2_a_spec,
    github_f2_b_materializer,
    github_f2_b_spec,
)
from .f2_runtime import github_f2_a_fixture, github_f2_b_fixture
from .f3 import (
    github_f3_a_materializer,
    github_f3_a_spec,
    github_f3_b_materializer,
    github_f3_b_spec,
)
from .f3_runtime import github_f3_a_fixture, github_f3_b_fixture
from .f4 import (
    github_f4_a_materializer,
    github_f4_a_spec,
    github_f4_b_materializer,
    github_f4_b_spec,
)
from .f4_runtime import github_f4_a_fixture, github_f4_b_fixture
from .f5 import (
    github_f5_a_materializer,
    github_f5_a_spec,
    github_f5_b_materializer,
    github_f5_b_spec,
)
from .f5_runtime import github_f5_a_fixture, github_f5_b_fixture
from .f6 import (
    github_f6_a_materializer,
    github_f6_a_spec,
    github_f6_b_materializer,
    github_f6_b_spec,
)
from .f6_runtime import github_f6_a_fixture, github_f6_b_fixture


@dataclass
class github_disposable_session:
    owner: str
    session_dir: str
    api_usage_start: Mapping[str, Any]
    active_repositories: dict[int, str] = field(default_factory=dict)
    forensic_archives: list[str] = field(default_factory=list)
    ledger: github_resource_ledger | None = None


@dataclass(frozen=True)
class github_disposable_run_handle:
    identity: github_repository_identity
    fixture: Any
    fixture_handle: Any
    admission_token: str = field(repr=False)
    shared_materialization: bool = False


@dataclass
class github_materialization_handle:
    key: str
    scenario_id: str
    shared: bool
    identity: github_repository_identity | None = None
    fixture: Any = None
    fixture_id: str | None = None
    tainted: bool = False
    retired: bool = False


class github_workspace_disposable_lifecycle:
    def __init__(
        self,
        controller: github_controller_client,
        app_client: github_app_client,
        *,
        experiment_id: str,
        run_name_prefix: str,
        expected_default_branch: str,
        fixture_base_version: str,
        fixture_base_files: tuple[github_fixture_base_file, ...],
        f1_a_spec: github_f1_a_spec,
        f1_b_spec: github_f1_b_spec,
        f2_a_spec: github_f2_a_spec,
        f2_b_spec: github_f2_b_spec,
        f3_a_spec: github_f3_a_spec,
        f3_b_spec: github_f3_b_spec,
        f4_a_spec: github_f4_a_spec | None = None,
        f4_b_spec: github_f4_b_spec | None = None,
        f5_a_spec: github_f5_a_spec | None = None,
        f5_b_spec: github_f5_b_spec | None = None,
        f6_a_spec: github_f6_a_spec | None = None,
        f6_b_spec: github_f6_b_spec | None = None,
        sleep=time.sleep,
    ) -> None:
        self._controller = controller
        self._app_client = app_client
        self._experiment_id = experiment_id
        self._run_name_prefix = run_name_prefix.strip()
        self._expected_default_branch = expected_default_branch
        self._fixture_base_version = fixture_base_version
        self._fixture_base_files = tuple(fixture_base_files)
        self._f1_a_spec = f1_a_spec
        self._f1_b_spec = f1_b_spec
        self._f2_a_spec = f2_a_spec
        self._f2_b_spec = f2_b_spec
        self._f3_a_spec = f3_a_spec
        self._f3_b_spec = f3_b_spec
        self._f4_a_spec = f4_a_spec
        self._f4_b_spec = f4_b_spec
        self._f5_a_spec = f5_a_spec
        self._f5_b_spec = f5_b_spec
        self._f6_a_spec = f6_a_spec
        self._f6_b_spec = f6_b_spec
        self._sleep = sleep

    def session_initialize(self, context: runtime_session_context) -> github_disposable_session:
        set_progress = getattr(self._controller, "set_progress_reporter", None)
        if callable(set_progress):
            set_progress(context.progress)
        api_usage_start = self._api_usage_snapshot()
        controller_login = _login(self._controller.current_user(), "controller")

        stale = self._discover_disposable_repositories()
        if stale:
            names = ", ".join(stale)
            raise github_controller_error(
                "Disposable scientific session is blocked because prior run "
                f"repositories are still discoverable: {names}. Clean the recorded "
                "quarantine before starting another execution."
            )
        return github_disposable_session(
            owner=controller_login,
            session_dir=context.session_dir,
            api_usage_start=api_usage_start,
            ledger=github_resource_ledger(context.session_dir),
        )

    def materialization_initialize(
        self,
        session_handle: github_disposable_session,
        context: runtime_materialization_context,
    ) -> github_materialization_handle:
        if not isinstance(session_handle, github_disposable_session):
            raise TypeError("Disposable GitHub session handle is invalid.")
        if len(context.scenario_ids) != 1:
            raise github_controller_error(
                "GitHub scenario materialization requires exactly one scenario per "
                f"slice; received {context.scenario_ids!r}."
            )

        scenario_id = context.scenario_ids[0]
        # Incremental qualification proceeds fixture-family by fixture-family.
        # F1-A and F1-B now have complete trusted restore/taint implementations.
        # Other scenario slices keep their existing disposable-per-run behavior
        # while exercising the same Core materialization scheduler.
        if scenario_id not in {
            "f1_a_regression_disposition",
            "f1_b_release_candidate_status",
        }:
            return github_materialization_handle(
                key=context.key,
                scenario_id=scenario_id,
                shared=False,
            )

        if session_handle.active_repositories:
            names = ", ".join(sorted(session_handle.active_repositories.values()))
            raise github_controller_error(
                "Cannot initialize shared F1-A materialization while another "
                f"repository remains active: {names}."
            )
        if session_handle.ledger is None:
            raise github_controller_error("GitHub runtime resource ledger is unavailable.")

        repository_name = self._materialization_repository_name(context)
        created = self._controller.create_repository(
            name=repository_name,
            description=(
                f"ACMM scenario materialization for {self._experiment_id}: "
                f"{scenario_id} / {context.key}"
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
        session_handle.ledger.record_repository(
            run_index=context.selected_run_indices[0],
            repository_id=repository_id,
            owner=owner,
            name=repository_name,
            full_name=full_name,
        )
        installation_attached = False

        try:
            controller_identity = self._controller.repository_identity(owner, repository_name)
            _verify_disposable_identity(
                controller_identity,
                expected_full_name=full_name,
                expected_repository_id=repository_id,
                role="controller",
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
                    f"Materialized repository default branch is '{identity.default_branch}'; "
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
                fixture = github_f1_a_fixture(
                    self._controller, materializer, self._f1_a_spec
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
                fixture = github_f1_b_fixture(
                    self._controller, materializer, self._f1_b_spec
                )
                fixture_id = self._f1_b_spec.fixture_id
            materializer.run()

            self._controller.add_repository_to_app_installation(
                installation_id=self._app_client.installation_id,
                repository_id=repository_id,
            )
            installation_attached = True
            session_handle.ledger.update(repository_id, installation_attached=True)
            self._write_api_usage_artifact(session_handle)
            return github_materialization_handle(
                key=context.key,
                scenario_id=scenario_id,
                shared=True,
                identity=identity,
                fixture=fixture,
                fixture_id=fixture_id,
            )
        except (Exception, KeyboardInterrupt) as exc:
            cleanup_errors: list[str] = []
            if installation_attached:
                try:
                    self._controller.remove_repository_from_app_installation(
                        installation_id=self._app_client.installation_id,
                        repository_id=repository_id,
                    )
                    session_handle.ledger.update(
                        repository_id,
                        installation_detached=True,
                    )
                except Exception as cleanup_exc:
                    cleanup_errors.append(f"App detachment: {cleanup_exc}")
            archive_context = self._materialization_archive_context(context)
            archive_path = self._archive_then_delete_failed_repository(
                session_handle,
                archive_context,
                owner=owner,
                repository_name=repository_name,
                full_name=full_name,
                repository_id=repository_id,
                phase="materialization_initialization",
                reason=str(exc) or exc.__class__.__name__,
            )
            self._write_api_usage_artifact(session_handle)
            if isinstance(exc, KeyboardInterrupt):
                raise
            detail = (
                f"Shared materialization repository {full_name} was archived locally "
                f"and deleted after initialization failure: {exc}. "
                f"Forensic archive: {archive_path}"
            )
            if cleanup_errors:
                detail += "; cleanup warnings: " + "; ".join(cleanup_errors)
            raise github_controller_error(detail) from exc

    def materialization_finalize(
        self,
        session_handle: github_disposable_session,
        context: runtime_materialization_context,
        handle: github_materialization_handle | None,
        outcome: runtime_materialization_finalization,
    ) -> Mapping[str, Any]:
        if not isinstance(session_handle, github_disposable_session):
            raise TypeError("Disposable GitHub session handle is invalid.")
        if handle is None or not isinstance(handle, github_materialization_handle):
            return {"shared": False, "retired": False}
        if not handle.shared:
            return {"shared": False, "retired": False}
        if handle.retired:
            return {
                "shared": True,
                "retired": True,
                "tainted": handle.tainted,
            }
        identity = handle.identity
        if identity is None:
            raise github_controller_error(
                f"Shared materialization {context.key} has no repository identity."
            )

        if not outcome.completed:
            handle.tainted = True
            archive_path = self._archive_then_delete_failed_repository(
                session_handle,
                self._materialization_archive_context(context),
                owner=identity.owner,
                repository_name=identity.name,
                full_name=identity.full_name,
                repository_id=identity.repository_id,
                phase="materialization_finalization",
                reason=outcome.detail or (
                    "materialization interrupted"
                    if outcome.interrupted
                    else "materialization did not complete"
                ),
            )
            handle.retired = True
            self._write_api_usage_artifact(session_handle)
            return {
                "shared": True,
                "retired": True,
                "tainted": True,
                "archived": True,
                "forensic_archive": archive_path,
                "repository": identity.full_name,
                "repository_id": identity.repository_id,
            }

        self._retire_materialization_repository(session_handle, handle)
        self._write_api_usage_artifact(session_handle)
        return {
            "shared": True,
            "retired": True,
            "tainted": handle.tainted,
            "repository": identity.full_name,
            "repository_id": identity.repository_id,
        }

    def run_prepare(
        self,
        session_handle: github_disposable_session,
        context: runtime_run_context,
        scenario: dict[str, Any],
        reset: dict[str, Any],
    ) -> prepared_environment:
        if not isinstance(session_handle, github_disposable_session):
            raise TypeError("Disposable GitHub session handle is invalid.")
        materialization_handle = context.materialization_handle
        if (
            isinstance(materialization_handle, github_materialization_handle)
            and materialization_handle.shared
        ):
            return self._prepare_shared_materialization_run(
                session_handle,
                context,
                scenario,
                reset,
                materialization_handle,
            )
        if session_handle.active_repositories:
            names = ", ".join(sorted(session_handle.active_repositories.values()))
            raise github_controller_error(
                "Disposable scientific session already has active run apparatus: "
                f"{names}."
            )
        scenario_id = scenario.get("id")
        if scenario_id not in {
            "f1_a_regression_disposition",
            "f1_b_release_candidate_status",
            "f2_a_incoming_regression_triage",
            "f2_b_stale_work_item_maintenance",
            "f3_a_implementation_provenance",
            "f3_b_reverted_fix_status",
            "f4_a_failing_validation_diagnosis",
            "f4_b_superseded_failure_alert",
            "f5_a_targeted_code_fix",
            "f5_b_release_metadata_sync",
            "f6_a_release_blocker_resolution",
            "f6_b_existing_pr_repair",
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
        if session_handle.ledger is None:
            raise github_controller_error("GitHub runtime resource ledger is unavailable.")
        session_handle.ledger.record_repository(
            run_index=context.run_index,
            repository_id=repository_id,
            owner=owner,
            name=repository_name,
            full_name=full_name,
        )
        issued_token = None
        installation_attached = False

        try:
            controller_identity = self._controller.repository_identity(owner, repository_name)
            _verify_disposable_identity(
                controller_identity,
                expected_full_name=full_name,
                expected_repository_id=repository_id,
                role="controller",
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
                fixture = github_f1_a_fixture(self._controller, materializer, self._f1_a_spec)
                fixture_id = self._f1_a_spec.fixture_id
            elif scenario_id == "f1_b_release_candidate_status":
                materializer = github_f1_b_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f1_b_spec,
                )
                fixture = github_f1_b_fixture(self._controller, materializer, self._f1_b_spec)
                fixture_id = self._f1_b_spec.fixture_id
            elif scenario_id == "f2_a_incoming_regression_triage":
                materializer = github_f2_a_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f2_a_spec,
                )
                fixture = github_f2_a_fixture(self._controller, materializer, self._f2_a_spec)
                fixture_id = self._f2_a_spec.fixture_id
            elif scenario_id == "f2_b_stale_work_item_maintenance":
                materializer = github_f2_b_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f2_b_spec,
                )
                fixture = github_f2_b_fixture(self._controller, materializer, self._f2_b_spec)
                fixture_id = self._f2_b_spec.fixture_id
            elif scenario_id == "f3_a_implementation_provenance":
                materializer = github_f3_a_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f3_a_spec,
                )
                fixture = github_f3_a_fixture(self._controller, materializer, self._f3_a_spec)
                fixture_id = self._f3_a_spec.fixture_id
            elif scenario_id == "f3_b_reverted_fix_status":
                materializer = github_f3_b_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f3_b_spec,
                )
                fixture = github_f3_b_fixture(self._controller, materializer, self._f3_b_spec)
                fixture_id = self._f3_b_spec.fixture_id
            elif scenario_id == "f4_a_failing_validation_diagnosis":
                if self._f4_a_spec is None:
                    raise RuntimeError("F4-A disposable fixture specification is unavailable.")
                materializer = github_f4_a_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f4_a_spec,
                )
                fixture = github_f4_a_fixture(self._controller, materializer, self._f4_a_spec)
                fixture_id = self._f4_a_spec.fixture_id
            elif scenario_id == "f4_b_superseded_failure_alert":
                if self._f4_b_spec is None:
                    raise RuntimeError("F4-B disposable fixture specification is unavailable.")
                materializer = github_f4_b_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f4_b_spec,
                )
                fixture = github_f4_b_fixture(self._controller, materializer, self._f4_b_spec)
                fixture_id = self._f4_b_spec.fixture_id
            elif scenario_id == "f5_a_targeted_code_fix":
                if self._f5_a_spec is None:
                    raise RuntimeError("F5-A disposable fixture specification is unavailable.")
                materializer = github_f5_a_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f5_a_spec,
                )
                fixture = github_f5_a_fixture(self._controller, materializer, self._f5_a_spec)
                fixture_id = self._f5_a_spec.fixture_id
            elif scenario_id == "f5_b_release_metadata_sync":
                if self._f5_b_spec is None:
                    raise RuntimeError("F5-B disposable fixture specification is unavailable.")
                materializer = github_f5_b_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f5_b_spec,
                )
                fixture = github_f5_b_fixture(self._controller, materializer, self._f5_b_spec)
                fixture_id = self._f5_b_spec.fixture_id
            elif scenario_id == "f6_a_release_blocker_resolution":
                if self._f6_a_spec is None:
                    raise RuntimeError("F6-A disposable fixture specification is unavailable.")
                materializer = github_f6_a_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f6_a_spec,
                )
                fixture = github_f6_a_fixture(self._controller, materializer, self._f6_a_spec)
                fixture_id = self._f6_a_spec.fixture_id
            else:
                if self._f6_b_spec is None:
                    raise RuntimeError("F6-B disposable fixture specification is unavailable.")
                materializer = github_f6_b_materializer(
                    self._controller,
                    repository_name=repository_name,
                    expected_repository_full_name=full_name,
                    expected_repository_id=repository_id,
                    expected_default_branch=self._expected_default_branch,
                    fixture_base_files=dynamic_base,
                    spec=self._f6_b_spec,
                )
                fixture = github_f6_b_fixture(self._controller, materializer, self._f6_b_spec)
                fixture_id = self._f6_b_spec.fixture_id
            materializer.run()

            prepared = fixture.prepare(scenario, reset)

            self._controller.add_repository_to_app_installation(
                installation_id=self._app_client.installation_id,
                repository_id=repository_id,
            )
            installation_attached = True
            session_handle.ledger.update(
                repository_id,
                installation_attached=True,
            )
            issued_token = self._app_client.mint_repository_token(
                repository_id=repository_id,
                expected_repository_full_name=full_name,
            )
            session_handle.ledger.update(
                repository_id,
                token_minted=True,
                token_fingerprint=hashlib.sha256(
                    issued_token.token.encode("utf-8")
                ).hexdigest(),
            )
            configuration = dict(prepared.provenance.get("configuration", {}))
            configuration.update(
                {
                    "repository_full_name": full_name,
                    "repository_id": repository_id,
                    "disposable_repository": True,
                    "credential_model": "github_app_installation_token",
                    "installation_id": self._app_client.installation_id,
                }
            )
            return prepared_environment(
                handle=github_disposable_run_handle(
                    identity=identity,
                    fixture=fixture,
                    fixture_handle=prepared.handle,
                    admission_token=issued_token.token,
                ),
                provenance={
                    "fixture": fixture_id,
                    "configuration": configuration,
                },
                evidence=prepared.evidence,
                task_bindings=prepared.task_bindings,
                admission_requests=(
                    runtime_subject_admission_request(
                        integration_id="github_mcp",
                        payload={
                            "access_token": issued_token.token,
                            "repository_id": repository_id,
                            "repository_full_name": full_name,
                            "ledger_path": str(session_handle.ledger.path),
                            "revoke_installation_token": self._app_client.revoke,
                        },
                    ),
                ),
            )
        except (Exception, KeyboardInterrupt) as exc:
            # A first Ctrl+C is a graceful stop request at the Campaign layer.
            # Clean any repository/token state created during preparation, then
            # re-raise KeyboardInterrupt so Core records an interrupted execution
            # rather than converting the stop into a harness error. A second
            # Ctrl+C during cleanup still escapes immediately.
            cleanup_errors: list[str] = []
            if issued_token is not None:
                try:
                    self._app_client.revoke(issued_token.token)
                    session_handle.ledger.update(repository_id, token_revoked=True)
                except Exception as cleanup_exc:
                    cleanup_errors.append(f"token revocation: {cleanup_exc}")
            if installation_attached:
                try:
                    self._controller.remove_repository_from_app_installation(
                        installation_id=self._app_client.installation_id,
                        repository_id=repository_id,
                    )
                    session_handle.ledger.update(
                        repository_id,
                        installation_detached=True,
                    )
                except Exception as cleanup_exc:
                    cleanup_errors.append(f"App detachment: {cleanup_exc}")
            archive_path = self._archive_then_delete_failed_repository(
                session_handle,
                context,
                owner=owner,
                repository_name=repository_name,
                full_name=full_name,
                repository_id=repository_id,
                phase="preparation",
                reason=str(exc) or exc.__class__.__name__,
            )
            self._write_api_usage_artifact(session_handle)
            detail = (
                f"Disposable run repository {full_name} (repository id={repository_id}) "
                "was archived locally and deleted after preparation failure: "
                f"{exc}. Forensic archive: {archive_path}"
            )
            if cleanup_errors:
                detail += "; admission cleanup warnings: " + "; ".join(cleanup_errors)
            if isinstance(exc, KeyboardInterrupt):
                raise
            raise github_controller_error(detail) from exc

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
        if not isinstance(session_handle, github_disposable_session):
            raise TypeError("Disposable GitHub session handle is invalid.")
        if not isinstance(handle, github_disposable_run_handle):
            raise TypeError("Disposable GitHub run handle is invalid.")

        if handle.shared_materialization:
            return self._finalize_shared_materialization_run(
                session_handle,
                context,
                scenario,
                handle,
                reset,
                outcome,
            )

        del scenario
        del reset

        identity = handle.identity
        full_name = identity.full_name
        repository_id = identity.repository_id
        ledger_entry = self._ledger_entry(session_handle, repository_id)
        if (
            ledger_entry.get("token_minted") is True
            and ledger_entry.get("token_revoked") is not True
        ):
            try:
                self._app_client.revoke(handle.admission_token)
                assert session_handle.ledger is not None
                session_handle.ledger.update(repository_id, token_revoked=True)
                ledger_entry = self._ledger_entry(session_handle, repository_id)
            except Exception as exc:
                raise github_controller_error(
                    f"Refusing finalization of {full_name}: subject App token could not "
                    f"be revoked: {exc}"
                ) from exc
        if not outcome.persisted:
            reason = (
                "run evidence was not durably persisted"
                if not outcome.interrupted
                else "run execution was interrupted before durable persistence"
            )
            archive_path = self._archive_then_delete_failed_repository(
                session_handle,
                context,
                owner=identity.owner,
                repository_name=identity.name,
                full_name=full_name,
                repository_id=repository_id,
                phase="finalization",
                reason=reason,
            )
            self._write_api_usage_artifact(session_handle)
            return {
                "deleted": True,
                "quarantined": False,
                "archived": True,
                "forensic_archive": archive_path,
                "repository": full_name,
                "repository_id": repository_id,
                "reason": reason,
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

        self._detach_repository(session_handle, repository_id)
        self._controller.delete_repository(identity.owner, identity.name)
        self._verify_deleted(identity.owner, identity.name)
        session_handle.ledger.update(repository_id, repository_retired=True)
        session_handle.active_repositories.pop(repository_id, None)
        self._write_api_usage_artifact(session_handle)
        return {
            "deleted": True,
            "quarantined": False,
            "repository": full_name,
            "repository_id": repository_id,
        }

    def _prepare_shared_materialization_run(
        self,
        session_handle: github_disposable_session,
        context: runtime_run_context,
        scenario: dict[str, Any],
        reset: dict[str, Any],
        materialization_handle: github_materialization_handle,
    ) -> prepared_environment:
        if materialization_handle.tainted:
            raise github_controller_error(
                f"Refusing run {context.run_index}: shared materialization "
                f"{materialization_handle.key} is tainted."
            )
        if materialization_handle.retired:
            raise github_controller_error(
                f"Refusing run {context.run_index}: shared materialization "
                f"{materialization_handle.key} is already retired."
            )
        if context.scenario_id != materialization_handle.scenario_id:
            raise github_controller_error(
                "Run/materialization scenario mismatch: "
                f"{context.scenario_id} != {materialization_handle.scenario_id}."
            )
        if materialization_handle.scenario_id not in {
            "f1_a_regression_disposition",
            "f1_b_release_candidate_status",
        }:
            raise github_controller_error(
                "This scenario is not qualified for shared scenario materialization."
            )
        identity = materialization_handle.identity
        fixture = materialization_handle.fixture
        if identity is None or fixture is None:
            raise github_controller_error(
                f"Shared materialization {materialization_handle.key} is incomplete."
            )
        if session_handle.ledger is None:
            raise github_controller_error("GitHub runtime resource ledger is unavailable.")

        current = self._controller.repository_identity(identity.owner, identity.name)
        _verify_disposable_identity(
            current,
            expected_full_name=identity.full_name,
            expected_repository_id=identity.repository_id,
            role="controller",
        )
        prepared = fixture.prepare(scenario, reset)

        issued_token = self._app_client.mint_repository_token(
            repository_id=identity.repository_id,
            expected_repository_full_name=identity.full_name,
        )
        session_handle.ledger.update(
            identity.repository_id,
            token_minted=True,
            token_fingerprint=hashlib.sha256(
                issued_token.token.encode("utf-8")
            ).hexdigest(),
            token_revoked=False,
            subject_bound=False,
            subject_unbound=False,
        )
        configuration = dict(prepared.provenance.get("configuration", {}))
        configuration.update(
            {
                "repository_full_name": identity.full_name,
                "repository_id": identity.repository_id,
                "disposable_repository": True,
                "repository_lifetime": "scenario_materialization",
                "materialization_key": materialization_handle.key,
                "credential_model": "github_app_installation_token",
                "installation_id": self._app_client.installation_id,
            }
        )
        return prepared_environment(
            handle=github_disposable_run_handle(
                identity=identity,
                fixture=fixture,
                fixture_handle=prepared.handle,
                admission_token=issued_token.token,
                shared_materialization=True,
            ),
            provenance={
                "fixture": materialization_handle.fixture_id,
                "configuration": configuration,
            },
            evidence=prepared.evidence,
            task_bindings=prepared.task_bindings,
            admission_requests=(
                runtime_subject_admission_request(
                    integration_id="github_mcp",
                    payload={
                        "access_token": issued_token.token,
                        "repository_id": identity.repository_id,
                        "repository_full_name": identity.full_name,
                        "ledger_path": str(session_handle.ledger.path),
                        "revoke_installation_token": self._app_client.revoke,
                    },
                ),
            ),
        )

    def _finalize_shared_materialization_run(
        self,
        session_handle: github_disposable_session,
        context: runtime_run_context,
        scenario: dict[str, Any],
        handle: github_disposable_run_handle,
        reset: dict[str, Any],
        outcome: runtime_run_finalization,
    ) -> Mapping[str, Any]:
        identity = handle.identity
        materialization_handle = context.materialization_handle
        if not isinstance(materialization_handle, github_materialization_handle):
            raise github_controller_error(
                f"Run {context.run_index} lost its shared materialization handle."
            )
        if session_handle.ledger is None:
            raise github_controller_error("GitHub runtime resource ledger is unavailable.")

        ledger_entry = self._ledger_entry(session_handle, identity.repository_id)
        if (
            ledger_entry.get("token_minted") is True
            and ledger_entry.get("token_revoked") is not True
        ):
            try:
                self._app_client.revoke(handle.admission_token)
                session_handle.ledger.update(identity.repository_id, token_revoked=True)
            except Exception as exc:
                materialization_handle.tainted = True
                raise github_controller_error(
                    f"Refusing shared-materialization continuation for {identity.full_name}: "
                    f"subject App token could not be revoked: {exc}"
                ) from exc

        if not outcome.persisted:
            materialization_handle.tainted = True
            reason = (
                "run evidence was not durably persisted"
                if not outcome.interrupted
                else "run execution was interrupted before durable persistence"
            )
            archive_path = self._archive_then_delete_failed_repository(
                session_handle,
                context,
                owner=identity.owner,
                repository_name=identity.name,
                full_name=identity.full_name,
                repository_id=identity.repository_id,
                phase="shared_run_finalization",
                reason=reason,
            )
            materialization_handle.retired = True
            self._write_api_usage_artifact(session_handle)
            return {
                "shared": True,
                "restored": False,
                "tainted": True,
                "retired": True,
                "archived": True,
                "forensic_archive": archive_path,
                "repository": identity.full_name,
                "repository_id": identity.repository_id,
                "reason": reason,
            }

        restoration = handle.fixture.finalize(
            scenario,
            handle.fixture_handle,
            reset,
        )
        restored = (
            isinstance(restoration, Mapping)
            and restoration.get("restored") is True
        )
        if not restored:
            materialization_handle.tainted = True
            reason = (
                "shared scenario materialization could not be restored exactly after "
                f"run {context.run_index}: {restoration!r}"
            )
            archive_path = self._archive_then_delete_failed_repository(
                session_handle,
                context,
                owner=identity.owner,
                repository_name=identity.name,
                full_name=identity.full_name,
                repository_id=identity.repository_id,
                phase="shared_run_restore",
                reason=reason,
            )
            materialization_handle.retired = True
            self._write_api_usage_artifact(session_handle)
            raise github_controller_error(
                f"{reason}. The materialization was archived and retired: {archive_path}"
            )

        self._write_api_usage_artifact(session_handle)
        return {
            "shared": True,
            "restored": True,
            "tainted": False,
            "retired": False,
            "repository": identity.full_name,
            "repository_id": identity.repository_id,
            "restoration": dict(restoration),
        }

    def _retire_materialization_repository(
        self,
        session_handle: github_disposable_session,
        handle: github_materialization_handle,
    ) -> None:
        identity = handle.identity
        if identity is None:
            raise github_controller_error(
                f"Shared materialization {handle.key} has no repository identity."
            )
        current = self._controller.repository_optional(identity.owner, identity.name)
        if current is None:
            raise github_controller_error(
                f"Shared materialization repository {identity.full_name} disappeared "
                "before trusted finalization."
            )
        current_id = current.get("id")
        if current_id != identity.repository_id:
            raise github_controller_error(
                f"Refusing deletion of {identity.full_name}: repository id changed "
                f"from {identity.repository_id} to {current_id}."
            )
        if current.get("private") is not True:
            raise github_controller_error(
                f"Refusing deletion workflow for {identity.full_name}: repository is "
                "no longer private."
            )
        self._detach_repository(session_handle, identity.repository_id)
        self._controller.delete_repository(identity.owner, identity.name)
        self._verify_deleted(identity.owner, identity.name)
        assert session_handle.ledger is not None
        session_handle.ledger.update(
            identity.repository_id,
            repository_retired=True,
        )
        session_handle.active_repositories.pop(identity.repository_id, None)
        handle.retired = True

    def _materialization_archive_context(
        self,
        context: runtime_materialization_context,
    ) -> runtime_run_context:
        return runtime_run_context(
            execution_id=context.execution_id,
            run_index=context.selected_run_indices[0],
            subject_id=(context.subject_ids[0] if context.subject_ids else "materialization"),
            scenario_id=(context.scenario_ids[0] if context.scenario_ids else "materialization"),
            repetition=(context.repetitions[0] if context.repetitions else 0),
            attempt=0,
            materialization_key=context.key,
        )

    def session_finalize(
        self,
        session_handle: github_disposable_session,
        context: runtime_session_context,
        outcome: runtime_session_finalization,
    ) -> Mapping[str, Any]:
        del context
        if not isinstance(session_handle, github_disposable_session):
            raise TypeError("Disposable GitHub session handle is invalid.")
        usage_path, usage = self._write_api_usage_artifact(session_handle)
        set_progress = getattr(self._controller, "set_progress_reporter", None)
        if callable(set_progress):
            set_progress(None)
        return {
            "completed": outcome.completed,
            "interrupted": outcome.interrupted,
            "active_repository_count": len(session_handle.active_repositories),
            "quarantined_repository_count": 0,
            "quarantined_repositories": (),
            "forensic_archive_count": len(session_handle.forensic_archives),
            "forensic_archives": tuple(session_handle.forensic_archives),
            "api_usage_artifact": str(usage_path),
            "api_usage": usage["delta"],
        }

    def _write_api_usage_artifact(
        self,
        session_handle: github_disposable_session,
    ) -> tuple[Path, dict[str, Any]]:
        api_usage_end = self._api_usage_snapshot()
        usage = {
            "schema_version": "0.1",
            "start": dict(session_handle.api_usage_start),
            "end": dict(api_usage_end),
            "delta": github_api_usage_delta(
                session_handle.api_usage_start,
                api_usage_end,
            ),
        }
        usage_path = Path(session_handle.session_dir) / "apparatus_api_usage.json"
        usage_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = usage_path.with_suffix(usage_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(usage, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(usage_path)
        return usage_path, usage

    def _api_usage_snapshot(self) -> Mapping[str, Any]:
        snapshot = getattr(self._controller, "api_usage_snapshot", None)
        if not callable(snapshot):
            return {
                "schema_version": "0.1",
                "metrics": {},
                "routes": {},
                "provider_window": {},
            }
        value = snapshot()
        return dict(value) if isinstance(value, Mapping) else {}

    def _archive_then_delete_failed_repository(
        self,
        session_handle: github_disposable_session,
        context: runtime_run_context,
        *,
        owner: str,
        repository_name: str,
        full_name: str,
        repository_id: int,
        phase: str,
        reason: str,
    ) -> str:
        current = self._controller.repository_optional(owner, repository_name)
        if current is None:
            raise github_controller_error(
                f"Disposable repository {full_name} disappeared before failure-state archival."
            )
        if current.get("id") != repository_id:
            raise github_controller_error(
                f"Refusing failure-state archival/deletion of {full_name}: repository id "
                f"changed from {repository_id} to {current.get('id')}."
            )
        if current.get("private") is not True:
            raise github_controller_error(
                f"Refusing failure-state archival/deletion of {full_name}: repository is "
                "no longer private."
            )

        archive_path = self._write_forensic_archive(
            session_handle,
            context,
            owner=owner,
            repository_name=repository_name,
            full_name=full_name,
            repository_id=repository_id,
            phase=phase,
            reason=reason,
            repository=current,
        )
        try:
            self._detach_repository(session_handle, repository_id)
            self._controller.delete_repository(owner, repository_name)
            self._verify_deleted(owner, repository_name)
            if session_handle.ledger is not None:
                session_handle.ledger.update(
                    repository_id,
                    repository_retired=True,
                )
        except Exception as exc:
            raise github_controller_error(
                f"Forensic archive persisted at {archive_path}, but remote cleanup failed "
                f"for disposable run repository {full_name} "
                f"(repository id={repository_id}): {exc}"
            ) from exc

        session_handle.active_repositories.pop(repository_id, None)
        session_handle.forensic_archives.append(archive_path)
        return archive_path

    def _ledger_entry(
        self,
        session_handle: github_disposable_session,
        repository_id: int,
    ) -> Mapping[str, Any]:
        if session_handle.ledger is None:
            raise github_controller_error("GitHub runtime resource ledger is unavailable.")
        for item in session_handle.ledger.repositories():
            if item.get("repository_id") == repository_id:
                return item
        raise github_controller_error(
            f"GitHub runtime resource ledger has no repository id {repository_id}."
        )

    def _detach_repository(
        self,
        session_handle: github_disposable_session,
        repository_id: int,
    ) -> None:
        if session_handle.ledger is None:
            raise github_controller_error("GitHub runtime resource ledger is unavailable.")
        entry = self._ledger_entry(session_handle, repository_id)
        if entry.get("installation_detached") is True:
            return
        if entry.get("installation_attached") is not True:
            return
        self._controller.remove_repository_from_app_installation(
            installation_id=self._app_client.installation_id,
            repository_id=repository_id,
        )
        session_handle.ledger.update(
            repository_id,
            installation_detached=True,
        )

    def _write_forensic_archive(
        self,
        session_handle: github_disposable_session,
        context: runtime_run_context,
        *,
        owner: str,
        repository_name: str,
        full_name: str,
        repository_id: int,
        phase: str,
        reason: str,
        repository: Mapping[str, Any],
    ) -> str:
        archive_root = Path(session_handle.session_dir) / "apparatus_quarantine"
        archive_root.mkdir(parents=True, exist_ok=True)
        base_name = (
            f"run_{context.run_index:06d}_attempt_{context.attempt}_"
            f"{_slug(context.scenario_id)}_{_slug(context.subject_id)}_"
            f"repo_{repository_id}.zip"
        )
        destination = archive_root / base_name
        temporary = destination.with_suffix(destination.suffix + ".tmp")

        capture_errors: list[dict[str, str]] = []

        def capture(label: str, operation, fallback):
            try:
                return operation()
            except Exception as exc:
                capture_errors.append(
                    {
                        "surface": label,
                        "error": str(exc) or exc.__class__.__name__,
                    }
                )
                return fallback

        branches = capture(
            "branches",
            lambda: tuple(self._controller.list_branches(owner, repository_name)),
            (),
        )
        labels = capture(
            "labels",
            lambda: tuple(self._controller.list_labels(owner, repository_name)),
            (),
        )
        issues = capture(
            "issues",
            lambda: tuple(
                item
                for item in self._controller.list_issues(owner, repository_name)
                if "pull_request" not in item
            ),
            (),
        )
        pulls = capture(
            "pull_requests",
            lambda: tuple(self._controller.list_pull_requests(owner, repository_name)),
            (),
        )
        workflows = capture(
            "workflows",
            lambda: self._controller.list_workflows(owner, repository_name),
            {},
        )
        workflow_runs = capture(
            "workflow_runs",
            lambda: self._controller.list_workflow_runs(owner, repository_name),
            {},
        )
        commits = capture(
            "default_branch_commits",
            lambda: tuple(
                self._controller.list_commits(
                    owner,
                    repository_name,
                    sha=str(repository.get("default_branch") or self._expected_default_branch),
                )
            ),
            (),
        )

        issue_details: dict[str, Any] = {}
        for item in issues:
            number = item.get("number")
            if not isinstance(number, int):
                continue
            issue_details[str(number)] = {
                "issue": capture(
                    f"issue:{number}",
                    lambda number=number: self._controller.issue(owner, repository_name, number),
                    dict(item),
                ),
                "comments": capture(
                    f"issue_comments:{number}",
                    lambda number=number: tuple(
                        self._controller.issue_comments(owner, repository_name, number)
                    ),
                    (),
                ),
            }

        pull_details: dict[str, Any] = {}
        for item in pulls:
            number = item.get("number")
            if not isinstance(number, int):
                continue
            pull_details[str(number)] = {
                "pull_request": capture(
                    f"pull_request:{number}",
                    lambda number=number: self._controller.pull_request(
                        owner, repository_name, number
                    ),
                    dict(item),
                ),
                "reviews": capture(
                    f"pull_request_reviews:{number}",
                    lambda number=number: tuple(
                        self._controller.pull_request_reviews(owner, repository_name, number)
                    ),
                    (),
                ),
                "review_comments": capture(
                    f"pull_request_review_comments:{number}",
                    lambda number=number: tuple(
                        self._controller.pull_request_review_comments(
                            owner, repository_name, number
                        )
                    ),
                    (),
                ),
            }

        branch_archives: dict[str, bytes] = {}
        for item in branches:
            branch_name = item.get("name")
            if not isinstance(branch_name, str) or not branch_name:
                continue
            archived = capture(
                f"repository_archive:{branch_name}",
                lambda branch_name=branch_name: self._controller.repository_archive(
                    owner, repository_name, ref=branch_name
                ),
                None,
            )
            if isinstance(archived, bytes):
                branch_archives[branch_name] = archived

        manifest = {
            "schema_version": "0.1",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "experiment_id": self._experiment_id,
            "execution_id": context.execution_id,
            "run_index": context.run_index,
            "subject_id": context.subject_id,
            "scenario_id": context.scenario_id,
            "repetition": context.repetition,
            "attempt": context.attempt,
            "failure_phase": phase,
            "failure_reason": reason,
            "repository_full_name": full_name,
            "repository_id": repository_id,
            "capture_errors": capture_errors,
        }

        def encoded(value: Any) -> str:
            return json.dumps(value, indent=2, sort_keys=True, default=str) + "\n"

        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", encoded(manifest))
                archive.writestr("github/repository.json", encoded(repository))
                archive.writestr("github/branches.json", encoded(branches))
                archive.writestr("github/labels.json", encoded(labels))
                archive.writestr("github/issues.json", encoded(issues))
                archive.writestr("github/pull_requests.json", encoded(pulls))
                archive.writestr("github/issue_details.json", encoded(issue_details))
                archive.writestr("github/pull_request_details.json", encoded(pull_details))
                archive.writestr("github/default_branch_commits.json", encoded(commits))
                archive.writestr("github/workflows.json", encoded(workflows))
                archive.writestr("github/workflow_runs.json", encoded(workflow_runs))
                for branch_name, payload in sorted(branch_archives.items()):
                    archive.writestr(
                        f"repository_snapshots/{_slug(branch_name)}.zip",
                        payload,
                    )
            temporary.replace(destination)
        except Exception as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise github_controller_error(
                f"Could not persist forensic archive for {full_name}: {exc}"
            ) from exc

        if not destination.is_file() or destination.stat().st_size <= 0:
            raise github_controller_error(
                f"Forensic archive for {full_name} was not durably created."
            )
        return str(destination)

    def _discover_disposable_repositories(self) -> tuple[str, ...]:
        prefix = self._run_name_prefix + "-"
        found: set[str] = set()
        for repository in self._controller.list_repositories():
            name = repository.get("name")
            full_name = repository.get("full_name")
            if (
                isinstance(name, str)
                and name.startswith(prefix)
                and isinstance(full_name, str)
                and full_name
            ):
                found.add(full_name)
        return tuple(sorted(found))

    def _repository_name(self, context: runtime_run_context) -> str:
        scenario_aliases = {
            "f1_a_regression_disposition": "f1-a",
            "f1_b_release_candidate_status": "f1-b",
            "f2_a_incoming_regression_triage": "f2-a",
            "f2_b_stale_work_item_maintenance": "f2-b",
            "f3_a_implementation_provenance": "f3-a",
            "f3_b_reverted_fix_status": "f3-b",
        }
        scenario = scenario_aliases.get(context.scenario_id, _slug(context.scenario_id))
        subject = _slug(context.subject_id.replace("_gpt_oss120b", ""))
        token = uuid4().hex[:8]
        execution_tag = hashlib.sha256(
            context.execution_id.encode("utf-8")
        ).hexdigest()[:8]
        raw = (
            f"{self._run_name_prefix}-{scenario}-{subject}-e{execution_tag}-"
            f"r{context.repetition:02d}-a{context.attempt}-{token}"
        )
        return raw[:96].rstrip("-")

    def _materialization_repository_name(
        self,
        context: runtime_materialization_context,
    ) -> str:
        scenario_aliases = {
            "f1_a_regression_disposition": "f1-a",
            "f1_b_release_candidate_status": "f1-b",
            "f2_a_incoming_regression_triage": "f2-a",
            "f2_b_stale_work_item_maintenance": "f2-b",
            "f3_a_implementation_provenance": "f3-a",
            "f3_b_reverted_fix_status": "f3-b",
        }
        scenario_id = context.scenario_ids[0] if context.scenario_ids else "materialization"
        scenario = scenario_aliases.get(scenario_id, _slug(scenario_id))
        token = uuid4().hex[:8]
        execution_tag = hashlib.sha256(
            context.execution_id.encode("utf-8")
        ).hexdigest()[:8]
        key_tag = hashlib.sha256(context.key.encode("utf-8")).hexdigest()[:8]
        raw = (
            f"{self._run_name_prefix}-{scenario}-e{execution_tag}-"
            f"m{key_tag}-{token}"
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
        with self._controller.git_publish_batch(identity.owner, identity.name):
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
            if controller_value is None:
                return
            if attempt < 5:
                self._controller.wait_for_poll(2.0, "repository.read")
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
