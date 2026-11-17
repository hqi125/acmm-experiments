from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from acmm.experiment_api import captured_evidence, observed_environment, prepared_environment

from .controller import github_controller_client, github_controller_error, github_repository_identity
from .slice_restore import restore_branch_refs, restore_issue_snapshot, restore_repository_labels
from .f6 import (
    github_f6_a_materializer,
    github_f6_a_spec,
    github_f6_b_materializer,
    github_f6_b_run_scoped_spec,
    github_f6_b_spec,
)


@dataclass(frozen=True)
class github_f6_a_run_handle:
    identity: github_repository_identity
    observations: dict[str, Any]
    initial_state: dict[str, Any]


@dataclass(frozen=True)
class github_f6_b_run_handle:
    identity: github_repository_identity
    observations: dict[str, Any]
    initial_state: dict[str, Any]


class github_f6_a_fixture:
    def __init__(self, client, materializer, spec) -> None:
        self._client = client
        self._materializer = materializer
        self._spec = spec

    def prepare(self, scenario, reset) -> prepared_environment:
        del reset
        if scenario.get("id") != "f6_a_release_blocker_resolution":
            raise ValueError("F6-A fixture received an unexpected scenario.")
        identity, observations = self._materializer.inspect()
        state = _snapshot_f6_a_state(self._client, identity, self._spec, observations)
        _assert_f6_a_pristine(state, self._spec)
        return prepared_environment(
            handle=github_f6_a_run_handle(identity, dict(observations), state),
            provenance={"fixture": self._spec.fixture_id, "configuration": {"repository_name": identity.name}},
            evidence=(_json_evidence("initial_environment_state", "initial_environment_state", "evidence/initial_environment_state.json", state),),
            task_bindings={
                "repo_owner": identity.owner,
                "repo_name": identity.name,
                "blocker_issue_number": str(observations["blocker_issue_number"]),
            },
        )

    def observe(self, scenario, handle) -> observed_environment:
        del scenario
        if not isinstance(handle, github_f6_a_run_handle):
            raise TypeError("F6-A environment handle is invalid.")
        state = _snapshot_f6_a_state(self._client, handle.identity, self._spec, handle.observations)
        return observed_environment(evidence=(_json_evidence("final_environment_state", "final_environment_state", "evidence/final_environment_state.json", state),))

    def finalize(self, scenario, handle, reset):
        del scenario
        del reset
        if not isinstance(handle, github_f6_a_run_handle):
            return {"restored": False, "detail": "invalid F6-A environment handle"}
        return _restore_f6_a_slice(
            self._client,
            handle.identity,
            self._spec,
            handle.observations,
            handle.initial_state,
        )


class github_f6_b_slice_fixture:
    """Create fresh F6-B run fixtures inside one scenario-slice repository."""

    def __init__(
        self,
        client: github_controller_client,
        *,
        repository_name: str,
        expected_repository_full_name: str,
        expected_repository_id: int,
        expected_default_branch: str,
        fixture_base_files,
        spec: github_f6_b_spec,
    ) -> None:
        self._client = client
        self._repository_name = repository_name
        self._expected_repository_full_name = expected_repository_full_name
        self._expected_repository_id = expected_repository_id
        self._expected_default_branch = expected_default_branch
        self._fixture_base_files = tuple(fixture_base_files)
        self._spec = spec

    def prepare_for_run(self, scenario, reset, context):
        scoped_spec = github_f6_b_run_scoped_spec(
            self._spec,
            run_index=context.run_index,
        )
        materializer = github_f6_b_materializer(
            self._client,
            repository_name=self._repository_name,
            expected_repository_full_name=self._expected_repository_full_name,
            expected_repository_id=self._expected_repository_id,
            expected_default_branch=self._expected_default_branch,
            fixture_base_files=self._fixture_base_files,
            spec=scoped_spec,
        )
        materializer.run()
        fixture = github_f6_b_fixture(self._client, materializer, scoped_spec)
        return fixture, fixture.prepare(scenario, reset)


