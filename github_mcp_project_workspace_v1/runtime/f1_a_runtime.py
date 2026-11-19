from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from acmm.experiment_api import (
    captured_evidence,
    observed_environment,
    prepared_environment,
)

from .controller import github_controller_client, github_repository_identity
from .f1_a import github_f1_a_materializer, github_f1_a_spec
from .world import package_owned_body, package_owned_branch


@dataclass(frozen=True)
class github_f1_a_run_handle:
    identity: github_repository_identity
    observations: Mapping[str, Any]
    initial_state: Mapping[str, Any]


class github_f1_a_fixture:
    def __init__(
        self,
        client: github_controller_client,
        materializer: github_f1_a_materializer,
        spec: github_f1_a_spec,
    ) -> None:
        self._client = client
        self._materializer = materializer
        self._spec = spec

    def prepare(self, scenario, reset) -> prepared_environment:
        del reset
        if scenario.get("id") != "f1_a_regression_disposition":
            raise ValueError("F1-A fixture received an unexpected scenario.")

        identity, observations = self._materializer.inspect()
        state = _snapshot_f1_a_state(
            self._client,
            identity,
            self._spec,
            observations,
        )
        _assert_pristine_f1_a_catalog(state, self._spec, observations)

        return prepared_environment(
            handle=github_f1_a_run_handle(
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
                "regression_issue_number": str(
                    observations["regression_issue_number"]
                ),
            },
        )

    def observe(self, scenario, handle) -> observed_environment:
        del scenario
        if not isinstance(handle, github_f1_a_run_handle):
            raise TypeError("F1-A environment handle is invalid.")
        state = _snapshot_f1_a_state(
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

    def finalize(self, scenario, handle, reset):
        del scenario
        del reset
        if not isinstance(handle, github_f1_a_run_handle):
            return {"restored": False, "detail": "invalid F1-A environment handle"}

        try:
            before = _snapshot_f1_a_state(
                self._client,
                handle.identity,
                self._spec,
                handle.observations,
            )
            if before["protected_digest"] == handle.initial_state["protected_digest"]:
                return {"restored": True, "changed": False}

            non_restorable = _restore_f1_a_state(
                self._client,
                handle.identity,
                handle.initial_state,
            )
            after = _snapshot_f1_a_state(
                self._client,
                handle.identity,
                self._spec,
                handle.observations,
            )
            restored = (
                not non_restorable
                and after["protected_digest"]
                == handle.initial_state["protected_digest"]
            )
            return {
                "restored": restored,
                "changed": True,
                "non_restorable": tuple(non_restorable),
            }
        except Exception as exc:
            return {
                "restored": False,
                "changed": True,
                "detail": str(exc) or exc.__class__.__name__,
            }


def _snapshot_f1_a_state(
    client: github_controller_client,
    identity: github_repository_identity,
    spec: github_f1_a_spec,
    observations: Mapping[str, Any],
) -> dict[str, Any]:
    owner = identity.owner
    repo = identity.name
    issue_number = int(observations["regression_issue_number"])
    original_pr_number = int(observations["original_fix_pr_number"])
    noise_issue_number = int(observations["noise_issue_number"])
    noise_pr_number = int(observations["noise_pr_number"])

    branches = tuple(client.list_branches(owner, repo))
    issues = tuple(
        item
        for item in client.list_issues(owner, repo)
        if "pull_request" not in item
    )
    pulls = tuple(client.list_pull_requests(owner, repo))
    labels = tuple(client.list_labels(owner, repo))

    tracked_issue_numbers = tuple(
        sorted(
            int(item["number"])
            for item in issues
            if isinstance(item.get("number"), int)
            and package_owned_body(item.get("body"))
        )
    )
    tracked_pr_numbers = tuple(
        sorted(
            int(item["number"])
            for item in pulls
            if isinstance(item.get("number"), int)
            and package_owned_body(item.get("body"))
        )
    )

    if issue_number not in tracked_issue_numbers or noise_issue_number not in tracked_issue_numbers:
        raise RuntimeError("F1-A package-owned issue markers are missing from repository catalog.")
    if original_pr_number not in tracked_pr_numbers or noise_pr_number not in tracked_pr_numbers:
        raise RuntimeError("F1-A package-owned pull-request markers are missing from repository catalog.")

    issue_state = {
        str(number): _issue_snapshot(
            client,
            owner,
            repo,
            number,
        )
        for number in tracked_issue_numbers
    }
    pull_state = {
        str(number): _pull_snapshot(
            client,
            owner,
            repo,
            number,
        )
        for number in tracked_pr_numbers
    }

    current_config = client.read_text_file(
        owner,
        repo,
        spec.config_path,
        ref=identity.default_branch,
    )
    original_fix_commit = str(observations["original_fix_commit"])
    fixed_config = client.read_text_file(
        owner,
        repo,
        spec.config_path,
        ref=original_fix_commit,
    )
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
                    "number": int(item.get("number")),
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
                    "number": int(item.get("number")),
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
        "issues": issue_state,
        "pull_requests": pull_state,
        "current_branch": {
            "name": identity.default_branch,
            "head_sha": _nested_string(main_ref, "object", "sha"),
            "config_path": spec.config_path,
            "config_text": current_config,
            "timeout_seconds": _timeout_from_config(current_config),
        },
        "historical_fix": {
            "commit_sha": original_fix_commit,
            "config_text": fixed_config,
            "timeout_seconds": _timeout_from_config(fixed_config),
        },
        "fixture_aliases": {
            "regression_issue_number": issue_number,
            "original_fix_pr_number": original_pr_number,
            "noise_issue_number": noise_issue_number,
            "noise_pr_number": noise_pr_number,
            "merge_commit": str(observations["merge_commit"]),
            "reintroduction_commit": str(observations["reintroduction_commit"]),
        },
    }
    digest = hashlib.sha256(_canonical_json(protected)).hexdigest()
    protected["protected_digest"] = digest
    return protected


