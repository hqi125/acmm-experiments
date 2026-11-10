from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from acmm.experiment_api import captured_evidence, observed_environment, prepared_environment

from .controller import github_controller_client, github_repository_identity
from .f3 import (
    github_f3_a_materializer,
    github_f3_a_spec,
    github_f3_b_materializer,
    github_f3_b_spec,
)


@dataclass(frozen=True)
class github_f3_a_run_handle:
    identity: github_repository_identity
    observations: Mapping[str, Any]
    initial_state: Mapping[str, Any]


@dataclass(frozen=True)
class github_f3_b_run_handle:
    identity: github_repository_identity
    observations: Mapping[str, Any]
    initial_state: Mapping[str, Any]


class github_f3_a_fixture:
    def __init__(
        self,
        client: github_controller_client,
        materializer: github_f3_a_materializer,
        spec: github_f3_a_spec,
    ) -> None:
        self._client = client
        self._materializer = materializer
        self._spec = spec

    def prepare(self, scenario, reset) -> prepared_environment:
        del reset
        if scenario.get("id") != "f3_a_implementation_provenance":
            raise ValueError("F3-A fixture received an unexpected scenario.")
        identity, observations = self._materializer.inspect()
        state = _snapshot_f3_a_state(self._client, identity, self._spec, observations)
        _assert_f3_a_pristine(state, self._spec, observations)
        return prepared_environment(
            handle=github_f3_a_run_handle(identity, dict(observations), state),
            provenance={
                "fixture": self._spec.fixture_id,
                "configuration": {"repository_name": identity.name},
            },
            evidence=(
                _json_evidence(
                    "initial_environment_state",
                    "initial_environment_state",
                    "evidence/initial_environment_state.json",
                    state,
                ),
            ),
            task_bindings={
                "repo_owner": identity.owner,
                "repo_name": identity.name,
                "implementation_issue_number": str(
                    observations["implementation_issue_number"]
                ),
                "project_record_policy_path": self._spec.project_record_policy_path,
                "target_implementation_path": self._spec.target_implementation_path,
                "candidate_pr_number_a": str(observations["implementation_pr_number"]),
                "candidate_pr_number_b": str(observations["decoy_pr_number"]),
            },
        )

    def observe(self, scenario, handle) -> observed_environment:
        del scenario
        if not isinstance(handle, github_f3_a_run_handle):
            raise TypeError("F3-A environment handle is invalid.")
        state = _snapshot_f3_a_state(
            self._client,
            handle.identity,
            self._spec,
            handle.observations,
        )
        return observed_environment(
            evidence=(
                _json_evidence(
                    "final_environment_state",
                    "final_environment_state",
                    "evidence/final_environment_state.json",
                    state,
                ),
            ),
        )


class github_f3_b_fixture:
    def __init__(
        self,
        client: github_controller_client,
        materializer: github_f3_b_materializer,
        spec: github_f3_b_spec,
    ) -> None:
        self._client = client
        self._materializer = materializer
        self._spec = spec

    def prepare(self, scenario, reset) -> prepared_environment:
        del reset
        if scenario.get("id") != "f3_b_reverted_fix_status":
            raise ValueError("F3-B fixture received an unexpected scenario.")
        identity, observations = self._materializer.inspect()
        state = _snapshot_f3_b_state(self._client, identity, self._spec, observations)
        _assert_f3_b_pristine(state, self._spec, observations)
        return prepared_environment(
            handle=github_f3_b_run_handle(identity, dict(observations), state),
            provenance={
                "fixture": self._spec.fixture_id,
                "configuration": {"repository_name": identity.name},
            },
            evidence=(
                _json_evidence(
                    "initial_environment_state",
                    "initial_environment_state",
                    "evidence/initial_environment_state.json",
                    state,
                ),
            ),
            task_bindings={
                "repo_owner": identity.owner,
                "repo_name": identity.name,
                "tracking_issue_number": str(observations["tracking_issue_number"]),
                "release_status_policy_path": self._spec.release_status_policy_path,
                "target_fix_path": self._spec.target_fix_path,
                "candidate_pr_number_a": str(observations["old_fix_pr_number"]),
                "candidate_pr_number_b": str(observations["revert_pr_number"]),
                "candidate_pr_number_c": str(observations["replacement_pr_number"]),
            },
        )

    def observe(self, scenario, handle) -> observed_environment:
        del scenario
        if not isinstance(handle, github_f3_b_run_handle):
            raise TypeError("F3-B environment handle is invalid.")
        state = _snapshot_f3_b_state(
            self._client,
            handle.identity,
            self._spec,
            handle.observations,
        )
        return observed_environment(
            evidence=(
                _json_evidence(
                    "final_environment_state",
                    "final_environment_state",
                    "evidence/final_environment_state.json",
                    state,
                ),
            ),
        )


