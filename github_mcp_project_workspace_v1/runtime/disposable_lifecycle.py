from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import signal
import threading
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
    runtime_run_recovery_error,
    runtime_run_recovery_result,
    runtime_subject_admission_request,
    runtime_run_finalization,
    runtime_session_context,
    runtime_session_finalization,
)

from .api_governor import github_api_usage_delta
from .mcp_usage import github_mcp_usage_delta, github_mcp_usage_reader
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
from .f6_runtime import github_f6_a_fixture, github_f6_b_fixture, github_f6_b_slice_fixture


@contextmanager
def _defer_sigint_during_cleanup(enabled: bool = True):
    """Prevent a later Ctrl+C from tearing through package-owned cleanup."""

    if (
        not enabled
        or threading.current_thread() is not threading.main_thread()
        or not hasattr(signal, "SIGINT")
    ):
        yield
        return

    previous = signal.getsignal(signal.SIGINT)
    if previous not in (signal.default_int_handler, signal.SIG_DFL):
        # A higher lifecycle layer (notably Core interruption cleanup) already
        # owns SIGINT semantics. Preserve that handler instead of shadowing its
        # cooperative force-request state.
        yield
        return

    def _defer(_signum, _frame):
        return None

    try:
        signal.signal(signal.SIGINT, _defer)
    except (ValueError, OSError):
        yield
        return

    try:
        yield
    finally:
        try:
            signal.signal(signal.SIGINT, previous)
        except (ValueError, OSError):
            pass


@dataclass
class github_disposable_session:
    owner: str
    session_dir: str
    api_usage_start: Mapping[str, Any]
    mcp_usage_start: Mapping[str, Any]
    active_repositories: dict[int, str] = field(default_factory=dict)
    forensic_archives: list[str] = field(default_factory=list)
    diagnostic_snapshots: list[str] = field(default_factory=list)
    ledger: github_resource_ledger | None = None