def _assert_pristine_f1_a_catalog(
    state: Mapping[str, Any],
    spec: github_f1_a_spec,
    observations: Mapping[str, Any],
) -> None:
    branch_rows = [
        item
        for item in state.get("branches", [])
        if isinstance(item, Mapping)
    ]
    branch_names = {item.get("name") for item in branch_rows}
    repository = state.get("repository")
    default_branch = (
        repository.get("default_branch")
        if isinstance(repository, Mapping)
        else None
    )
    if not isinstance(default_branch, str) or not default_branch:
        raise RuntimeError("F1-A snapshot is missing the authoritative default branch.")
    expected_branches = {
        default_branch,
        spec.original_fix_branch,
        spec.noise_branch,
    }
    missing_branches = expected_branches - branch_names
    if missing_branches:
        raise RuntimeError(
            "F1-A repository is missing required branches: "
            + ",".join(sorted(str(value) for value in missing_branches))
        )
    unexpected_branches = {
        str(value)
        for value in branch_names - expected_branches
        if value != default_branch and not package_owned_branch(value)
    }
    if unexpected_branches:
        raise RuntimeError(
            "F1-A repository contains non-package branches: "
            + ",".join(sorted(unexpected_branches))
        )

    issue_rows = [
        item
        for item in state.get("issue_catalog", [])
        if isinstance(item, Mapping) and isinstance(item.get("number"), int)
    ]
    issue_numbers = {int(item["number"]) for item in issue_rows}
    expected_issues = {
        int(observations["regression_issue_number"]),
        int(observations["noise_issue_number"]),
    }
    if not expected_issues.issubset(issue_numbers):
        raise RuntimeError("F1-A required issue catalog entries are missing.")
    foreign_issues = [
        int(item["number"])
        for item in issue_rows
        if int(item["number"]) not in expected_issues
        and item.get("package_owned") is not True
    ]
    if foreign_issues:
        raise RuntimeError(
            "F1-A repository contains non-package issues: "
            + ",".join(str(value) for value in sorted(foreign_issues))
        )

    pull_rows = [
        item
        for item in state.get("pull_request_catalog", [])
        if isinstance(item, Mapping) and isinstance(item.get("number"), int)
    ]
    pull_numbers = {int(item["number"]) for item in pull_rows}
    expected_pulls = {
        int(observations["original_fix_pr_number"]),
        int(observations["noise_pr_number"]),
    }
    if not expected_pulls.issubset(pull_numbers):
        raise RuntimeError("F1-A required pull-request catalog entries are missing.")
    foreign_pulls = [
        int(item["number"])
        for item in pull_rows
        if int(item["number"]) not in expected_pulls
        and item.get("package_owned") is not True
    ]
    if foreign_pulls:
        raise RuntimeError(
            "F1-A repository contains non-package pull requests: "
            + ",".join(str(value) for value in sorted(foreign_pulls))
        )

    for number in expected_issues:
        issue = state.get("issues", {}).get(str(number), {})
        if not isinstance(issue, Mapping):
            raise RuntimeError(f"F1-A issue #{number} snapshot is missing.")
        if issue.get("labels") not in ([], ()):
            raise RuntimeError(f"F1-A issue #{number} has unexpected labels.")
        if issue.get("assignees") not in ([], ()):
            raise RuntimeError(f"F1-A issue #{number} has unexpected assignees.")
        if issue.get("milestone") is not None:
            raise RuntimeError(f"F1-A issue #{number} has an unexpected milestone.")
        if issue.get("comments") not in ([], ()):
            raise RuntimeError(f"F1-A issue #{number} has unexpected comments.")

    for number in expected_pulls:
        pull = state.get("pull_requests", {}).get(str(number), {})
        if not isinstance(pull, Mapping):
            raise RuntimeError(f"F1-A pull request #{number} snapshot is missing.")
        for key, label in (
            ("issue_comments", "issue comments"),
            ("review_comments", "review comments"),
            ("reviews", "reviews"),
        ):
            if pull.get(key) not in ([], ()):
                raise RuntimeError(
                    f"F1-A pull request #{number} has unexpected {label}."
                )