class github_f6_b_fixture:
    def __init__(self, client, materializer, spec) -> None:
        self._client = client
        self._materializer = materializer
        self._spec = spec

    def prepare(self, scenario, reset) -> prepared_environment:
        del reset
        if scenario.get("id") != "f6_b_existing_pr_repair":
            raise ValueError("F6-B fixture received an unexpected scenario.")
        identity, observations = self._materializer.inspect()
        state = _snapshot_f6_b_state(self._client, identity, self._spec, observations)
        _assert_f6_b_pristine(state, self._spec)
        return prepared_environment(
            handle=github_f6_b_run_handle(identity, dict(observations), state),
            provenance={"fixture": self._spec.fixture_id, "configuration": {"repository_name": identity.name}},
            evidence=(_json_evidence("initial_environment_state", "initial_environment_state", "evidence/initial_environment_state.json", state),),
            task_bindings={
                "repo_owner": identity.owner,
                "repo_name": identity.name,
                "repair_issue_number": str(observations["repair_issue_number"]),
                "repair_pr_number": str(observations["repair_pr_number"]),
            },
        )

    def observe(self, scenario, handle) -> observed_environment:
        del scenario
        if not isinstance(handle, github_f6_b_run_handle):
            raise TypeError("F6-B environment handle is invalid.")
        state = _snapshot_f6_b_state(self._client, handle.identity, self._spec, handle.observations)
        return observed_environment(evidence=(_json_evidence("final_environment_state", "final_environment_state", "evidence/final_environment_state.json", state),))

    def finalize(self, scenario, handle, reset):
        del scenario
        del reset
        if not isinstance(handle, github_f6_b_run_handle):
            return {"restored": False, "detail": "invalid F6-B environment handle"}
        return _retire_f6_b_run_fixture(
            self._client,
            handle.identity,
            self._spec,
            handle.observations,
            handle.initial_state,
        )


def _snapshot_f6_a_state(client, identity, spec: github_f6_a_spec, observations: Mapping[str, Any]) -> dict[str, Any]:
    issue_number = int(observations["blocker_issue_number"])
    common = _snapshot_common(client, identity)
    release_sha = _branch_sha_by_name(common["branches"], spec.release_branch)
    if release_sha is None:
        raise github_controller_error("F6-A release branch is missing.")
    relevant_paths = (
        spec.release_policy_path,
        spec.protocol_authority_path,
        spec.release_manifest_path,
        spec.required_workflow.path,
    )
    state = {
        **common,
        "release_branch": {
            "name": spec.release_branch,
            "sha": release_sha,
            "files": {path: client.read_text_file(identity.owner, identity.name, path, ref=release_sha) for path in relevant_paths},
        },
        "blocker_issue": _issue_snapshot(client, identity, issue_number),
        "candidate_branches": _candidate_branch_files(client, identity, relevant_paths, excluded={identity.default_branch, spec.release_branch}),
        "actions": _actions_snapshot(client, identity),
        "expected_terminal_manifest": spec.release_manifest_expected_content,
        "fixture_aliases": {
            "blocker_issue_number": issue_number,
            "release_branch": spec.release_branch,
            "release_head": observations["release_head"],
            "release_policy_path": spec.release_policy_path,
            "protocol_authority_path": spec.protocol_authority_path,
            "release_manifest_path": spec.release_manifest_path,
            "required_workflow_name": observations["required_workflow_name"],
            "failed_release_run_id": observations["failed_release_run"]["id"],
            "release_blocker_label": spec.release_blocker_label.name,
            "needs_investigation_label": spec.needs_investigation_label.name,
            "fix_in_review_label": spec.fix_in_review_label.name,
        },
    }
    state["protected_digest"] = _f6_a_protected_digest(state)
    state["full_digest"] = _digest(state)
    return state