@dataclass(frozen=True)
class github_disposable_run_handle:
    identity: github_repository_identity
    fixture: Any
    fixture_handle: Any
    admission_token: str = field(repr=False)
    shared_materialization: bool = False
    diagnostic_snapshots: tuple[str, ...] = ()


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
        run_admission_pressure_features: Mapping[str, float] | None = None,
        mcp_usage: github_mcp_usage_reader | None = None,
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
        self._run_admission_pressure_features = dict(
            run_admission_pressure_features or {}
        )
        self._mcp_usage = mcp_usage
        self._sleep = sleep

    def session_initialize(self, context: runtime_session_context) -> github_disposable_session:
        set_progress = getattr(self._controller, "set_progress_reporter", None)
        if callable(set_progress):
            set_progress(context.progress)
        api_usage_start = self._api_usage_snapshot()
        mcp_usage_start = self._mcp_usage_snapshot()
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
            mcp_usage_start=mcp_usage_start,
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
        supported = {
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
        }
        if scenario_id not in supported:
            raise github_controller_error(
                f"Scenario '{scenario_id}' is not qualified for scenario-slice materialization."
            )
        if session_handle.active_repositories:
            names = ", ".join(sorted(session_handle.active_repositories.values()))
            raise github_controller_error(
                "Cannot initialize scenario materialization while another repository "
                f"remains active: {names}."
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
            preparation_mode="scenario_slice",
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

            # F5/F6 contribute their remote-independent commits to the same initial
            # publication phase as the generic fixture base. F1-F4 retain their
            # already-qualified materializers unchanged.
            components = None
            publication_seed = None
            if scenario_id in {
                "f5_a_targeted_code_fix",
                "f5_b_release_metadata_sync",
                "f6_a_release_blocker_resolution",
                "f6_b_existing_pr_repair",
            }:
                components = self._scenario_fixture_components(
                    scenario_id=scenario_id,
                    repository_name=repository_name,
                    full_name=full_name,
                    repository_id=repository_id,
                    dynamic_base=dynamic_base,
                )
                publication_seed = getattr(components[0], "seed_initial_publication", None)
                if not callable(publication_seed):
                    raise github_controller_error(
                        f"Scenario '{scenario_id}' does not expose an initial publication seed."
                    )

            self._initialize_empty_repository(
                controller_identity,
                dynamic_base,
                publication_seed=publication_seed,
            )
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

            if components is None:
                components = self._scenario_fixture_components(
                    scenario_id=scenario_id,
                    repository_name=repository_name,
                    full_name=full_name,
                    repository_id=repository_id,
                    dynamic_base=dynamic_base,
                )
            materializer, fixture, fixture_id = components
            if scenario_id == "f6_b_existing_pr_repair":
                materializer.ensure_slice_base()
            else:
                materializer.run()

            self._controller.add_repository_to_app_installation(
                installation_id=self._app_client.installation_id,
                repository_id=repository_id,
            )
            installation_attached = True
            session_handle.ledger.update(
                repository_id,
                installation_attached=True,
                preparation_state="ready",
            )
            self._write_api_usage_artifact(session_handle)
            return github_materialization_handle(
                key=context.key,
                scenario_id=scenario_id,
                shared=True,
                identity=identity,
                fixture=fixture,
                fixture_id=fixture_id,
            )
        except BaseException as exc:
            cleanup_errors: list[str] = []
            archive_context = self._materialization_archive_context(context)
            try:
                with _defer_sigint_during_cleanup():
                    if installation_attached:
                        try:
                            self._controller.remove_repository_from_app_installation(
                                installation_id=self._app_client.installation_id,
                                repository_id=repository_id,
                            )
                            session_handle.ledger.update(
                                repository_id, installation_detached=True
                            )
                        except BaseException as cleanup_exc:
                            cleanup_errors.append(f"App detachment: {cleanup_exc}")
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
            except BaseException as cleanup_exc:
                if isinstance(cleanup_exc, KeyboardInterrupt):
                    raise
                if isinstance(exc, KeyboardInterrupt):
                    raise
                detail = (
                    f"Scenario materialization initialization failed for {full_name} "
                    f"({exc}), and trusted retirement could not be established: "
                    f"{cleanup_exc}"
                )
                raise runtime_run_recovery_error(
                    runtime_run_recovery_result(
                        safe_to_continue=False,
                        materialization_reusable=False,
                        retryable=False,
                        detail=detail,
                        observations={
                            "phase": "materialization_initialization",
                            "repository": full_name,
                            "repository_id": repository_id,
                        },
                    )
                ) from cleanup_exc
            if isinstance(exc, KeyboardInterrupt):
                raise
            detail = (
                f"Scenario materialization repository {full_name} was archived locally "
                f"and deleted after initialization failure: {exc}. "
                f"Forensic archive: {archive_path}"
            )
            if cleanup_errors:
                detail += "; cleanup warnings: " + "; ".join(cleanup_errors)
            raise runtime_run_recovery_error(
                runtime_run_recovery_result(
                    safe_to_continue=True,
                    materialization_reusable=False,
                    retryable=False,
                    detail=detail,
                    observations={
                        "phase": "materialization_initialization",
                        "repository": full_name,
                        "repository_id": repository_id,
                        "forensic_archive": archive_path,
                        "retired": True,
                    },
                )
            ) from exc

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
        if not (
            isinstance(materialization_handle, github_materialization_handle)
            and materialization_handle.shared
        ):
            raise github_controller_error(
                "GitHub scientific runs require a scenario-slice materialization. "
                "Per-run repository creation is intentionally unsupported."
            )
        return self._prepare_shared_materialization_run(
            session_handle,
            context,
            scenario,
            reset,
            materialization_handle,
        )

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
        if not handle.shared_materialization:
            raise github_controller_error(
                "Per-run GitHub repository finalization is intentionally unsupported; "
                "the run must belong to a scenario materialization slice."
            )
        return self._finalize_shared_materialization_run(
            session_handle,
            context,
            scenario,
            handle,
            reset,
            outcome,
        )

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
        prepare_for_run = getattr(fixture, "prepare_for_run", None)
        run_fixture = fixture
        prepared = None
        diagnostic_snapshots: tuple[str, ...] = ()
        issued_token = None
        try:
            # Run-scoped fixture preparation is part of the guarded preparation
            # transaction. Some fixtures create provider-visible state before a
            # prepared_environment exists, so failures here must enter the same
            # restoration/retirement path as later preparation failures.
            if callable(prepare_for_run):
                run_fixture, prepared = prepare_for_run(scenario, reset, context)
            else:
                prepared = fixture.prepare(scenario, reset)

            if context.capture_environment_snapshots:
                pre_snapshot = self._write_diagnostic_snapshot(
                    session_handle,
                    context,
                    owner=identity.owner,
                    repository_name=identity.name,
                    full_name=identity.full_name,
                    repository_id=identity.repository_id,
                    phase="pre_run",
                )
                session_handle.diagnostic_snapshots.append(pre_snapshot)
                diagnostic_snapshots = (pre_snapshot,)

            # The active logical run owns Core's synchronous Provider Gate. App token
            # minting therefore enters Event PPH/APP through the same transport path as
            # every other trusted-controller request; do not wrap it in the legacy
            # callback watchdog or it would be admitted twice.
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
                    "repository_lifetime": "scenario_slice",
                    "materialization_key": materialization_handle.key,
                    "credential_model": "github_app_installation_token",
                    "installation_id": self._app_client.installation_id,
                }
            )
            return prepared_environment(
                handle=github_disposable_run_handle(
                    identity=identity,
                    fixture=run_fixture,
                    fixture_handle=prepared.handle,
                    admission_token=issued_token.token,
                    shared_materialization=True,
                    diagnostic_snapshots=diagnostic_snapshots,
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
        except BaseException as exc:
            cleanup_errors: list[str] = []
            with _defer_sigint_during_cleanup():
                if issued_token is not None:
                    try:
                        self._app_client.revoke(issued_token.token)
                        try:
                            session_handle.ledger.update(
                                identity.repository_id,
                                token_revoked=True,
                            )
                        except BaseException as ledger_exc:
                            cleanup_errors.append(
                                "resource ledger could not record prepare-failure token "
                                f"revocation: {ledger_exc}"
                            )
                    except BaseException as revoke_exc:
                        cleanup_errors.append(
                            f"prepare-failure App token revocation failed: {revoke_exc}"
                        )

                try:
                    if prepared is not None:
                        restoration = run_fixture.finalize(
                            scenario,
                            prepared.handle,
                            reset,
                        )
                    else:
                        cleanup_failed_prepare = getattr(
                            fixture,
                            "cleanup_failed_prepare",
                            None,
                        )
                        if callable(cleanup_failed_prepare):
                            restoration = cleanup_failed_prepare(
                                scenario,
                                reset,
                                context,
                            )
                        else:
                            restoration = {
                                "restored": False,
                                "detail": (
                                    "fixture preparation failed before a run handle "
                                    "existed and the fixture provides no "
                                    "cleanup_failed_prepare hook"
                                ),
                            }
                except BaseException as restore_exc:
                    if isinstance(restore_exc, KeyboardInterrupt):
                        raise
                    restoration = {
                        "restored": False,
                        "detail": str(restore_exc) or restore_exc.__class__.__name__,
                    }
                if not (
                    isinstance(restoration, Mapping)
                    and restoration.get("restored") is True
                ):
                    cleanup_errors.append(
                        "prepare-failure fixture restoration did not re-establish the "
                        f"shared-run invariant: {restoration!r}"
                    )

            if cleanup_errors:
                materialization_handle.tainted = True
                try:
                    archive_path = self._archive_then_delete_failed_repository(
                        session_handle,
                        context,
                        owner=identity.owner,
                        repository_name=identity.name,
                        full_name=identity.full_name,
                        repository_id=identity.repository_id,
                        phase="shared_run_prepare",
                        reason="; ".join(cleanup_errors),
                    )
                except BaseException as archive_exc:
                    if isinstance(archive_exc, KeyboardInterrupt):
                        raise
                    if isinstance(exc, KeyboardInterrupt):
                        raise
                    detail = (
                        f"Run {context.run_index} preparation failed ({exc}); cleanup "
                        "could not re-establish the shared-run invariant and trusted "
                        f"materialization retirement also failed: {archive_exc}"
                    )
                    raise runtime_run_recovery_error(
                        runtime_run_recovery_result(
                            safe_to_continue=False,
                            materialization_reusable=False,
                            retryable=False,
                            detail=detail,
                            observations={
                                "phase": "shared_run_prepare",
                                "repository": identity.full_name,
                                "repository_id": identity.repository_id,
                            },
                        )
                    ) from archive_exc
                materialization_handle.retired = True
                if isinstance(exc, KeyboardInterrupt):
                    raise
                detail = (
                    f"Run {context.run_index} preparation failed ({exc}); cleanup could "
                    f"not re-establish the shared-run invariant. The materialization "
                    f"was archived and retired: {archive_path}. Cleanup detail: "
                    + "; ".join(cleanup_errors)
                )
                raise runtime_run_recovery_error(
                    runtime_run_recovery_result(
                        safe_to_continue=True,
                        materialization_reusable=False,
                        retryable=False,
                        detail=detail,
                        observations={
                            "phase": "shared_run_prepare",
                            "repository": identity.full_name,
                            "repository_id": identity.repository_id,
                            "forensic_archive": archive_path,
                            "retired": True,
                        },
                    )
                ) from exc
            raise

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
            except BaseException as exc:
                if isinstance(exc, KeyboardInterrupt):
                    raise
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
                "continuation_safe": True,
                "materialization_reusable": False,
                "retryable": False,
                "recovery_detail": reason,
                "forensic_archive": archive_path,
                "repository": identity.full_name,
                "repository_id": identity.repository_id,
                "reason": reason,
            }

        try:
            restoration = handle.fixture.finalize(
                scenario,
                handle.fixture_handle,
                reset,
            )
        except BaseException as restore_exc:
            if isinstance(restore_exc, KeyboardInterrupt):
                raise
            restoration = {
                "restored": False,
                "detail": str(restore_exc) or restore_exc.__class__.__name__,
                "exception_type": restore_exc.__class__.__name__,
            }
        restored = (
            isinstance(restoration, Mapping)
            and restoration.get("restored") is True
        )
        if not restored:
            materialization_handle.tainted = True
            reason = (
                "shared scenario materialization could not be restored exactly to its declared shared-run invariant after "
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
            return {
                "shared": True,
                "restored": False,
                "tainted": True,
                "retired": True,
                "archived": True,
                "continuation_safe": True,
                "materialization_reusable": False,
                "retryable": False,
                "recovery_detail": reason,
                "forensic_archive": archive_path,
                "repository": identity.full_name,
                "repository_id": identity.repository_id,
                "restoration": (
                    dict(restoration)
                    if isinstance(restoration, Mapping)
                    else restoration
                ),
            }

        diagnostic_snapshots = list(handle.diagnostic_snapshots)
        if context.capture_environment_snapshots:
            post_snapshot = self._write_diagnostic_snapshot(
                session_handle,
                context,
                owner=identity.owner,
                repository_name=identity.name,
                full_name=identity.full_name,
                repository_id=identity.repository_id,
                phase="post_restore",
            )
            session_handle.diagnostic_snapshots.append(post_snapshot)
            diagnostic_snapshots.append(post_snapshot)

        self._write_api_usage_artifact(session_handle)
        return {
            "shared": True,
            "restored": True,
            "tainted": False,
            "retired": False,
            "repository": identity.full_name,
            "repository_id": identity.repository_id,
            "restoration": dict(restoration),
            "diagnostic_snapshots": tuple(diagnostic_snapshots),
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
        if not isinstance(session_handle, github_disposable_session):
            raise TypeError("Disposable GitHub session handle is invalid.")

        sweep_errors: list[str] = []
        if session_handle.active_repositories:
            if outcome.completed:
                names = ", ".join(
                    sorted(session_handle.active_repositories.values())
                )
                raise github_controller_error(
                    "Completed GitHub lifecycle session still owns active "
                    f"repository materialization(s): {names}."
                )

            for repository_id, full_name in list(
                session_handle.active_repositories.items()
            ):
                if "/" not in full_name:
                    sweep_errors.append(
                        f"repository id {repository_id}: malformed full name {full_name!r}"
                    )
                    continue
                owner, repository_name = full_name.split("/", 1)
                cleanup_context = runtime_run_context(
                    execution_id=context.execution_id,
                    run_index=(
                        int(context.selected_run_indices[0])
                        if context.selected_run_indices
                        else 0
                    ),
                    subject_id="session_cleanup",
                    scenario_id="session_cleanup",
                    repetition=0,
                    attempt=0,
                    materialization_key="session_cleanup",
                )
                try:
                    self._archive_then_delete_failed_repository(
                        session_handle,
                        cleanup_context,
                        owner=owner,
                        repository_name=repository_name,
                        full_name=full_name,
                        repository_id=repository_id,
                        phase="session_finalization_sweep",
                        reason=(
                            outcome.detail
                            or (
                                "interrupted session finalization sweep"
                                if outcome.interrupted
                                else "failed session finalization sweep"
                            )
                        ),
                    )
                except BaseException as exc:
                    if isinstance(exc, KeyboardInterrupt):
                        raise
                    sweep_errors.append(
                        f"{full_name} (repository id={repository_id}): {exc}"
                    )

        usage_path, usage = self._write_api_usage_artifact(session_handle)
        mcp_usage_path = Path(session_handle.session_dir) / "mcp_subject_api_usage.json"
        mcp_usage = json.loads(mcp_usage_path.read_text(encoding="utf-8"))
        set_progress = getattr(self._controller, "set_progress_reporter", None)
        if callable(set_progress):
            set_progress(None)
        result = {
            "completed": outcome.completed,
            "interrupted": outcome.interrupted,
            "active_repository_count": len(session_handle.active_repositories),
            "quarantined_repository_count": 0,
            "quarantined_repositories": (),
            "forensic_archive_count": len(session_handle.forensic_archives),
            "forensic_archives": tuple(session_handle.forensic_archives),
            "diagnostic_snapshot_count": len(session_handle.diagnostic_snapshots),
            "diagnostic_snapshots": tuple(session_handle.diagnostic_snapshots),
            "api_usage_artifact": str(usage_path),
            "api_usage": usage["delta"],
            "mcp_subject_api_usage_artifact": str(mcp_usage_path),
            "mcp_subject_api_usage": mcp_usage["delta"],
        }
        if sweep_errors:
            result["cleanup_warnings"] = tuple(sweep_errors)
            raise github_controller_error(
                "GitHub lifecycle session cleanup sweep could not retire all active "
                "repositories: " + "; ".join(sweep_errors)
            )
        return result

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
        try:
            temporary.write_text(
                json.dumps(usage, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(usage_path)
        except BaseException:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        self._write_mcp_usage_artifact(session_handle)
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

    def _write_mcp_usage_artifact(
        self,
        session_handle: github_disposable_session,
    ) -> tuple[Path, dict[str, Any]]:
        end = self._mcp_usage_snapshot()
        usage = {
            "schema_version": "0.1",
            "plane": "subject_mcp",
            "start": dict(session_handle.mcp_usage_start),
            "end": dict(end),
            "delta": github_mcp_usage_delta(session_handle.mcp_usage_start, end),
        }
        usage_path = Path(session_handle.session_dir) / "mcp_subject_api_usage.json"
        usage_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = usage_path.with_suffix(usage_path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(usage, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(usage_path)
        except BaseException:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return usage_path, usage

    def _mcp_usage_snapshot(self) -> Mapping[str, Any]:
        if self._mcp_usage is None:
            return {
                "schema_version": "0.1",
                "observed_at": time.time(),
                "available": False,
                "metrics": {},
                "method_counts": {},
                "state": {},
            }
        return dict(self._mcp_usage.snapshot())

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
        except BaseException as exc:
            if isinstance(exc, KeyboardInterrupt):
                raise
            raise github_controller_error(
                f"Forensic archive persisted at {archive_path}, but remote cleanup failed "
                f"for disposable scenario repository {full_name} "
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
        return self._write_repository_archive(
            session_handle,
            context,
            owner=owner,
            repository_name=repository_name,
            full_name=full_name,
            repository_id=repository_id,
            archive_root_name="apparatus_quarantine",
            capture_kind="failure_forensics",
            capture_phase=phase,
            failure_reason=reason,
            strict_capture=False,
            repository=repository,
        )

    def _write_diagnostic_snapshot(
        self,
        session_handle: github_disposable_session,
        context: runtime_run_context,
        *,
        owner: str,
        repository_name: str,
        full_name: str,
        repository_id: int,
        phase: str,
    ) -> str:
        current = self._controller.repository_optional(owner, repository_name)
        if current is None:
            raise github_controller_error(
                f"Diagnostic repository snapshot cannot find {full_name}."
            )
        if current.get("id") != repository_id:
            raise github_controller_error(
                f"Refusing diagnostic snapshot of {full_name}: repository id changed "
                f"from {repository_id} to {current.get('id')}."
            )
        if current.get("private") is not True:
            raise github_controller_error(
                f"Refusing diagnostic snapshot of {full_name}: repository is no longer private."
            )
        return self._write_repository_archive(
            session_handle,
            context,
            owner=owner,
            repository_name=repository_name,
            full_name=full_name,
            repository_id=repository_id,
            archive_root_name="repository_diagnostics",
            capture_kind="diagnostic",
            capture_phase=phase,
            failure_reason=None,
            strict_capture=True,
            repository=current,
        )

    def _write_repository_archive(
        self,
        session_handle: github_disposable_session,
        context: runtime_run_context,
        *,
        owner: str,
        repository_name: str,
        full_name: str,
        repository_id: int,
        archive_root_name: str,
        capture_kind: str,
        capture_phase: str,
        failure_reason: str | None,
        strict_capture: bool,
        repository: Mapping[str, Any],
    ) -> str:
        traffic_purpose = (
            "diagnostic_snapshot"
            if capture_kind == "diagnostic"
            else "forensic_archive"
        )
        with self._controller.provider_traffic_scope(
            {
                "traffic_purpose": traffic_purpose,
                "capture_kind": capture_kind,
                "capture_phase": capture_phase,
                "run_index": context.run_index,
                "scenario_id": context.scenario_id,
                "subject_id": context.subject_id,
            }
        ):
            return self._write_repository_archive_scoped(
                session_handle,
                context,
                owner=owner,
                repository_name=repository_name,
                full_name=full_name,
                repository_id=repository_id,
                archive_root_name=archive_root_name,
                capture_kind=capture_kind,
                capture_phase=capture_phase,
                failure_reason=failure_reason,
                strict_capture=strict_capture,
                repository=repository,
            )

    def _write_repository_archive_scoped(
        self,
        session_handle: github_disposable_session,
        context: runtime_run_context,
        *,
        owner: str,
        repository_name: str,
        full_name: str,
        repository_id: int,
        archive_root_name: str,
        capture_kind: str,
        capture_phase: str,
        failure_reason: str | None,
        strict_capture: bool,
        repository: Mapping[str, Any],
    ) -> str:
        archive_root = Path(session_handle.session_dir) / archive_root_name
        archive_root.mkdir(parents=True, exist_ok=True)
        phase_component = (
            f"{_slug(capture_phase)}_" if capture_kind == "diagnostic" else ""
        )
        base_name = (
            f"run_{context.run_index:06d}_attempt_{context.attempt}_"
            f"{_slug(context.scenario_id)}_{_slug(context.subject_id)}_"
            f"{phase_component}repo_{repository_id}.zip"
        )
        destination = archive_root / base_name
        temporary = destination.with_suffix(destination.suffix + ".tmp")

        capture_errors: list[dict[str, str]] = []

        def capture(label: str, operation, fallback):
            try:
                return operation()
            except BaseException as exc:
                if isinstance(exc, KeyboardInterrupt):
                    raise
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

        if strict_capture and capture_errors:
            surfaces = ", ".join(item["surface"] for item in capture_errors)
            raise github_controller_error(
                f"Diagnostic repository snapshot for {full_name} was incomplete; "
                f"failed surface(s): {surfaces}."
            )

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
            "capture_kind": capture_kind,
            "capture_phase": capture_phase,
            "repository_full_name": full_name,
            "repository_id": repository_id,
            "capture_errors": capture_errors,
        }

        if failure_reason is not None:
            # Backward-compatible fields retained for existing failure-forensics
            # consumers and historical result archives.
            manifest["failure_phase"] = capture_phase
            manifest["failure_reason"] = failure_reason

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
        except BaseException as exc:
            if isinstance(exc, KeyboardInterrupt):
                raise
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise github_controller_error(
                f"Could not persist repository archive for {full_name}: {exc}"
            ) from exc

        if not destination.is_file() or destination.stat().st_size <= 0:
            raise github_controller_error(
                f"Repository archive for {full_name} was not durably created."
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

    def _scenario_fixture_components(
        self,
        *,
        scenario_id: str,
        repository_name: str,
        full_name: str,
        repository_id: int,
        dynamic_base: tuple[github_fixture_base_file, ...],
    ):
        common = {
            "repository_name": repository_name,
            "expected_repository_full_name": full_name,
            "expected_repository_id": repository_id,
            "expected_default_branch": self._expected_default_branch,
            "fixture_base_files": dynamic_base,
        }
        if scenario_id == "f1_a_regression_disposition":
            materializer = github_f1_a_materializer(
                self._controller, spec=self._f1_a_spec, **common
            )
            fixture = github_f1_a_fixture(
                self._controller, materializer, self._f1_a_spec
            )
            return materializer, fixture, self._f1_a_spec.fixture_id
        if scenario_id == "f1_b_release_candidate_status":
            materializer = github_f1_b_materializer(
                self._controller, spec=self._f1_b_spec, **common
            )
            fixture = github_f1_b_fixture(
                self._controller, materializer, self._f1_b_spec
            )
            return materializer, fixture, self._f1_b_spec.fixture_id
        if scenario_id == "f2_a_incoming_regression_triage":
            materializer = github_f2_a_materializer(
                self._controller, spec=self._f2_a_spec, **common
            )
            fixture = github_f2_a_fixture(
                self._controller, materializer, self._f2_a_spec
            )
            return materializer, fixture, self._f2_a_spec.fixture_id
        if scenario_id == "f2_b_stale_work_item_maintenance":
            materializer = github_f2_b_materializer(
                self._controller, spec=self._f2_b_spec, **common
            )
            fixture = github_f2_b_fixture(
                self._controller, materializer, self._f2_b_spec
            )
            return materializer, fixture, self._f2_b_spec.fixture_id
        if scenario_id == "f3_a_implementation_provenance":
            materializer = github_f3_a_materializer(
                self._controller, spec=self._f3_a_spec, **common
            )
            fixture = github_f3_a_fixture(
                self._controller, materializer, self._f3_a_spec
            )
            return materializer, fixture, self._f3_a_spec.fixture_id
        if scenario_id == "f3_b_reverted_fix_status":
            materializer = github_f3_b_materializer(
                self._controller, spec=self._f3_b_spec, **common
            )
            fixture = github_f3_b_fixture(
                self._controller, materializer, self._f3_b_spec
            )
            return materializer, fixture, self._f3_b_spec.fixture_id
        if scenario_id == "f4_a_failing_validation_diagnosis":
            if self._f4_a_spec is None:
                raise github_controller_error("F4-A fixture specification is unavailable.")
            materializer = github_f4_a_materializer(
                self._controller, spec=self._f4_a_spec, **common
            )
            fixture = github_f4_a_fixture(
                self._controller, materializer, self._f4_a_spec
            )
            return materializer, fixture, self._f4_a_spec.fixture_id
        if scenario_id == "f4_b_superseded_failure_alert":
            if self._f4_b_spec is None:
                raise github_controller_error("F4-B fixture specification is unavailable.")
            materializer = github_f4_b_materializer(
                self._controller, spec=self._f4_b_spec, **common
            )
            fixture = github_f4_b_fixture(
                self._controller, materializer, self._f4_b_spec
            )
            return materializer, fixture, self._f4_b_spec.fixture_id
        if scenario_id == "f5_a_targeted_code_fix":
            if self._f5_a_spec is None:
                raise github_controller_error("F5-A fixture specification is unavailable.")
            materializer = github_f5_a_materializer(
                self._controller, spec=self._f5_a_spec, **common
            )
            fixture = github_f5_a_fixture(
                self._controller, materializer, self._f5_a_spec
            )
            return materializer, fixture, self._f5_a_spec.fixture_id
        if scenario_id == "f5_b_release_metadata_sync":
            if self._f5_b_spec is None:
                raise github_controller_error("F5-B fixture specification is unavailable.")
            materializer = github_f5_b_materializer(
                self._controller, spec=self._f5_b_spec, **common
            )
            fixture = github_f5_b_fixture(
                self._controller, materializer, self._f5_b_spec
            )
            return materializer, fixture, self._f5_b_spec.fixture_id
        if scenario_id == "f6_a_release_blocker_resolution":
            if self._f6_a_spec is None:
                raise github_controller_error("F6-A fixture specification is unavailable.")
            materializer = github_f6_a_materializer(
                self._controller, spec=self._f6_a_spec, **common
            )
            fixture = github_f6_a_fixture(
                self._controller, materializer, self._f6_a_spec
            )
            return materializer, fixture, self._f6_a_spec.fixture_id
        if scenario_id == "f6_b_existing_pr_repair":
            if self._f6_b_spec is None:
                raise github_controller_error("F6-B fixture specification is unavailable.")
            materializer = github_f6_b_materializer(
                self._controller, spec=self._f6_b_spec, **common
            )
            fixture = github_f6_b_slice_fixture(
                self._controller, spec=self._f6_b_spec, **common
            )
            return materializer, fixture, self._f6_b_spec.fixture_id
        raise github_controller_error(
            f"Scenario '{scenario_id}' has no scenario-slice fixture composition."
        )

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
        *,
        publication_seed=None,
    ) -> None:
        """Publish one remote-visible initial phase for the whole scenario slice."""
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
            if publication_seed is not None:
                publication_seed(identity)
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
            "scientific-workspace identity."
        )
    if value.get("private") is not True:
        raise github_controller_error(
            "Disposable scientific-workspace repository was not created private."
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