def _snapshot_f3_a_state(
    client: github_controller_client,
    identity: github_repository_identity,
    spec: github_f3_a_spec,
    observations: Mapping[str, Any],
) -> dict[str, Any]:
    common = _snapshot_common_state(client, identity)
    issue_number = int(observations["implementation_issue_number"])
    historical_comment_id = int(observations["historical_comment_id"])
    issue = common["issues"].get(str(issue_number), {})
    history = tuple(client.list_commits(identity.owner, identity.name, sha=identity.default_branch))
    history_shas = [str(item.get("sha")) for item in history if isinstance(item.get("sha"), str)]
    state = {
        **common,
        "files": {
            spec.project_record_policy_path: client.read_text_file(
                identity.owner,
                identity.name,
                spec.project_record_policy_path,
                ref=identity.default_branch,
            ),
            spec.target_implementation_path: client.read_text_file(
                identity.owner,
                identity.name,
                spec.target_implementation_path,
                ref=identity.default_branch,
            ),
            spec.decoy_support_path: client.read_text_file(
                identity.owner,
                identity.name,
                spec.decoy_support_path,
                ref=identity.default_branch,
            ),
        },
        "default_branch_history": history_shas,
        "delivery_commit_on_default_branch": observations["delivery_commit"] in history_shas,
        "decoy_commit_on_default_branch": observations["decoy_commit"] in history_shas,
        "fixture_aliases": {
            "implementation_issue_number": issue_number,
            "implementation_pr_number": int(observations["implementation_pr_number"]),
            "decoy_pr_number": int(observations["decoy_pr_number"]),
            "delivery_commit": str(observations["delivery_commit"]),
            "decoy_commit": str(observations["decoy_commit"]),
            "implementation_merge_commit": str(observations["implementation_merge_commit"]),
            "decoy_merge_commit": str(observations["decoy_merge_commit"]),
            "historical_comment_id": historical_comment_id,
            "implemented_label": spec.implemented_label.name,
            "linkage_audit_label": spec.linkage_audit_label.name,
        },
    }
    state["protected_digest"] = _digest(
        _f3_a_protected_state(state, issue, historical_comment_id, spec)
    )
    state["full_digest"] = _digest(state)
    return state