def _snapshot_f6_b_state(client, identity, spec: github_f6_b_spec, observations: Mapping[str, Any]) -> dict[str, Any]:
    repair_issue_number = int(observations["repair_issue_number"])
    repair_pr_number = int(observations["repair_pr_number"])
    unrelated_pr_number = int(observations["unrelated_pr_number"])
    common = _snapshot_common(client, identity)
    repair_pr = common["pull_requests"].get(str(repair_pr_number))
    if not isinstance(repair_pr, Mapping):
        raise github_controller_error("F6-B repair PR is missing from authoritative snapshot.")
    repair_head = repair_pr.get("head")
    if not isinstance(repair_head, str):
        raise github_controller_error("F6-B repair PR head SHA is unavailable.")
    paths = (
        spec.repair_policy_path,
        spec.config_source_path,
        spec.config_docs_path,
        spec.compat_tests_path,
        spec.required_workflow.path,
    )
    state = {
        **common,
        "base_branch_files": {path: client.read_text_file(identity.owner, identity.name, path, ref=identity.default_branch) for path in paths},
        "repair_head_files": {path: client.read_text_file(identity.owner, identity.name, path, ref=repair_head) for path in paths},
        "repair_issue": _issue_snapshot(client, identity, repair_issue_number),
        "repair_pr": _pull_snapshot(client, identity, repair_pr_number),
        "unrelated_pr": _pull_snapshot(client, identity, unrelated_pr_number),
        "actions": _actions_snapshot(client, identity),
        "expected_terminal_files": {
            spec.config_source_path: spec.config_expected_content,
            spec.config_docs_path: spec.config_docs_expected_content,
        },
        "compatibility_behavior": config_timeout_behavior(client.read_text_file(identity.owner, identity.name, spec.config_source_path, ref=repair_head)),
        "fixture_aliases": {
            "repair_issue_number": repair_issue_number,
            "repair_pr_number": repair_pr_number,
            "unrelated_pr_number": unrelated_pr_number,
            "repair_head_branch": observations["repair_head_branch"],
            "pre_run_repair_head": observations["pre_run_repair_head"],
            "repair_policy_path": spec.repair_policy_path,
            "config_source_path": spec.config_source_path,
            "config_docs_path": spec.config_docs_path,
            "compat_tests_path": spec.compat_tests_path,
            "required_workflow_name": observations["required_workflow_name"],
            "failed_compat_run_id": observations["failed_compat_run"]["id"],
            "implementation_in_progress_label": spec.implementation_in_progress_label.name,
            "fix_in_review_label": spec.fix_in_review_label.name,
        },
    }
    state["protected_digest"] = _f6_b_protected_digest(state)
    state["full_digest"] = _digest(state)
    return state


def _snapshot_common(client, identity) -> dict[str, Any]:
    branches = tuple(client.list_branches(identity.owner, identity.name))
    issues = tuple(item for item in client.list_issues(identity.owner, identity.name) if "pull_request" not in item)
    pulls = tuple(client.list_pull_requests(identity.owner, identity.name))
    labels = tuple(client.list_labels(identity.owner, identity.name))
    pull_rows = {}
    for item in pulls:
        number = item.get("number")
        if isinstance(number, int):
            if str(item.get("state") or "") == "closed":
                pull_rows[str(number)] = _pull_snapshot_from_catalog(item, number)
            else:
                pull_rows[str(number)] = _pull_snapshot(client, identity, number)
    return {
        "authoritative_source": "github_rest_api",
        "repository": {"id": identity.repository_id, "full_name": identity.full_name, "default_branch": identity.default_branch},
        "branches": sorted(({"name": str(item.get("name")), "sha": _branch_sha(item), "protected": bool(item.get("protected", False))} for item in branches), key=lambda item: item["name"]),
        "issue_catalog": sorted(({"number": int(item["number"]), "title": item.get("title"), "state": item.get("state")} for item in issues if isinstance(item.get("number"), int)), key=lambda item: item["number"]),
        "pull_request_catalog": sorted(({"number": int(item["number"]), "title": item.get("title"), "state": item.get("state"), "draft": bool(item.get("draft", False))} for item in pulls if isinstance(item.get("number"), int)), key=lambda item: item["number"]),
        "repository_labels": sorted(({"name": item.get("name"), "color": item.get("color"), "description": item.get("description")} for item in labels), key=lambda item: str(item["name"])),
        "issues": {str(int(item["number"])): _issue_snapshot(client, identity, int(item["number"])) for item in issues if isinstance(item.get("number"), int)},
        "pull_requests": pull_rows,
    }