def _restore_f1_a_state(
    client: github_controller_client,
    identity: github_repository_identity,
    expected: Mapping[str, Any],
) -> list[str]:
    owner = identity.owner
    repo = identity.name
    non_restorable: list[str] = []

    expected_branches = {
        str(item["name"]): str(item["sha"])
        for item in expected.get("branches", [])
        if isinstance(item, Mapping)
    }
    current_branches = {
        str(item.get("name")): _branch_sha(item)
        for item in client.list_branches(owner, repo)
    }
    for name in sorted(set(current_branches) - set(expected_branches)):
        if name == identity.default_branch:
            non_restorable.append(f"unexpected default branch {name}")
            continue
        client.delete_ref(owner, repo, name)
    for name, sha in expected_branches.items():
        current = current_branches.get(name)
        if current is None:
            client.create_ref(owner, repo, name, sha)
        elif current != sha:
            client.update_ref(owner, repo, name, sha, force=True)

    for number_text, issue in expected.get("issues", {}).items():
        if not isinstance(issue, Mapping):
            continue
        number = int(number_text)
        issue_payload = {
            "title": issue.get("title"),
            "body": issue.get("body"),
            "state": issue.get("state"),
            "labels": list(issue.get("labels", [])),
            "assignees": list(issue.get("assignees", [])),
            "milestone": _milestone_number(issue.get("milestone")),
        }
        if isinstance(issue.get("state_reason"), str):
            issue_payload["state_reason"] = issue.get("state_reason")
        client.update_issue(owner, repo, number, issue_payload)
        _restore_issue_comments(
            client,
            owner,
            repo,
            number,
            issue.get("comments", []),
        )

    for number_text, pull in expected.get("pull_requests", {}).items():
        if not isinstance(pull, Mapping):
            continue
        number = int(number_text)
        current = client.pull_request(owner, repo, number)
        expected_merged = bool(pull.get("merged", False))
        current_merged = bool(current.get("merged", False))
        if expected_merged != current_merged:
            non_restorable.append(f"pull request #{number} merge state changed")
        expected_draft = bool(pull.get("draft", False))
        current_draft = bool(current.get("draft", False))
        if expected_draft != current_draft:
            non_restorable.append(f"pull request #{number} draft state changed")

        payload = {
            "title": pull.get("title"),
            "body": pull.get("body"),
            "state": pull.get("state"),
            "base": _nested_optional_string(pull, "base", "ref"),
        }
        if not current_merged:
            client.update_pull_request(owner, repo, number, payload)
        else:
            client.update_pull_request(
                owner,
                repo,
                number,
                {"title": pull.get("title"), "body": pull.get("body")},
            )

        _restore_issue_comments(
            client,
            owner,
            repo,
            number,
            pull.get("issue_comments", []),
        )
        _restore_review_comments(
            client,
            owner,
            repo,
            number,
            pull.get("review_comments", []),
        )
        _restore_reviews(
            client,
            owner,
            repo,
            number,
            pull.get("reviews", []),
            non_restorable,
        )

    _restore_repository_labels(
        client,
        owner,
        repo,
        expected.get("repository_labels", []),
    )

    expected_issue_numbers = {
        int(item["number"])
        for item in expected.get("issue_catalog", [])
        if isinstance(item, Mapping) and isinstance(item.get("number"), int)
    }
    current_issue_numbers = {
        int(item["number"])
        for item in client.list_issues(owner, repo)
        if "pull_request" not in item and isinstance(item.get("number"), int)
    }
    for number in sorted(current_issue_numbers - expected_issue_numbers):
        client.update_issue(owner, repo, number, {"state": "closed"})
        non_restorable.append(f"unexpected issue #{number} remains in repository history")

    expected_pull_numbers = {
        int(item["number"])
        for item in expected.get("pull_request_catalog", [])
        if isinstance(item, Mapping) and isinstance(item.get("number"), int)
    }
    current_pull_numbers = {
        int(item["number"])
        for item in client.list_pull_requests(owner, repo)
        if isinstance(item.get("number"), int)
    }
    for number in sorted(current_pull_numbers - expected_pull_numbers):
        current = client.pull_request(owner, repo, number)
        if current.get("merged") is not True:
            client.update_pull_request(owner, repo, number, {"state": "closed"})
        non_restorable.append(
            f"unexpected pull request #{number} remains in repository history"
        )

    return non_restorable


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
        "issue_comments": _comments_snapshot(
            client.issue_comments(owner, repo, number)
        ),
        "review_comments": _comments_snapshot(
            client.pull_request_review_comments(owner, repo, number)
        ),
        "reviews": _reviews_snapshot(
            client.pull_request_reviews(owner, repo, number)
        ),
    }