def _snapshot_f3_b_state(
    client: github_controller_client,
    identity: github_repository_identity,
    spec: github_f3_b_spec,
    observations: Mapping[str, Any],
) -> dict[str, Any]:
    common = _snapshot_common_state(client, identity)
    issue_number = int(observations["tracking_issue_number"])
    historical_comment_id = int(observations["historical_comment_id"])
    issue = common["issues"].get(str(issue_number), {})
    history = tuple(client.list_commits(identity.owner, identity.name, sha=identity.default_branch))
    history_shas = [str(item.get("sha")) for item in history if isinstance(item.get("sha"), str)]
    replacement_content = client.read_text_file(
        identity.owner,
        identity.name,
        spec.target_fix_path,
        ref=spec.replacement_pr.branch,
    )
    state = {
        **common,
        "files": {
            spec.release_status_policy_path: client.read_text_file(
                identity.owner,
                identity.name,
                spec.release_status_policy_path,
                ref=identity.default_branch,
            ),
            spec.target_fix_path: client.read_text_file(
                identity.owner,
                identity.name,
                spec.target_fix_path,
                ref=identity.default_branch,
            ),
        },
        "replacement_branch_target_content": replacement_content,
        "default_branch_history": history_shas,
        "old_fix_commit_on_default_branch": observations["old_fix_commit"] in history_shas,
        "revert_commit_on_default_branch": observations["revert_commit"] in history_shas,
        "revised_fix_commit_on_default_branch": observations["revised_fix_commit"] in history_shas,
        "fixture_aliases": {
            "tracking_issue_number": issue_number,
            "old_fix_pr_number": int(observations["old_fix_pr_number"]),
            "revert_pr_number": int(observations["revert_pr_number"]),
            "replacement_pr_number": int(observations["replacement_pr_number"]),
            "old_fix_commit": str(observations["old_fix_commit"]),
            "revert_commit": str(observations["revert_commit"]),
            "revised_fix_commit": str(observations["revised_fix_commit"]),
            "old_fix_merge_commit": str(observations["old_fix_merge_commit"]),
            "revert_merge_commit": str(observations["revert_merge_commit"]),
            "historical_comment_id": historical_comment_id,
            "release_blocker_label": spec.release_blocker_label.name,
            "ready_label": spec.ready_label.name,
            "blocked_label": spec.blocked_label.name,
        },
    }
    state["protected_digest"] = _digest(
        _f3_b_protected_state(state, issue, historical_comment_id, spec)
    )
    state["full_digest"] = _digest(state)
    return state


def _f3_a_protected_state(
    state: Mapping[str, Any],
    issue: Mapping[str, Any],
    historical_comment_id: int,
    spec: github_f3_a_spec,
) -> dict[str, Any]:
    protected = {
        key: value
        for key, value in state.items()
        if key not in {"issues", "fixture_aliases", "protected_digest", "full_digest"}
    }
    issue_number = int(state["fixture_aliases"]["implementation_issue_number"])
    protected["other_issues"] = {
        key: value for key, value in state["issues"].items() if key != str(issue_number)
    }
    protected["tracked_issue"] = {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "body": issue.get("body"),
        "state": issue.get("state"),
        "implemented_label_present": spec.implemented_label.name in issue.get("labels", []),
        "assignees": issue.get("assignees"),
        "milestone": issue.get("milestone"),
        "historical_comment": _comment_by_id(issue.get("comments"), historical_comment_id),
    }
    return protected


def _f3_b_protected_state(
    state: Mapping[str, Any],
    issue: Mapping[str, Any],
    historical_comment_id: int,
    spec: github_f3_b_spec,
) -> dict[str, Any]:
    protected = {
        key: value
        for key, value in state.items()
        if key not in {"issues", "fixture_aliases", "protected_digest", "full_digest"}
    }
    issue_number = int(state["fixture_aliases"]["tracking_issue_number"])
    protected["other_issues"] = {
        key: value for key, value in state["issues"].items() if key != str(issue_number)
    }
    protected["tracked_issue"] = {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "body": issue.get("body"),
        "state": issue.get("state"),
        "release_blocker_label_present": spec.release_blocker_label.name in issue.get("labels", []),
        "assignees": issue.get("assignees"),
        "milestone": issue.get("milestone"),
        "historical_comment": _comment_by_id(issue.get("comments"), historical_comment_id),
    }
    return protected


def _assert_f3_a_pristine(
    state: Mapping[str, Any],
    spec: github_f3_a_spec,
    observations: Mapping[str, Any],
) -> None:
    issues = state.get("issues")
    pulls = state.get("pull_requests")
    if not isinstance(issues, Mapping) or not isinstance(pulls, Mapping):
        raise RuntimeError("F3-A authoritative state is malformed.")
    issue = issues.get(str(observations["implementation_issue_number"]), {})
    implementation_pr = pulls.get(str(observations["implementation_pr_number"]), {})
    decoy_pr = pulls.get(str(observations["decoy_pr_number"]), {})
    if not all(isinstance(item, Mapping) for item in (issue, implementation_pr, decoy_pr)):
        raise RuntimeError("F3-A tracked objects are missing from authoritative state.")
    if issue.get("state") != "closed":
        raise RuntimeError("F3-A implementation issue is not closed.")
    if issue.get("labels") != sorted(
        [spec.implemented_label.name, spec.linkage_audit_label.name]
    ):
        raise RuntimeError("F3-A implementation issue labels are not pristine.")
    if implementation_pr.get("merged") is not True or decoy_pr.get("merged") is not True:
        raise RuntimeError("F3-A candidate pull requests are not both merged.")
    if state.get("delivery_commit_on_default_branch") is not True:
        raise RuntimeError("F3-A delivery commit is not reachable from the default branch.")
    if state.get("files", {}).get(spec.target_implementation_path) != spec.target_delivered_content:
        raise RuntimeError("F3-A delivered implementation content is not pristine.")
    if len(issue.get("comments", [])) != 1:
        raise RuntimeError("F3-A historical provenance record is not pristine.")