def _pull_snapshot_from_catalog(item: Mapping[str, Any], number: int) -> dict[str, Any]:
    """Snapshot immutable closed-PR residue from the list response only.

    Closed historical PRs are slice-owned residue. Their list representation already
    exposes the state/title/body/draft/head/base identity needed to detect later
    mutation. Avoiding one detail read plus one compare per historical PR prevents
    shared-repository verification from growing quadratically with the slice.
    """
    return {
        "number": number,
        "title": item.get("title"),
        "body": item.get("body"),
        "state": item.get("state"),
        "draft": bool(item.get("draft", False)),
        "merged": bool(item.get("merged") is True or item.get("merged_at")),
        "head": _nested_optional_string(item, "head", "sha"),
        "head_ref": _nested_optional_string(item, "head", "ref"),
        "base": _nested_optional_string(item, "base", "sha"),
        "base_ref": _nested_optional_string(item, "base", "ref"),
        "changed_files": [],
    }


def _pull_snapshot(client, identity, number: int) -> dict[str, Any]:
    item = client.pull_request(identity.owner, identity.name, number)
    head = _nested_optional_string(item, "head", "sha")
    base = _nested_optional_string(item, "base", "sha")
    files = []
    if isinstance(base, str) and isinstance(head, str):
        comparison = client.compare_commits(identity.owner, identity.name, base, head)
        values = comparison.get("files") if isinstance(comparison, Mapping) else None
        if isinstance(values, list):
            files = [{"filename": value.get("filename"), "status": value.get("status"), "previous_filename": value.get("previous_filename")} for value in values if isinstance(value, Mapping)]
    return {
        "number": number,
        "title": item.get("title"),
        "body": item.get("body"),
        "state": item.get("state"),
        "draft": bool(item.get("draft", False)),
        "merged": item.get("merged") is True,
        "head": head,
        "head_ref": _nested_optional_string(item, "head", "ref"),
        "base": base,
        "base_ref": _nested_optional_string(item, "base", "ref"),
        "changed_files": sorted(files, key=lambda value: str(value.get("filename"))),
    }


def _issue_snapshot(client, identity, number: int) -> dict[str, Any]:
    item = client.issue(identity.owner, identity.name, number)
    comments = tuple(client.issue_comments(identity.owner, identity.name, number))
    return {
        "number": number,
        "title": item.get("title"),
        "body": item.get("body"),
        "state": item.get("state"),
        "labels": sorted(_label_names(item)),
        "comments": [_comment_snapshot(value) for value in comments],
    }


def _candidate_branch_files(client, identity, paths: tuple[str, ...], *, excluded: set[str]) -> dict[str, Any]:
    result = {}
    for branch in client.list_branches(identity.owner, identity.name):
        name = branch.get("name")
        sha = _branch_sha(branch)
        if not isinstance(name, str) or name in excluded or not isinstance(sha, str):
            continue
        files = {}
        for path in paths:
            value = client.contents_optional(identity.owner, identity.name, path, ref=sha)
            files[path] = None if value is None else client.read_text_file(identity.owner, identity.name, path, ref=sha)
        result[name] = {"sha": sha, "files": files}
    return result


def _actions_snapshot(client, identity) -> dict[str, Any]:
    workflows_value = client.list_workflows(identity.owner, identity.name)
    workflows = workflows_value.get("workflows") if isinstance(workflows_value, Mapping) else None
    runs_value = client.list_workflow_runs(identity.owner, identity.name, per_page=100)
    runs = runs_value.get("workflow_runs") if isinstance(runs_value, Mapping) else None
    return {
        "workflows": sorted(({"id": item.get("id"), "name": item.get("name"), "path": item.get("path"), "state": item.get("state")} for item in (workflows or []) if isinstance(item, Mapping)), key=lambda item: str(item.get("name"))),
        "runs": sorted(({"id": item.get("id"), "name": item.get("name"), "workflow_id": item.get("workflow_id"), "head_branch": item.get("head_branch"), "head_sha": item.get("head_sha"), "event": item.get("event"), "status": item.get("status"), "conclusion": item.get("conclusion")} for item in (runs or []) if isinstance(item, Mapping)), key=lambda item: int(item.get("id") or 0)),
    }


def _f6_a_protected_digest(state: Mapping[str, Any]) -> str:
    aliases = state.get("fixture_aliases", {})
    blocker = str(aliases.get("blocker_issue_number"))
    release_branch = aliases.get("release_branch")
    default_branch = state.get("repository", {}).get("default_branch") if isinstance(state.get("repository"), Mapping) else None
    value = {
        "repository": state.get("repository"),
        "protected_branches": [item for item in state.get("branches", []) if isinstance(item, Mapping) and item.get("name") in {default_branch, release_branch}],
        "release_branch": state.get("release_branch"),
        "repository_labels": state.get("repository_labels"),
        "unrelated_issues": {key: item for key, item in state.get("issues", {}).items() if key != blocker},
        "actions": state.get("actions"),
    }
    return _digest(value)


