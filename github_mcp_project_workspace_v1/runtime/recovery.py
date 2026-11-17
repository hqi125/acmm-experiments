from __future__ import annotations

import hashlib
from typing import Any, Mapping

from acmm.experiment_api import (
    runtime_execution_recovery_context,
    runtime_execution_recovery_result,
)

from .controller import github_controller_client, github_controller_error
from .github_app import github_app_client
from .resource_ledger import github_resource_ledger


class github_workspace_runtime_recovery:
    def __init__(
        self,
        controller: github_controller_client,
        app_client: github_app_client,
        *,
        run_name_prefix: str,
    ) -> None:
        if not run_name_prefix.strip():
            raise ValueError("Disposable repository run prefix must not be empty.")
        self._controller = controller
        self._app_client = app_client
        self._run_name_prefix = run_name_prefix.strip()

    def reconcile(
        self,
        context: runtime_execution_recovery_context,
    ) -> runtime_execution_recovery_result:
        ledger = github_resource_ledger(context.session_dir)
        recorded = {
            int(item["repository_id"]): dict(item)
            for item in ledger.repositories()
            if isinstance(item.get("repository_id"), int)
            and not isinstance(item.get("repository_id"), bool)
        }
        execution_tag = hashlib.sha256(
            context.execution_id.encode("utf-8")
        ).hexdigest()[:8]
        name_marker = f"-e{execution_tag}-"

        discovered: dict[int, Mapping[str, Any]] = {}
        try:
            for repository in self._controller.list_repositories():
                repository_id = repository.get("id")
                name = repository.get("name")
                if (
                    isinstance(repository_id, int)
                    and not isinstance(repository_id, bool)
                    and repository_id > 0
                    and isinstance(name, str)
                    and name.startswith(self._run_name_prefix + "-")
                    and name_marker in name
                ):
                    discovered[repository_id] = repository
        except Exception as exc:
            return runtime_execution_recovery_result(
                safe_to_continue=False,
                changed=False,
                detail=(
                    "GitHub runtime recovery could not enumerate disposable "
                    f"repositories for the interrupted execution: {exc}"
                ),
                observations={"execution_tag": execution_tag},
            )

        candidate_ids = set(recorded) | set(discovered)
        changed = False
        retired: list[str] = []
        missing: list[int] = []
        failures: list[str] = []
        unledgered: list[str] = []

        for repository_id in sorted(candidate_ids):
            entry = recorded.get(repository_id)
            repository = discovered.get(repository_id)
            if entry is not None and entry.get("repository_retired") is True:
                continue

            owner = None
            name = None
            full_name = None
            if entry is not None:
                owner = entry.get("owner")
                name = entry.get("name")
                full_name = entry.get("full_name")
            if repository is not None:
                owner_value = repository.get("owner")
                repository_owner = (
                    owner_value.get("login")
                    if isinstance(owner_value, Mapping)
                    else None
                )
                repository_name = repository.get("name")
                repository_full_name = repository.get("full_name")
                owner = owner or repository_owner
                name = name or repository_name
                full_name = full_name or repository_full_name
                if entry is None and isinstance(repository_full_name, str):
                    unledgered.append(repository_full_name)

            if not isinstance(owner, str) or not owner.strip() or not isinstance(name, str) or not name.strip():
                failures.append(
                    f"repository id {repository_id}: identity metadata is incomplete"
                )
                continue

            try:
                current = self._controller.repository_optional(owner, name)
                if current is not None:
                    current_id = current.get("id")
                    if current_id != repository_id:
                        raise github_controller_error(
                            f"repository id changed from {repository_id} to {current_id}"
                        )
                    if current.get("private") is not True:
                        raise github_controller_error(
                            "refusing recovery deletion because repository is no longer private"
                        )

                # A hard crash may lose the token value, so direct revocation is not
                # always possible. Detach only when the durable ledger says the
                # repository was admitted. Legacy READY prepared-isolated resources were
                # never attached and should not spend an unnecessary provider call.
                # Unledgered recovery candidates remain conservative because their
                # admission state is unknowable after the crash.
                should_detach = entry is None or (
                    entry.get("installation_attached") is True
                    and entry.get("installation_detached") is not True
                )
                if should_detach:
                    self._controller.remove_repository_from_app_installation(
                        installation_id=self._app_client.installation_id,
                        repository_id=repository_id,
                    )
                    changed = True
                    if entry is not None:
                        ledger.update(
                            repository_id,
                            installation_detached=True,
                        )

                if current is not None:
                    self._controller.delete_repository(owner, name)
                    if self._controller.repository_optional(owner, name) is not None:
                        raise github_controller_error(
                            "repository remained visible after recovery deletion"
                        )
                    changed = True
                    retired.append(str(full_name or f"{owner}/{name}"))
                else:
                    missing.append(repository_id)

                if entry is not None:
                    ledger.update(
                        repository_id,
                        repository_retired=True,
                    )
            except Exception as exc:
                failures.append(
                    f"{full_name or f'{owner}/{name}'} (id={repository_id}): {exc}"
                )

        observations = {
            "execution_tag": execution_tag,
            "recorded_repository_count": len(recorded),
            "discovered_repository_count": len(discovered),
            "retired_repositories": tuple(retired),
            "already_missing_repository_ids": tuple(missing),
            "unledgered_discovered_repositories": tuple(unledgered),
            "orphaned_token_policy": (
                "exact repository detached/deleted; lost one-repository token cannot "
                "reach future repositories and expires provider-side"
            ),
        }
        if failures:
            observations["failures"] = tuple(failures)
            return runtime_execution_recovery_result(
                safe_to_continue=False,
                changed=changed,
                detail=(
                    "GitHub runtime recovery could not safely retire all resources: "
                    + "; ".join(failures)
                ),
                observations=observations,
            )

        return runtime_execution_recovery_result(
            safe_to_continue=True,
            changed=changed,
            detail=(
                "GitHub runtime recovery reconciled interrupted disposable repository "
                "resources."
            ),
            observations=observations,
        )
