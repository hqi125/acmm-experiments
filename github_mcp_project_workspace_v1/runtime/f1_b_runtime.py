from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from acmm.experiment_api import captured_evidence, observed_environment, prepared_environment

from .controller import github_controller_client, github_repository_identity
from .f1_b import github_f1_b_materializer, github_f1_b_spec
from .world import package_owned_body


@dataclass(frozen=True)
class github_f1_b_run_handle:
    identity: github_repository_identity
    observations: Mapping[str, Any]
    initial_state: Mapping[str, Any]


class github_f1_b_fixture:
    def __init__(
        self,
        client: github_controller_client,
        materializer: github_f1_b_materializer,
        spec: github_f1_b_spec,
    ) -> None:
        self._client = client
        self._materializer = materializer
        self._spec = spec

    def prepare(self, scenario, reset) -> prepared_environment:
        del reset
        if scenario.get("id") != "f1_b_release_candidate_status":
            raise ValueError("F1-B fixture received an unexpected scenario.")

        identity, observations = self._materializer.inspect()
        state = _snapshot_f1_b_state(
            self._client,
            identity,
            self._spec,
            observations,
        )
        _assert_pristine_f1_b_catalog(state, self._spec, observations)

        return prepared_environment(
            handle=github_f1_b_run_handle(
                identity=identity,
                observations=dict(observations),
                initial_state=state,
            ),
            provenance={
                "fixture": self._spec.fixture_id,
                "configuration": {
                    "repository_name": identity.name,
                },
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
                "release_branch": self._spec.release_branch,
                "release_milestone": self._spec.milestone_title,
                "blocker_label": self._spec.blocker_label_name,
                "required_workflow_name": self._spec.workflow_name,
            },
        )

    def observe(self, scenario, handle) -> observed_environment:
        del scenario
        if not isinstance(handle, github_f1_b_run_handle):
            raise TypeError("F1-B environment handle is invalid.")
        state = _snapshot_f1_b_state(
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


def _snapshot_f1_b_state(
    client: github_controller_client,
    identity: github_repository_identity,
    spec: github_f1_b_spec,
    observations: Mapping[str, Any],
) -> dict[str, Any]:
    owner = identity.owner
    repo = identity.name

    branches = tuple(client.list_branches(owner, repo))
    issues = tuple(
        item
        for item in client.list_issues(owner, repo)
        if "pull_request" not in item
    )
    pulls = tuple(client.list_pull_requests(owner, repo))
    labels = tuple(client.list_labels(owner, repo))
    milestones = tuple(client.list_milestones(owner, repo))

    issue_numbers = tuple(
        sorted(
            int(item["number"])
            for item in issues
            if isinstance(item.get("number"), int)
        )
    )
    pull_numbers = tuple(
        sorted(
            int(item["number"])
            for item in pulls
            if isinstance(item.get("number"), int)
        )
    )

    issue_state = {
        str(number): _issue_snapshot(client, owner, repo, number)
        for number in issue_numbers
    }
    pull_state = {
        str(number): _pull_snapshot(client, owner, repo, number)
        for number in pull_numbers
    }

    workflow_catalog = client.list_workflows(owner, repo)
    workflows = workflow_catalog.get("workflows")
    if not isinstance(workflows, list):
        raise RuntimeError("F1-B workflow catalog is malformed.")
    required_workflows = [
        item
        for item in workflows
        if isinstance(item, Mapping)
        and item.get("name") == spec.workflow_name
        and item.get("path") == spec.workflow_path
    ]
    if len(required_workflows) != 1:
        raise RuntimeError("F1-B required workflow is missing or duplicated.")
    workflow_id = required_workflows[0].get("id")
    if not isinstance(workflow_id, int):
        raise RuntimeError("F1-B required workflow omitted numeric ID.")

    run_catalog = client.list_workflow_runs_for_workflow(
        owner,
        repo,
        workflow_id,
        branch=spec.release_branch,
        event="workflow_dispatch",
        per_page=100,
    )
    run_rows = run_catalog.get("workflow_runs")
    if not isinstance(run_rows, list):
        raise RuntimeError("F1-B required workflow run catalog is malformed.")
    workflow_runs = sorted(
        (
            _workflow_run_snapshot(item)
            for item in run_rows
            if isinstance(item, Mapping)
        ),
        key=lambda item: int(item["id"]),
    )

    included_fix_commit = str(observations["included_fix_commit"])
    missing_fix_commit = str(observations["missing_fix_commit"])
    candidate_history = tuple(
        client.list_commits(
            owner,
            repo,
            sha=spec.release_branch,
            per_page=100,
        )
    )
    candidate_history_shas = sorted(
        str(item["sha"])
        for item in candidate_history
        if isinstance(item.get("sha"), str)
    )

    release_ref = client.ref(owner, repo, f"heads/{spec.release_branch}")
    main_ref = client.ref(owner, repo, f"heads/{identity.default_branch}")

    protected = {
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
                    "package_owned": package_owned_body(item.get("body")),
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
                    "package_owned": package_owned_body(item.get("body")),
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
        "milestones": sorted(
            (_milestone_full_snapshot(item) for item in milestones),
            key=lambda item: item["number"],
        ),
        "issues": issue_state,
        "pull_requests": pull_state,
        "release_candidate": {
            "branch": spec.release_branch,
            "head_sha": _nested_string(release_ref, "object", "sha"),
            "default_branch_head_sha": _nested_string(main_ref, "object", "sha"),
            "candidate_path": spec.candidate_path,
            "candidate_text": client.read_text_file(
                owner,
                repo,
                spec.candidate_path,
                ref=spec.release_branch,
            ),
            "included_fix_commit": included_fix_commit,
            "included_fix_present": included_fix_commit in candidate_history_shas,
            "missing_fix_commit": missing_fix_commit,
            "missing_fix_present": missing_fix_commit in candidate_history_shas,
            "history_shas": candidate_history_shas,
        },
        "required_checks": {
            "workflow": {
                "id": workflow_id,
                "name": spec.workflow_name,
                "path": spec.workflow_path,
                "state": required_workflows[0].get("state"),
            },
            "runs": workflow_runs,
            "required_run_id": observations.get("required_workflow_run_id"),
        },
        "fixture_aliases": {
            "milestone_number": int(observations["milestone_number"]),
            "release_pr_number": int(observations["release_pr_number"]),
            "included_issue_number": int(observations["included_issue_number"]),
            "included_pr_number": int(observations["included_pr_number"]),
            "included_fix_commit": included_fix_commit,
            "missing_issue_number": int(observations["missing_issue_number"]),
            "missing_pr_number": int(observations["missing_pr_number"]),
            "missing_fix_commit": missing_fix_commit,
            "noise_issue_number": int(observations["noise_issue_number"]),
            "required_workflow_run_id": int(observations["required_workflow_run_id"]),
        },
    }
    protected["protected_digest"] = hashlib.sha256(_canonical_json(protected)).hexdigest()
    return protected


def _assert_pristine_f1_b_catalog(
    state: Mapping[str, Any],
    spec: github_f1_b_spec,
    observations: Mapping[str, Any],
) -> None:
    branch_rows = [item for item in state.get("branches", []) if isinstance(item, Mapping)]
    branch_names = {item.get("name") for item in branch_rows}
    expected_branches = {
        "main",
        spec.included.fix_branch,
        spec.release_branch,
        spec.missing.fix_branch,
    }
    if branch_names != expected_branches:
        raise RuntimeError(
            "F1-B disposable repository branch catalog does not match the scenario blueprint; "
            f"expected={sorted(expected_branches)!r}, observed={sorted(str(x) for x in branch_names)!r}."
        )

    issue_catalog = [
        item for item in state.get("issue_catalog", []) if isinstance(item, Mapping)
    ]
    pull_catalog = [
        item for item in state.get("pull_request_catalog", []) if isinstance(item, Mapping)
    ]
    if len(issue_catalog) != 3 or any(item.get("package_owned") is not True for item in issue_catalog):
        raise RuntimeError("F1-B disposable repository contains unexpected issue state.")
    if len(pull_catalog) != 3 or any(item.get("package_owned") is not True for item in pull_catalog):
        raise RuntimeError("F1-B disposable repository contains unexpected pull-request state.")

    expected_issue_numbers = {
        int(observations["included_issue_number"]),
        int(observations["missing_issue_number"]),
        int(observations["noise_issue_number"]),
    }
    observed_issue_numbers = {int(item["number"]) for item in issue_catalog}
    if observed_issue_numbers != expected_issue_numbers:
        raise RuntimeError("F1-B issue catalog does not match the scenario aliases.")

    expected_pr_numbers = {
        int(observations["included_pr_number"]),
        int(observations["missing_pr_number"]),
        int(observations["release_pr_number"]),
    }
    observed_pr_numbers = {int(item["number"]) for item in pull_catalog}
    if observed_pr_numbers != expected_pr_numbers:
        raise RuntimeError("F1-B pull-request catalog does not match the scenario aliases.")

    candidate = state.get("release_candidate")
    checks = state.get("required_checks")
    if not isinstance(candidate, Mapping) or not isinstance(checks, Mapping):
        raise RuntimeError("F1-B authoritative candidate/check state is missing.")
    if candidate.get("included_fix_present") is not True:
        raise RuntimeError("F1-B candidate is missing the included blocker fix.")
    if candidate.get("missing_fix_present") is not False:
        raise RuntimeError("F1-B candidate unexpectedly contains the designated missing fix.")

    required_run_id = checks.get("required_run_id")
    runs = checks.get("runs")
    if not isinstance(required_run_id, int) or not isinstance(runs, list):
        raise RuntimeError("F1-B required-check state is incomplete.")
    required_run = next(
        (item for item in runs if isinstance(item, Mapping) and item.get("id") == required_run_id),
        None,
    )
    if not isinstance(required_run, Mapping):
        raise RuntimeError("F1-B required-check run is absent from authoritative state.")
    if required_run.get("status") != "completed" or required_run.get("conclusion") != "success":
        raise RuntimeError("F1-B required-check run is not completed successfully.")


def _issue_snapshot(
    client: github_controller_client,
    owner: str,
    repo: str,
    number: int,
) -> dict[str, Any]:
    issue = client.issue(owner, repo, number)
    return {
        "number": number,
        "title": issue.get("title"),
        "body": issue.get("body"),
        "state": issue.get("state"),
        "state_reason": issue.get("state_reason"),
        "labels": sorted(_label_names(issue.get("labels"))),
        "assignees": sorted(_login_names(issue.get("assignees"))),
        "milestone": _milestone_snapshot(issue.get("milestone")),
        "comments": _comments_snapshot(client.issue_comments(owner, repo, number)),
    }


def _pull_snapshot(
    client: github_controller_client,
    owner: str,
    repo: str,
    number: int,
) -> dict[str, Any]:
    pull = client.pull_request(owner, repo, number)
    return {
        "number": number,
        "title": pull.get("title"),
        "body": pull.get("body"),
        "state": pull.get("state"),
        "draft": bool(pull.get("draft", False)),
        "merged": bool(pull.get("merged", False)),
        "merged_at": pull.get("merged_at"),
        "merge_commit_sha": pull.get("merge_commit_sha"),
        "head": {
            "ref": _nested_optional_string(pull, "head", "ref"),
            "sha": _nested_optional_string(pull, "head", "sha"),
        },
        "base": {
            "ref": _nested_optional_string(pull, "base", "ref"),
            "sha": _nested_optional_string(pull, "base", "sha"),
        },
        "issue_comments": _comments_snapshot(client.issue_comments(owner, repo, number)),
        "review_comments": _comments_snapshot(
            client.pull_request_review_comments(owner, repo, number)
        ),
        "reviews": _reviews_snapshot(client.pull_request_reviews(owner, repo, number)),
    }


def _comments_snapshot(items) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in items:
        comment_id = item.get("id")
        if not isinstance(comment_id, int):
            continue
        user = item.get("user")
        values.append(
            {
                "id": comment_id,
                "body": item.get("body"),
                "user": user.get("login") if isinstance(user, Mapping) else None,
            }
        )
    return sorted(values, key=lambda item: item["id"])


def _reviews_snapshot(items) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in items:
        review_id = item.get("id")
        if not isinstance(review_id, int):
            continue
        user = item.get("user")
        values.append(
            {
                "id": review_id,
                "state": item.get("state"),
                "body": item.get("body"),
                "commit_id": item.get("commit_id"),
                "user": user.get("login") if isinstance(user, Mapping) else None,
            }
        )
    return sorted(values, key=lambda item: item["id"])


def _label_snapshot(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": str(item.get("name") or ""),
        "color": str(item.get("color") or ""),
        "description": item.get("description"),
    }


def _milestone_full_snapshot(item: Mapping[str, Any]) -> dict[str, Any]:
    number = item.get("number")
    if not isinstance(number, int):
        raise RuntimeError("GitHub milestone catalog omitted numeric milestone number.")
    return {
        "number": number,
        "title": item.get("title"),
        "description": item.get("description"),
        "state": item.get("state"),
    }


def _milestone_snapshot(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or not isinstance(value.get("number"), int):
        return None
    return {
        "number": int(value["number"]),
        "title": value.get("title"),
    }


def _workflow_run_snapshot(item: Mapping[str, Any]) -> dict[str, Any]:
    run_id = item.get("id")
    if not isinstance(run_id, int):
        raise RuntimeError("GitHub Actions run omitted numeric ID.")
    return {
        "id": run_id,
        "name": item.get("name"),
        "event": item.get("event"),
        "head_branch": item.get("head_branch"),
        "head_sha": item.get("head_sha"),
        "status": item.get("status"),
        "conclusion": item.get("conclusion"),
        "run_attempt": item.get("run_attempt"),
    }


def _label_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, Mapping) and isinstance(item.get("name"), str):
            names.append(item["name"])
        elif isinstance(item, str):
            names.append(item)
    return names


def _login_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, Mapping) and isinstance(item.get("login"), str):
            names.append(item["login"])
        elif isinstance(item, str):
            names.append(item)
    return names


def _branch_sha(item: Mapping[str, Any]) -> str:
    commit = item.get("commit")
    if isinstance(commit, Mapping) and isinstance(commit.get("sha"), str):
        return str(commit["sha"])
    raise RuntimeError("GitHub branch listing omitted commit SHA.")


def _nested_string(value: Mapping[str, Any], *keys: str) -> str:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            raise RuntimeError("GitHub response omitted required nested object.")
        current = current.get(key)
    if not isinstance(current, str) or not current:
        raise RuntimeError("GitHub response omitted required nested string.")
    return current


def _nested_optional_string(value: Mapping[str, Any], *keys: str) -> str | None:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current if isinstance(current, str) else None


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _json_evidence(
    evidence_id: str,
    channel: str,
    artifact: str,
    value: Any,
) -> captured_evidence:
    return captured_evidence(
        id=evidence_id,
        channel=channel,
        artifact=artifact,
        content=_canonical_json(value),
    )