def _f6_b_protected_digest(state: Mapping[str, Any]) -> str:
    aliases = state.get("fixture_aliases", {})
    repair_issue = str(aliases.get("repair_issue_number"))
    repair_pr = str(aliases.get("repair_pr_number"))
    default_branch = state.get("repository", {}).get("default_branch") if isinstance(state.get("repository"), Mapping) else None
    repair_branch = aliases.get("repair_head_branch")
    value = {
        "repository": state.get("repository"),
        "default_branch": next((item for item in state.get("branches", []) if isinstance(item, Mapping) and item.get("name") == default_branch), None),
        "repository_labels": state.get("repository_labels"),
        "base_branch_files": state.get("base_branch_files"),
        "unrelated_branches": [item for item in state.get("branches", []) if isinstance(item, Mapping) and item.get("name") not in {default_branch, repair_branch}],
        "unrelated_issues": {key: item for key, item in state.get("issues", {}).items() if key != repair_issue},
        "unrelated_pull_requests": {key: item for key, item in state.get("pull_requests", {}).items() if key != repair_pr},
        "actions": state.get("actions"),
    }
    return _digest(value)


def _assert_f6_a_pristine(state: Mapping[str, Any], spec: github_f6_a_spec) -> None:
    issue = state.get("blocker_issue")
    if not isinstance(issue, Mapping) or issue.get("state") != "open":
        raise github_controller_error("F6-A blocker issue is not pristine and open.")
    if set(issue.get("labels", [])) != {spec.release_blocker_label.name, spec.needs_investigation_label.name}:
        raise github_controller_error("F6-A blocker issue labels are not pristine.")
    release = state.get("release_branch")
    if not isinstance(release, Mapping):
        raise github_controller_error("F6-A release branch snapshot is missing.")
    files = release.get("files")
    if not isinstance(files, Mapping) or files.get(spec.protocol_authority_path) != spec.protocol_authority_content or files.get(spec.release_manifest_path) != spec.release_manifest_stale_content:
        raise github_controller_error("F6-A release branch fixture is not pristine.")
    if state.get("candidate_branches"):
        raise github_controller_error("F6-A unexpectedly contains an active repair branch before subject execution.")
    for pull in state.get("pull_requests", {}).values():
        if not isinstance(pull, Mapping) or pull.get("state") != "closed" or pull.get("merged") is True:
            raise github_controller_error(
                "F6-A scenario slice contains an active or merged historical pull request."
            )


