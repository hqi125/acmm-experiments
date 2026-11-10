from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from acmm.experiment_api import captured_evidence, observed_environment, prepared_environment

from .controller import github_controller_client, github_repository_identity
from .f2 import (
    github_f2_a_materializer,
    github_f2_a_spec,
    github_f2_b_materializer,
    github_f2_b_spec,
)


@dataclass(frozen=True)
class github_f2_a_run_handle:
    identity: github_repository_identity
    observations: Mapping[str, Any]
    initial_state: Mapping[str, Any]


@dataclass(frozen=True)
class github_f2_b_run_handle:
    identity: github_repository_identity
    observations: Mapping[str, Any]
    initial_state: Mapping[str, Any]


class github_f2_a_fixture:
    def __init__(
        self,
        client: github_controller_client,
        materializer: github_f2_a_materializer,
        spec: github_f2_a_spec,
    ) -> None:
        self._client = client
        self._materializer = materializer
        self._spec = spec

    def prepare(self, scenario, reset) -> prepared_environment:
        del reset
        if scenario.get("id") != "f2_a_incoming_regression_triage":
            raise ValueError("F2-A fixture received an unexpected scenario.")
        identity, observations = self._materializer.inspect()
        state = _snapshot_f2_a_state(self._client, identity, self._spec, observations)
        _assert_f2_a_pristine(state, self._spec, observations)
        return prepared_environment(
            handle=github_f2_a_run_handle(identity, dict(observations), state),
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
                "incoming_issue_number": str(observations["incoming_issue_number"]),
            },
        )

    def observe(self, scenario, handle) -> observed_environment:
        del scenario
        if not isinstance(handle, github_f2_a_run_handle):
            raise TypeError("F2-A environment handle is invalid.")
        state = _snapshot_f2_a_state(
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


class github_f2_b_fixture:
    def __init__(
        self,
        client: github_controller_client,
        materializer: github_f2_b_materializer,
        spec: github_f2_b_spec,
    ) -> None:
        self._client = client
        self._materializer = materializer
        self._spec = spec

    def prepare(self, scenario, reset) -> prepared_environment:
        del reset
        if scenario.get("id") != "f2_b_stale_work_item_maintenance":
            raise ValueError("F2-B fixture received an unexpected scenario.")
        identity, observations = self._materializer.inspect()
        state = _snapshot_f2_b_state(self._client, identity, self._spec, observations)
        _assert_f2_b_pristine(state, self._spec, observations)
        return prepared_environment(
            handle=github_f2_b_run_handle(identity, dict(observations), state),
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
                "work_item_number": str(observations["work_item_number"]),
            },
        )

    def observe(self, scenario, handle) -> observed_environment:
        del scenario
        if not isinstance(handle, github_f2_b_run_handle):
            raise TypeError("F2-B environment handle is invalid.")
        state = _snapshot_f2_b_state(
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


def _snapshot_f2_a_state(
    client: github_controller_client,
    identity: github_repository_identity,
    spec: github_f2_a_spec,
    observations: Mapping[str, Any],
) -> dict[str, Any]:
    common = _snapshot_common_state(client, identity)
    incoming_number = int(observations["incoming_issue_number"])
    canonical_number = int(observations["canonical_issue_number"])
    decoy_number = int(observations["decoy_issue_number"])
    issues = common["issues"]
    incoming = issues.get(str(incoming_number), {})

    state = {
        **common,
        "files": {
            spec.triage_policy_path: client.read_text_file(
                identity.owner,
                identity.name,
                spec.triage_policy_path,
                ref=identity.default_branch,
            ),
            spec.csv_test_path: client.read_text_file(
                identity.owner,
                identity.name,
                spec.csv_test_path,
                ref=identity.default_branch,
            ),
        },
        "fixture_aliases": {
            "incoming_issue_number": incoming_number,
            "canonical_issue_number": canonical_number,
            "decoy_issue_number": decoy_number,
            "duplicate_label": spec.duplicate_label.name,
            "needs_triage_label": spec.needs_triage_label.name,
        },
    }
    protected = {
        key: value
        for key, value in state.items()
        if key not in {"issues", "fixture_aliases"}
    }
    protected_issues = {
        key: value
        for key, value in issues.items()
        if key != str(incoming_number)
    }
    protected["issues"] = protected_issues
    protected["issue_catalog"] = [
        (
            {"number": item.get("number"), "title": item.get("title")}
            if item.get("number") == incoming_number
            else item
        )
        for item in state.get("issue_catalog", [])
        if isinstance(item, Mapping)
    ]
    protected["incoming_issue_protected"] = {
        "number": incoming.get("number"),
        "title": incoming.get("title"),
        "body": incoming.get("body"),
        "assignees": incoming.get("assignees"),
        "milestone": incoming.get("milestone"),
    }
    state["protected_digest"] = _digest(protected)
    state["full_digest"] = _digest(state)
    return state


def _snapshot_f2_b_state(
    client: github_controller_client,
    identity: github_repository_identity,
    spec: github_f2_b_spec,
    observations: Mapping[str, Any],
) -> dict[str, Any]:
    common = _snapshot_common_state(client, identity)
    commits = tuple(client.list_commits(identity.owner, identity.name, sha=identity.default_branch))
    commit_shas = [str(item.get("sha")) for item in commits if isinstance(item.get("sha"), str)]
    state = {
        **common,
        "files": {
            spec.triage_policy_path: client.read_text_file(
                identity.owner,
                identity.name,
                spec.triage_policy_path,
                ref=identity.default_branch,
            ),
        },
        "default_branch_history": commit_shas,
        "dependency_fix_on_default_branch": observations["dependency_fix_commit"] in commit_shas,
        "fixture_aliases": {
            "work_item_number": int(observations["work_item_number"]),
            "dependency_issue_number": int(observations["dependency_issue_number"]),
            "dependency_pr_number": int(observations["dependency_pr_number"]),
            "noise_issue_number": int(observations["noise_issue_number"]),
            "dependency_fix_commit": str(observations["dependency_fix_commit"]),
            "dependency_merge_commit": str(observations["dependency_merge_commit"]),
            "ready_label": spec.ready_label.name,
            "blocked_label": spec.blocked_label.name,
        },
    }
    state["protected_digest"] = _digest(state)
    return state


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


def _assert_f2_a_pristine(
    state: Mapping[str, Any],
    spec: github_f2_a_spec,
    observations: Mapping[str, Any],
) -> None:
    aliases = state.get("fixture_aliases")
    issues = state.get("issues")
    if not isinstance(aliases, Mapping) or not isinstance(issues, Mapping):
        raise RuntimeError("F2-A authoritative state is malformed.")
    incoming = issues.get(str(observations["incoming_issue_number"]), {})
    canonical = issues.get(str(observations["canonical_issue_number"]), {})
    decoy = issues.get(str(observations["decoy_issue_number"]), {})
    if not all(isinstance(item, Mapping) for item in (incoming, canonical, decoy)):
        raise RuntimeError("F2-A tracked issues are missing from authoritative state.")
    if incoming.get("state") != "open" or incoming.get("labels") != [spec.needs_triage_label.name]:
        raise RuntimeError("F2-A incoming issue is not pristine.")
    if incoming.get("comments") != []:
        raise RuntimeError("F2-A incoming issue has unexpected seeded comments.")
    if spec.confirmed_bug_label.name not in canonical.get("labels", []):
        raise RuntimeError("F2-A canonical issue is missing confirmed-bug metadata.")
    if spec.confirmed_bug_label.name not in decoy.get("labels", []):
        raise RuntimeError("F2-A decoy issue is missing confirmed-bug metadata.")


def _assert_f2_b_pristine(
    state: Mapping[str, Any],
    spec: github_f2_b_spec,
    observations: Mapping[str, Any],
) -> None:
    issues = state.get("issues")
    pulls = state.get("pull_requests")
    if not isinstance(issues, Mapping) or not isinstance(pulls, Mapping):
        raise RuntimeError("F2-B authoritative state is malformed.")
    work = issues.get(str(observations["work_item_number"]), {})
    dependency = issues.get(str(observations["dependency_issue_number"]), {})
    pull = pulls.get(str(observations["dependency_pr_number"]), {})
    if not all(isinstance(item, Mapping) for item in (work, dependency, pull)):
        raise RuntimeError("F2-B tracked objects are missing from authoritative state.")
    if work.get("state") != "open" or work.get("labels") != [spec.ready_label.name]:
        raise RuntimeError("F2-B work item current status is not pristine.")
    if dependency.get("state") != "closed" or pull.get("merged") is not True:
        raise RuntimeError("F2-B dependency is not authoritatively resolved.")
    if state.get("dependency_fix_on_default_branch") is not True:
        raise RuntimeError("F2-B dependency fix is not present on the default branch.")
    if len(work.get("comments", [])) != 2:
        raise RuntimeError("F2-B work item audit-history comments are not pristine.")


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