def _comments_snapshot(items) -> list[dict[str, Any]]:
    values = []
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
    values = []
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


def _restore_issue_comments(
    client: github_controller_client,
    owner: str,
    repo: str,
    number: int,
    expected_items,
) -> None:
    expected = {
        int(item["id"]): item
        for item in expected_items
        if isinstance(item, Mapping) and isinstance(item.get("id"), int)
    }
    current = {
        int(item["id"]): item
        for item in client.issue_comments(owner, repo, number)
        if isinstance(item.get("id"), int)
    }
    for comment_id in sorted(set(current) - set(expected)):
        client.delete_issue_comment(owner, repo, comment_id)
    for comment_id, expected_item in expected.items():
        current_item = current.get(comment_id)
        if current_item is None:
            continue
        if current_item.get("body") != expected_item.get("body"):
            client.update_issue_comment(
                owner,
                repo,
                comment_id,
                str(expected_item.get("body") or ""),
            )


def _restore_review_comments(
    client: github_controller_client,
    owner: str,
    repo: str,
    number: int,
    expected_items,
) -> None:
    expected = {
        int(item["id"]): item
        for item in expected_items
        if isinstance(item, Mapping) and isinstance(item.get("id"), int)
    }
    current = {
        int(item["id"]): item
        for item in client.pull_request_review_comments(owner, repo, number)
        if isinstance(item.get("id"), int)
    }
    for comment_id in sorted(set(current) - set(expected)):
        client.delete_pull_request_review_comment(owner, repo, comment_id)
    for comment_id, expected_item in expected.items():
        current_item = current.get(comment_id)
        if current_item is None:
            continue
        if current_item.get("body") != expected_item.get("body"):
            client.update_pull_request_review_comment(
                owner,
                repo,
                comment_id,
                str(expected_item.get("body") or ""),
            )


def _restore_reviews(
    client: github_controller_client,
    owner: str,
    repo: str,
    number: int,
    expected_items,
    non_restorable: list[str],
) -> None:
    expected_ids = {
        int(item["id"])
        for item in expected_items
        if isinstance(item, Mapping) and isinstance(item.get("id"), int)
    }
    current = client.pull_request_reviews(owner, repo, number)
    for review in current:
        review_id = review.get("id")
        if not isinstance(review_id, int) or review_id in expected_ids:
            continue
        if str(review.get("state") or "").upper() == "PENDING":
            client.delete_pending_pull_request_review(owner, repo, number, review_id)
        else:
            non_restorable.append(
                f"pull request #{number} has submitted review {review_id}"
            )


def _restore_repository_labels(
    client: github_controller_client,
    owner: str,
    repo: str,
    expected_items,
) -> None:
    expected = {
        str(item["name"]): item
        for item in expected_items
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    }
    current = {
        str(item.get("name")): item
        for item in client.list_labels(owner, repo)
        if isinstance(item.get("name"), str)
    }
    for name in sorted(set(current) - set(expected)):
        client.delete_label(owner, repo, name)
    for name, item in expected.items():
        color = str(item.get("color") or "000000")
        description = item.get("description")
        if name not in current:
            client.create_label(
                owner,
                repo,
                label=name,
                color=color,
                description=description if isinstance(description, str) else None,
            )
            continue
        current_item = _label_snapshot(current[name])
        if current_item != item:
            client.update_label(
                owner,
                repo,
                name,
                new_name=name,
                color=color,
                description=description if isinstance(description, str) else None,
            )


def _label_snapshot(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": str(item.get("name") or ""),
        "color": str(item.get("color") or ""),
        "description": item.get("description"),
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


def _milestone_snapshot(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    number = value.get("number")
    if not isinstance(number, int):
        return None
    return {"number": number, "title": value.get("title")}


def _milestone_number(value: Any) -> int | None:
    if isinstance(value, Mapping) and isinstance(value.get("number"), int):
        return int(value["number"])
    return None


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


def _timeout_from_config(text: str) -> int:
    value = json.loads(text)
    if not isinstance(value, Mapping):
        raise RuntimeError("F1-A synchronization configuration is not an object.")
    timeout = value.get("default_synchronization_timeout_seconds")
    if not isinstance(timeout, int):
        raise RuntimeError("F1-A synchronization timeout is not an integer.")
    return timeout


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