def _assert_f6_b_pristine(state: Mapping[str, Any], spec: github_f6_b_spec) -> None:
    issue = state.get("repair_issue")
    pr = state.get("repair_pr")
    unrelated_pr = state.get("unrelated_pr")
    if not isinstance(issue, Mapping) or issue.get("state") != "open" or set(issue.get("labels", [])) != {spec.implementation_in_progress_label.name}:
        raise github_controller_error("F6-B repair issue is not pristine.")
    if not isinstance(pr, Mapping) or pr.get("state") != "open" or pr.get("draft") is not True or pr.get("merged") is True:
        raise github_controller_error("F6-B repair PR is not pristine and draft.")
    if not isinstance(unrelated_pr, Mapping) or unrelated_pr.get("state") != "open" or unrelated_pr.get("merged") is True:
        raise github_controller_error("F6-B unrelated comparison PR is not pristine and open.")

    aliases = state.get("fixture_aliases") if isinstance(state.get("fixture_aliases"), Mapping) else {}
    repair_issue_number = str(aliases.get("repair_issue_number"))
    repair_pr_number = str(aliases.get("repair_pr_number"))
    unrelated_pr_number = str(aliases.get("unrelated_pr_number"))
    default_branch = state.get("repository", {}).get("default_branch") if isinstance(state.get("repository"), Mapping) else None
    active_branch_names = {
        str(item.get("name"))
        for item in state.get("branches", [])
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    }
    expected_active = {default_branch, spec.repair_branch, spec.unrelated_branch}
    if active_branch_names != expected_active:
        raise github_controller_error(
            "F6-B scenario slice contains unexpected active branch state before subject execution."
        )

    for key, historical in state.get("pull_requests", {}).items():
        if key in {repair_pr_number, unrelated_pr_number}:
            continue
        if not isinstance(historical, Mapping) or historical.get("state") != "closed" or historical.get("merged") is True:
            raise github_controller_error(
                "F6-B scenario slice contains an active or merged historical pull request."
            )
    for key, historical in state.get("issues", {}).items():
        if key == repair_issue_number:
            continue
        if not isinstance(historical, Mapping) or historical.get("state") != "closed":
            raise github_controller_error(
                "F6-B scenario slice contains an active historical issue."
            )

    files = state.get("repair_head_files")
    if not isinstance(files, Mapping) or files.get(spec.config_source_path) != spec.config_broken_content or files.get(spec.config_docs_path) != spec.config_docs_broken_content or files.get(spec.compat_tests_path) != spec.compat_tests_content:
        raise github_controller_error("F6-B repair head fixture is not pristine.")
    behavior = state.get("compatibility_behavior")
    if not isinstance(behavior, Mapping) or behavior.get("legacy_timeout") == 3000 or behavior.get("timeout_ms") != 2500:
        raise github_controller_error("F6-B broken pre-state does not expose the intended compatibility failure.")