def _assert_f3_b_pristine(
    state: Mapping[str, Any],
    spec: github_f3_b_spec,
    observations: Mapping[str, Any],
) -> None:
    issues = state.get("issues")
    pulls = state.get("pull_requests")
    if not isinstance(issues, Mapping) or not isinstance(pulls, Mapping):
        raise RuntimeError("F3-B authoritative state is malformed.")
    issue = issues.get(str(observations["tracking_issue_number"]), {})
    old_fix_pr = pulls.get(str(observations["old_fix_pr_number"]), {})
    revert_pr = pulls.get(str(observations["revert_pr_number"]), {})
    replacement_pr = pulls.get(str(observations["replacement_pr_number"]), {})
    if not all(isinstance(item, Mapping) for item in (issue, old_fix_pr, revert_pr, replacement_pr)):
        raise RuntimeError("F3-B tracked objects are missing from authoritative state.")
    if issue.get("state") != "open":
        raise RuntimeError("F3-B tracking issue is not open.")
    if issue.get("labels") != sorted(
        [spec.ready_label.name, spec.release_blocker_label.name]
    ):
        raise RuntimeError("F3-B tracking issue labels are not in the intended stale state.")
    if old_fix_pr.get("merged") is not True or revert_pr.get("merged") is not True:
        raise RuntimeError("F3-B historical fix/revert topology is not pristine.")
    if replacement_pr.get("state") != "open" or replacement_pr.get("merged") is True:
        raise RuntimeError("F3-B replacement PR is not open and unmerged.")
    if state.get("old_fix_commit_on_default_branch") is not True:
        raise RuntimeError("F3-B old fix commit is not in default-branch history.")
    if state.get("revert_commit_on_default_branch") is not True:
        raise RuntimeError("F3-B revert commit is not in default-branch history.")
    if state.get("revised_fix_commit_on_default_branch") is not False:
        raise RuntimeError("F3-B replacement fix unexpectedly reached the default branch.")
    if state.get("files", {}).get(spec.target_fix_path) != spec.target_reverted_content:
        raise RuntimeError("F3-B default-branch target does not reflect the revert.")
    if state.get("replacement_branch_target_content") != spec.target_revised_fix_content:
        raise RuntimeError("F3-B replacement branch does not contain the revised fix.")
    if len(issue.get("comments", [])) != 1:
        raise RuntimeError("F3-B historical delivery record is not pristine.")