def _restore_f6_a_slice(
    client: github_controller_client,
    identity: github_repository_identity,
    spec: github_f6_a_spec,
    observations: Mapping[str, Any],
    initial: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        current = _snapshot_f6_a_state(client, identity, spec, observations)
        initial_pulls = initial.get("pull_requests") if isinstance(initial.get("pull_requests"), Mapping) else {}
        current_pulls = current.get("pull_requests") if isinstance(current.get("pull_requests"), Mapping) else {}
        historical_changed = any(current_pulls.get(key) != value for key, value in initial_pulls.items())
        new_pull_keys = [key for key in current_pulls if key not in initial_pulls]
        non_restorable: list[str] = []
        if historical_changed:
            non_restorable.append("historical pull-request residue changed")
        if len(new_pull_keys) > 1:
            non_restorable.append(
                f"run created {len(new_pull_keys)} pull requests; at most one run-owned PR is allowed"
            )
        for key in new_pull_keys:
            pull = current_pulls.get(key)
            if not isinstance(pull, Mapping):
                continue
            number = int(key)
            if pull.get("merged") is True:
                non_restorable.append(f"run-owned pull request #{number} was merged")
            if pull.get("base_ref") != spec.release_branch:
                non_restorable.append(
                    f"run-owned pull request #{number} targeted unexpected base {pull.get('base_ref')!r}"
                )
            client.update_pull_request(identity.owner, identity.name, number, {"state": "closed"})

        initial_issue_numbers = set((initial.get("issues") or {}).keys())
        current_issue_numbers = set((current.get("issues") or {}).keys())
        for number_text in sorted(current_issue_numbers - initial_issue_numbers, key=int):
            client.update_issue(identity.owner, identity.name, int(number_text), {"state": "closed"})
            non_restorable.append(f"unexpected issue #{number_text} remains in scenario history")

        restore_branch_refs(client, identity, initial, non_restorable, allowed_new_history=True)
        restore_issue_snapshot(
            client,
            identity,
            int(observations["blocker_issue_number"]),
            initial["blocker_issue"],
        )
        restore_repository_labels(client, identity, initial.get("repository_labels", []))

        after = _snapshot_f6_a_state(client, identity, spec, observations)
        baseline_ok = after.get("protected_digest") == initial.get("protected_digest")
        active_branches = after.get("candidate_branches") if isinstance(after.get("candidate_branches"), Mapping) else {}
        residue_ok = True
        after_pulls = after.get("pull_requests") if isinstance(after.get("pull_requests"), Mapping) else {}
        for key, value in initial_pulls.items():
            if after_pulls.get(key) != value:
                residue_ok = False
        for key in new_pull_keys:
            pull = after_pulls.get(key)
            if not isinstance(pull, Mapping) or pull.get("state") != "closed" or pull.get("merged") is True:
                residue_ok = False
        restored = not non_restorable and baseline_ok and not active_branches and residue_ok
        pristine_equivalent = (
            restored
            and after.get("full_digest") == initial.get("full_digest")
        )
        return {
            "restored": restored,
            "restoration_semantics": "active_state_with_explicit_append_only_history",
            "pristine_equivalent": pristine_equivalent,
            "changed": current.get("full_digest") != initial.get("full_digest"),
            "slice_owned_pull_residue": tuple(int(key) for key in new_pull_keys),
            "non_restorable": tuple(non_restorable),
        }
    except Exception as exc:
        return {"restored": False, "changed": True, "detail": str(exc) or exc.__class__.__name__}


def _retire_f6_b_run_fixture(
    client: github_controller_client,
    identity: github_repository_identity,
    spec: github_f6_b_spec,
    observations: Mapping[str, Any],
    initial: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        current = _snapshot_f6_b_state(client, identity, spec, observations)
        non_restorable: list[str] = []
        if current.get("protected_digest") != initial.get("protected_digest"):
            non_restorable.append("protected scenario-slice state changed outside the active repair scope")

        initial_pulls = initial.get("pull_requests") if isinstance(initial.get("pull_requests"), Mapping) else {}
        current_pulls = current.get("pull_requests") if isinstance(current.get("pull_requests"), Mapping) else {}
        if set(current_pulls) != set(initial_pulls):
            for key in sorted(set(current_pulls) - set(initial_pulls), key=int):
                pull = current_pulls.get(key)
                if isinstance(pull, Mapping) and pull.get("merged") is not True:
                    client.update_pull_request(identity.owner, identity.name, int(key), {"state": "closed"})
                non_restorable.append(f"unexpected pull request #{key} remains in scenario history")

        initial_issues = initial.get("issues") if isinstance(initial.get("issues"), Mapping) else {}
        current_issues = current.get("issues") if isinstance(current.get("issues"), Mapping) else {}
        if set(current_issues) != set(initial_issues):
            for key in sorted(set(current_issues) - set(initial_issues), key=int):
                client.update_issue(identity.owner, identity.name, int(key), {"state": "closed"})
                non_restorable.append(f"unexpected issue #{key} remains in scenario history")

        repair_pr = int(observations["repair_pr_number"])
        unrelated_pr = int(observations["unrelated_pr_number"])
        repair_issue = int(observations["repair_issue_number"])
        for number in (repair_pr, unrelated_pr):
            value = client.pull_request(identity.owner, identity.name, number)
            if value.get("merged") is True:
                non_restorable.append(f"run-owned pull request #{number} was merged")
            else:
                client.update_pull_request(identity.owner, identity.name, number, {"state": "closed"})
        client.update_issue(identity.owner, identity.name, repair_issue, {"state": "closed"})

        for branch in (spec.repair_branch, spec.unrelated_branch):
            try:
                client.delete_ref(identity.owner, identity.name, branch)
            except Exception:
                # Verification below decides whether the ref actually remains.
                pass

        restore_repository_labels(client, identity, initial.get("repository_labels", []))
        after_branches = {
            str(item.get("name"))
            for item in client.list_branches(identity.owner, identity.name)
            if isinstance(item.get("name"), str)
        }
        active_refs = {spec.repair_branch, spec.unrelated_branch} & after_branches
        if active_refs:
            non_restorable.append(
                "run-owned F6-B branches remain active: " + ", ".join(sorted(active_refs))
            )

        # The run-owned PRs/issues are intentionally retained only as closed provider
        # history. They are assigned unique markers/refs on every subsequent run.
        for number in (repair_pr, unrelated_pr):
            value = client.pull_request(identity.owner, identity.name, number)
            if value.get("state") != "closed" or value.get("merged") is True:
                non_restorable.append(f"run-owned pull request #{number} did not retire cleanly")
        issue_value = client.issue(identity.owner, identity.name, repair_issue)
        if issue_value.get("state") != "closed":
            non_restorable.append(f"run-owned issue #{repair_issue} did not retire cleanly")

        return {
            "restored": not non_restorable,
            "changed": True,
            "slice_owned_pull_residue": (repair_pr, unrelated_pr),
            "slice_owned_issue_residue": (repair_issue,),
            "non_restorable": tuple(non_restorable),
        }
    except Exception as exc:
        return {"restored": False, "changed": True, "detail": str(exc) or exc.__class__.__name__}


def config_timeout_behavior(source: str) -> dict[str, int | None] | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    function = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "timeout_ms"), None)
    if function is None or not function.args.args:
        return None
    parameter = function.args.args[0].arg
    try:
        return {
            "timeout_ms": int(_execute_config(function.body, parameter, {"timeout_ms": 2500})),
            "legacy_timeout": int(_execute_config(function.body, parameter, {"timeout": 3})),
            "default": int(_execute_config(function.body, parameter, {})),
        }
    except (ValueError, TypeError, KeyError):
        return {"timeout_ms": _safe_config(function.body, parameter, {"timeout_ms": 2500}), "legacy_timeout": _safe_config(function.body, parameter, {"timeout": 3}), "default": _safe_config(function.body, parameter, {})}


def _safe_config(statements, parameter, config):
    try:
        return int(_execute_config(statements, parameter, config))
    except (ValueError, TypeError, KeyError):
        return None


def _execute_config(statements: list[ast.stmt], parameter: str, config: dict[str, int]) -> Any:
    for statement in statements:
        if isinstance(statement, ast.Return):
            return _eval_config_expr(statement.value, parameter, config)
        if isinstance(statement, ast.If):
            branch = statement.body if bool(_eval_config_expr(statement.test, parameter, config)) else statement.orelse
            try:
                return _execute_config(branch, parameter, config)
            except ValueError:
                continue
    raise ValueError("No supported return path")


def _eval_config_expr(node: ast.AST | None, parameter: str, config: dict[str, int]) -> Any:
    if node is None:
        raise ValueError("missing expression")
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id == parameter:
        return config
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        left = _eval_config_expr(node.left, parameter, config)
        right = _eval_config_expr(node.comparators[0], parameter, config)
        if isinstance(node.ops[0], ast.In):
            return left in right
        if isinstance(node.ops[0], ast.NotIn):
            return left not in right
        if isinstance(node.ops[0], ast.Eq):
            return left == right
    if isinstance(node, ast.Subscript):
        target = _eval_config_expr(node.value, parameter, config)
        key = _eval_config_expr(node.slice, parameter, config)
        return target[key]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "int" and len(node.args) == 1:
        return int(_eval_config_expr(node.args[0], parameter, config))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        return _eval_config_expr(node.left, parameter, config) * _eval_config_expr(node.right, parameter, config)
    raise ValueError("unsupported expression")


def docs_support_both(content: str) -> bool:
    folded = content.casefold()
    return all(token in folded for token in ("timeout_ms", "millisecond", "timeout", "second")) and ("legacy" in folded or "compatib" in folded)


def _branch_sha_by_name(branches: Any, name: str) -> str | None:
    if not isinstance(branches, list):
        return None
    for item in branches:
        if isinstance(item, Mapping) and item.get("name") == name and isinstance(item.get("sha"), str):
            return item.get("sha")
    return None


def _branch_sha(item: Mapping[str, Any]) -> str | None:
    commit = item.get("commit")
    if isinstance(commit, Mapping) and isinstance(commit.get("sha"), str):
        return commit.get("sha")
    return None


def _label_names(item: Mapping[str, Any]) -> set[str]:
    values = item.get("labels")
    if not isinstance(values, list):
        return set()
    return {str(value.get("name")) for value in values if isinstance(value, Mapping) and isinstance(value.get("name"), str)}


def _nested_optional_string(item: Mapping[str, Any], first: str, second: str) -> str | None:
    nested = item.get(first)
    if isinstance(nested, Mapping) and isinstance(nested.get(second), str):
        return nested.get(second)
    return None


def _comment_snapshot(item: Mapping[str, Any]) -> dict[str, Any]:
    user = item.get("user")
    return {"id": item.get("id"), "body": item.get("body"), "user": user.get("login") if isinstance(user, Mapping) else None, "created_at": item.get("created_at"), "updated_at": item.get("updated_at")}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _json_evidence(evidence_id: str, channel: str, artifact: str, value: Any) -> captured_evidence:
    return captured_evidence(id=evidence_id, channel=channel, artifact=artifact, content=(json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))