def _snapshot_common_state(
    client: github_controller_client,
    identity: github_repository_identity,
) -> dict[str, Any]:
    branches = tuple(client.list_branches(identity.owner, identity.name))
    issues = tuple(
        item
        for item in client.list_issues(identity.owner, identity.name)
        if "pull_request" not in item
    )
    pulls = tuple(client.list_pull_requests(identity.owner, identity.name))
    labels = tuple(client.list_labels(identity.owner, identity.name))
    issue_numbers = sorted(
        int(item["number"])
        for item in issues
        if isinstance(item.get("number"), int)
    )
    pull_numbers = sorted(
        int(item["number"])
        for item in pulls
        if isinstance(item.get("number"), int)
    )
    return {
        "authoritative_source": "github_rest_api",
        "repository": {
            "id": identity.repository_id,
            "full_name": identity.full_name,
            "default_branch": identity.default_branch,
        },
        "branches": sorted(
            (
                {
                    "name": str(item.get("name")),
                    "sha": _branch_sha(item),
                    "protected": bool(item.get("protected", False)),
                }
                for item in branches
            ),
            key=lambda item: item["name"],
        ),
        "issue_catalog": sorted(
            (
                {
                    "number": int(item["number"]),
                    "title": item.get("title"),
                    "state": item.get("state"),
                }
                for item in issues
                if isinstance(item.get("number"), int)
            ),
            key=lambda item: item["number"],
        ),
        "pull_request_catalog": sorted(
            (
                {
                    "number": int(item["number"]),
                    "title": item.get("title"),
                    "state": item.get("state"),
                    "draft": bool(item.get("draft", False)),
                }
                for item in pulls
                if isinstance(item.get("number"), int)
            ),
            key=lambda item: item["number"],
        ),
        "repository_labels": sorted(
            (_label_snapshot(item) for item in labels),
            key=lambda item: item["name"],
        ),
        "issues": {
            str(number): _issue_snapshot(client, identity.owner, identity.name, number)
            for number in issue_numbers
        },
        "pull_requests": {
            str(number): _pull_snapshot(client, identity.owner, identity.name, number)
            for number in pull_numbers
        },
    }


def _issue_snapshot(
    client: github_controller_client,
    owner: str,
    repo: str,
    number: int,
) -> dict[str, Any]:
    item = client.issue(owner, repo, number)
    comments = tuple(client.issue_comments(owner, repo, number))
    return {
        "number": number,
        "title": item.get("title"),
        "body": item.get("body"),
        "state": item.get("state"),
        "labels": _label_names(item),
        "assignees": _login_names(item.get("assignees")),
        "milestone": _milestone_snapshot(item.get("milestone")),
        "comments": [_comment_snapshot(comment) for comment in comments],
    }


def _pull_snapshot(
    client: github_controller_client,
    owner: str,
    repo: str,
    number: int,
) -> dict[str, Any]:
    item = client.pull_request(owner, repo, number)
    return {
        "number": number,
        "title": item.get("title"),
        "body": item.get("body"),
        "state": item.get("state"),
        "draft": bool(item.get("draft", False)),
        "merged": item.get("merged") is True,
        "merge_commit_sha": item.get("merge_commit_sha"),
        "head": _nested_optional_string(item, "head", "sha"),
        "base": _nested_optional_string(item, "base", "sha"),
    }


def _comment_snapshot(item: Mapping[str, Any]) -> dict[str, Any]:
    user = item.get("user")
    return {
        "id": item.get("id"),
        "body": item.get("body"),
        "user": user.get("login") if isinstance(user, Mapping) else None,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _comment_by_id(value: Any, comment_id: int) -> Mapping[str, Any] | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, Mapping) and item.get("id") == comment_id:
            return item
    return None


def _label_snapshot(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": str(item.get("name")),
        "color": item.get("color"),
        "description": item.get("description"),
    }


def _label_names(value: Mapping[str, Any]) -> list[str]:
    labels = value.get("labels")
    if not isinstance(labels, list):
        return []
    names: list[str] = []
    for item in labels:
        if isinstance(item, Mapping) and isinstance(item.get("name"), str):
            names.append(str(item["name"]))
        elif isinstance(item, str):
            names.append(item)
    return sorted(names)


def _login_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, Mapping) and isinstance(item.get("login"), str):
            result.append(str(item["login"]))
    return sorted(result)


def _milestone_snapshot(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {
        "number": value.get("number"),
        "title": value.get("title"),
        "state": value.get("state"),
    }


def _branch_sha(item: Mapping[str, Any]) -> str:
    commit = item.get("commit")
    sha = commit.get("sha") if isinstance(commit, Mapping) else None
    return str(sha) if isinstance(sha, str) else ""


def _nested_optional_string(value: Mapping[str, Any], *keys: str) -> str | None:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current if isinstance(current, str) and current else None


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _json_evidence(
    evidence_id: str,
    channel: str,
    artifact: str,
    value: Mapping[str, Any],
) -> captured_evidence:
    return captured_evidence(
        id=evidence_id,
        channel=channel,
        artifact=artifact,
        content=json.dumps(value, indent=2, sort_keys=True).encode("utf-8"),
    )
