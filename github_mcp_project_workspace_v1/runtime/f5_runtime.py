from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from acmm.experiment_api import captured_evidence, observed_environment, prepared_environment

from .controller import github_controller_client, github_controller_error, github_repository_identity
from .slice_restore import restore_branch_refs, restore_issue_snapshot, restore_repository_labels
from .f5 import github_f5_a_materializer, github_f5_a_spec, github_f5_b_materializer, github_f5_b_spec


@dataclass(frozen=True)
class github_f5_a_run_handle:
    identity: github_repository_identity
    observations: dict[str, Any]
    initial_state: dict[str, Any]


@dataclass(frozen=True)
class github_f5_b_run_handle:
    identity: github_repository_identity
    observations: dict[str, Any]
    initial_state: dict[str, Any]


class github_f5_a_fixture:
    def __init__(
        self,
        client: github_controller_client,
        materializer: github_f5_a_materializer,
        spec: github_f5_a_spec,
    ) -> None:
        self._client = client
        self._materializer = materializer
        self._spec = spec

    def prepare(self, scenario, reset) -> prepared_environment:
        del reset
        if scenario.get("id") != "f5_a_targeted_code_fix":
            raise ValueError("F5-A fixture received an unexpected scenario.")
        identity, observations = self._materializer.inspect()
        state = _snapshot_f5_a_state(self._client, identity, self._spec, observations)
        _assert_f5_a_pristine(state, self._spec)
        return prepared_environment(
            handle=github_f5_a_run_handle(identity, dict(observations), state),
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
                "retry_issue_number": str(observations["retry_issue_number"]),
                "retry_source_path": self._spec.retry_source_path,
                "retry_tests_path": self._spec.retry_tests_path,
            },
        )

    def observe(self, scenario, handle) -> observed_environment:
        del scenario
        if not isinstance(handle, github_f5_a_run_handle):
            raise TypeError("F5-A environment handle is invalid.")
        state = _snapshot_f5_a_state(
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
            )
        )

    def finalize(self, scenario, handle, reset):
        del scenario
        del reset
        if not isinstance(handle, github_f5_a_run_handle):
            return {"restored": False, "detail": "invalid F5-A environment handle"}
        return _restore_f5_slice(
            self._client,
            handle.identity,
            self._spec,
            handle.observations,
            handle.initial_state,
            snapshot=lambda: _snapshot_f5_a_state(
                self._client, handle.identity, self._spec, handle.observations
            ),
        )


class github_f5_b_fixture:
    def __init__(
        self,
        client: github_controller_client,
        materializer: github_f5_b_materializer,
        spec: github_f5_b_spec,
    ) -> None:
        self._client = client
        self._materializer = materializer
        self._spec = spec

    def prepare(self, scenario, reset) -> prepared_environment:
        del reset
        if scenario.get("id") != "f5_b_release_metadata_sync":
            raise ValueError("F5-B fixture received an unexpected scenario.")
        identity, observations = self._materializer.inspect()
        state = _snapshot_f5_b_state(self._client, identity, self._spec, observations)
        _assert_f5_b_pristine(state, self._spec)
        return prepared_environment(
            handle=github_f5_b_run_handle(identity, dict(observations), state),
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
                "release_authority_path": self._spec.release_authority_path,
                "maintenance_policy_path": self._spec.maintenance_policy_path,
            },
        )

    def observe(self, scenario, handle) -> observed_environment:
        del scenario
        if not isinstance(handle, github_f5_b_run_handle):
            raise TypeError("F5-B environment handle is invalid.")
        state = _snapshot_f5_b_state(
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
            )
        )

    def finalize(self, scenario, handle, reset):
        del scenario
        del reset
        if not isinstance(handle, github_f5_b_run_handle):
            return {"restored": False, "detail": "invalid F5-B environment handle"}
        return _restore_f5_slice(
            self._client,
            handle.identity,
            self._spec,
            handle.observations,
            handle.initial_state,
            snapshot=lambda: _snapshot_f5_b_state(
                self._client, handle.identity, self._spec, handle.observations
            ),
        )


def _snapshot_f5_a_state(
    client: github_controller_client,
    identity: github_repository_identity,
    spec: github_f5_a_spec,
    observations: Mapping[str, Any],
) -> dict[str, Any]:
    issue_number = int(observations["retry_issue_number"])
    common = _snapshot_common(client, identity)
    state = {
        **common,
        "default_branch_files": {
            spec.retry_source_path: client.read_text_file(
                identity.owner,
                identity.name,
                spec.retry_source_path,
                ref=identity.default_branch,
            ),
            spec.retry_tests_path: client.read_text_file(
                identity.owner,
                identity.name,
                spec.retry_tests_path,
                ref=identity.default_branch,
            ),
        },
        "retry_issue": _issue_snapshot(client, identity, issue_number),
        "candidate_branches": _candidate_branch_files(
            client,
            identity,
            (spec.retry_source_path, spec.retry_tests_path),
        ),
        "fixture_aliases": {
            "retry_issue_number": issue_number,
            "retry_source_path": spec.retry_source_path,
            "retry_tests_path": spec.retry_tests_path,
            "base_branch": identity.default_branch,
        },
    }
    state["protected_digest"] = _f5_protected_digest(state)
    state["full_digest"] = _digest(state)
    return state


def _snapshot_f5_b_state(
    client: github_controller_client,
    identity: github_repository_identity,
    spec: github_f5_b_spec,
    observations: Mapping[str, Any],
) -> dict[str, Any]:
    del observations
    paths = (
        spec.release_authority_path,
        spec.maintenance_policy_path,
        spec.compatibility_path,
        spec.channel_metadata_path,
        spec.product_source_path,
    )
    common = _snapshot_common(client, identity)
    state = {
        **common,
        "default_branch_files": {
            path: client.read_text_file(
                identity.owner,
                identity.name,
                path,
                ref=identity.default_branch,
            )
            for path in paths
        },
        "candidate_branches": _candidate_branch_files(client, identity, paths),
        "expected_terminal_files": {
            spec.compatibility_path: spec.compatibility_expected_content,
            spec.channel_metadata_path: spec.channel_metadata_expected_content,
        },
        "fixture_aliases": {
            "release_authority_path": spec.release_authority_path,
            "maintenance_policy_path": spec.maintenance_policy_path,
            "compatibility_path": spec.compatibility_path,
            "channel_metadata_path": spec.channel_metadata_path,
            "product_source_path": spec.product_source_path,
            "release_version": _release_version(spec.release_authority_content),
            "base_branch": identity.default_branch,
        },
    }
    state["protected_digest"] = _f5_protected_digest(state)
    state["full_digest"] = _digest(state)
    return state


def _snapshot_common(
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
    pull_rows: dict[str, Any] = {}
    for item in pulls:
        number = item.get("number")
        if not isinstance(number, int):
            continue
        if str(item.get("state") or "") == "closed":
            pull_rows[str(number)] = _pull_snapshot_from_catalog(item, number)
        else:
            pull_rows[str(number)] = _pull_snapshot(client, identity, number)
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
            (
                {
                    "name": item.get("name"),
                    "color": item.get("color"),
                    "description": item.get("description"),
                }
                for item in labels
            ),
            key=lambda item: str(item["name"]),
        ),
        "issues": {
            str(int(item["number"])): _issue_snapshot(
                client,
                identity,
                int(item["number"]),
            )
            for item in issues
            if isinstance(item.get("number"), int)
        },
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


def _pull_snapshot(
    client: github_controller_client,
    identity: github_repository_identity,
    number: int,
) -> dict[str, Any]:
    item = client.pull_request(identity.owner, identity.name, number)
    head = _nested_optional_string(item, "head", "sha")
    base = _nested_optional_string(item, "base", "sha")
    changed_files: list[dict[str, Any]] = []
    if isinstance(base, str) and isinstance(head, str):
        comparison = client.compare_commits(identity.owner, identity.name, base, head)
        values = comparison.get("files") if isinstance(comparison, Mapping) else None
        if isinstance(values, list):
            changed_files = [
                {
                    "filename": value.get("filename"),
                    "status": value.get("status"),
                    "previous_filename": value.get("previous_filename"),
                }
                for value in values
                if isinstance(value, Mapping)
            ]
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
        "changed_files": sorted(
            changed_files,
            key=lambda value: str(value.get("filename")),
        ),
    }


def _issue_snapshot(
    client: github_controller_client,
    identity: github_repository_identity,
    number: int,
) -> dict[str, Any]:
    item = client.issue(identity.owner, identity.name, number)
    comments = tuple(client.issue_comments(identity.owner, identity.name, number))
    return {
        "number": number,
        "title": item.get("title"),
        "body": item.get("body"),
        "state": item.get("state"),
        "labels": sorted(_label_names(item)),
        "comments": [_comment_snapshot(comment) for comment in comments],
    }


def _candidate_branch_files(
    client: github_controller_client,
    identity: github_repository_identity,
    paths: tuple[str, ...],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for branch in client.list_branches(identity.owner, identity.name):
        name = branch.get("name")
        sha = _branch_sha(branch)
        if not isinstance(name, str) or name == identity.default_branch or not isinstance(sha, str):
            continue
        files: dict[str, Any] = {}
        for path in paths:
            value = client.contents_optional(identity.owner, identity.name, path, ref=sha)
            if value is None:
                files[path] = None
            else:
                files[path] = client.read_text_file(identity.owner, identity.name, path, ref=sha)
        result[name] = {"sha": sha, "files": files}
    return result


def _f5_protected_digest(state: Mapping[str, Any]) -> str:
    value = {
        "repository": state.get("repository"),
        "default_branch": next(
            (
                item
                for item in state.get("branches", [])
                if isinstance(item, Mapping)
                and item.get("name") == state.get("repository", {}).get("default_branch")
            ),
            None,
        ),
        "repository_labels": state.get("repository_labels"),
        "issues": state.get("issues"),
        "default_branch_files": state.get("default_branch_files"),
    }
    return _digest(value)


def _assert_f5_a_pristine(state: Mapping[str, Any], spec: github_f5_a_spec) -> None:
    if state["default_branch_files"][spec.retry_source_path] != spec.retry_source_content:
        raise github_controller_error("F5-A retry source content does not match package-owned content.")
    if state["default_branch_files"][spec.retry_tests_path] != spec.retry_tests_content:
        raise github_controller_error("F5-A acceptance test content does not match package-owned content.")
    if state.get("candidate_branches"):
        raise github_controller_error("F5-A fixture unexpectedly contains an active implementation branch.")
    _assert_closed_slice_pull_history(state, "F5-A")
    issue = state.get("retry_issue")
    if not isinstance(issue, Mapping) or issue.get("state") != "open":
        raise github_controller_error("F5-A retry issue is not pristine and open.")


def _assert_f5_b_pristine(state: Mapping[str, Any], spec: github_f5_b_spec) -> None:
    expected = {
        spec.release_authority_path: spec.release_authority_content,
        spec.maintenance_policy_path: spec.maintenance_policy_content,
        spec.compatibility_path: spec.compatibility_stale_content,
        spec.channel_metadata_path: spec.channel_metadata_stale_content,
        spec.product_source_path: spec.product_source_content,
    }
    if state.get("default_branch_files") != expected:
        raise github_controller_error("F5-B default-branch fixture content is not pristine.")
    if state.get("candidate_branches"):
        raise github_controller_error("F5-B fixture unexpectedly contains an active implementation branch.")
    _assert_closed_slice_pull_history(state, "F5-B")



def _assert_closed_slice_pull_history(state: Mapping[str, Any], label: str) -> None:
    pulls = state.get("pull_requests")
    if not isinstance(pulls, Mapping):
        raise github_controller_error(f"{label} pull-request snapshot is malformed.")
    for pull in pulls.values():
        if (
            not isinstance(pull, Mapping)
            or pull.get("state") != "closed"
            or pull.get("merged") is True
        ):
            raise github_controller_error(
                f"{label} scenario slice contains an active or merged historical pull request."
            )


def _restore_f5_slice(
    client: github_controller_client,
    identity: github_repository_identity,
    spec,
    observations: Mapping[str, Any],
    initial: Mapping[str, Any],
    *,
    snapshot,
) -> dict[str, Any]:
    del spec
    del observations
    try:
        current = snapshot()
        non_restorable: list[str] = []
        initial_pulls = initial.get("pull_requests") if isinstance(initial.get("pull_requests"), Mapping) else {}
        current_pulls = current.get("pull_requests") if isinstance(current.get("pull_requests"), Mapping) else {}

        for key, value in initial_pulls.items():
            if current_pulls.get(key) != value:
                non_restorable.append(f"historical pull request #{key} changed during the run")

        new_pull_keys = sorted(set(current_pulls) - set(initial_pulls), key=int)
        if len(new_pull_keys) > 1:
            non_restorable.append(
                f"run created {len(new_pull_keys)} pull requests; at most one run-owned PR is permitted"
            )
        for key in new_pull_keys:
            pull = current_pulls.get(key)
            if not isinstance(pull, Mapping):
                continue
            number = int(key)
            if pull.get("merged") is True:
                non_restorable.append(f"run-owned pull request #{number} was merged")
            elif pull.get("state") != "closed":
                client.update_pull_request(identity.owner, identity.name, number, {"state": "closed"})

        initial_issue_keys = set((initial.get("issues") or {}).keys())
        current_issue_keys = set((current.get("issues") or {}).keys())
        for key in sorted(current_issue_keys - initial_issue_keys, key=int):
            client.update_issue(identity.owner, identity.name, int(key), {"state": "closed"})
            non_restorable.append(f"unexpected issue #{key} remains in scenario history")

        restore_branch_refs(
            client,
            identity,
            initial,
            non_restorable,
            allowed_new_history=True,
        )
        for key, issue in (initial.get("issues") or {}).items():
            if isinstance(issue, Mapping):
                restore_issue_snapshot(client, identity, int(key), issue)
        restore_repository_labels(client, identity, initial.get("repository_labels", []))

        after = snapshot()
        baseline_ok = after.get("protected_digest") == initial.get("protected_digest")
        active_branches = after.get("candidate_branches") if isinstance(after.get("candidate_branches"), Mapping) else {}
        after_pulls = after.get("pull_requests") if isinstance(after.get("pull_requests"), Mapping) else {}
        residue_ok = True
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
        return {
            "restored": False,
            "changed": True,
            "detail": str(exc) or exc.__class__.__name__,
        }


def retry_policy_behavior(source: str) -> dict[str, bool] | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    function = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "is_retryable"
        ),
        None,
    )
    if function is None or not function.args.args:
        return None
    parameter = function.args.args[0].arg
    try:
        return {
            str(status): bool(_execute_statements(function.body, parameter, status))
            for status in (429, 500, 503, 599, 400, 404)
        }
    except (ValueError, TypeError):
        return None


def _execute_statements(statements: list[ast.stmt], parameter: str, status: int) -> bool:
    for statement in statements:
        if isinstance(statement, ast.Return):
            return bool(_eval_expr(statement.value, parameter, status))
        if isinstance(statement, ast.If):
            branch = statement.body if bool(_eval_expr(statement.test, parameter, status)) else statement.orelse
            try:
                return _execute_statements(branch, parameter, status)
            except ValueError:
                continue
    raise ValueError("No supported return path")


def _eval_expr(node: ast.AST | None, parameter: str, status: int) -> Any:
    if node is None:
        raise ValueError("missing expression")
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id == parameter:
        return status
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [_eval_expr(item, parameter, status) for item in node.elts]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not bool(_eval_expr(node.operand, parameter, status))
    if isinstance(node, ast.BoolOp):
        values = [bool(_eval_expr(item, parameter, status)) for item in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
    if isinstance(node, ast.Compare):
        left = _eval_expr(node.left, parameter, status)
        for operator, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval_expr(comparator, parameter, status)
            if isinstance(operator, ast.Eq):
                ok = left == right
            elif isinstance(operator, ast.NotEq):
                ok = left != right
            elif isinstance(operator, ast.Lt):
                ok = left < right
            elif isinstance(operator, ast.LtE):
                ok = left <= right
            elif isinstance(operator, ast.Gt):
                ok = left > right
            elif isinstance(operator, ast.GtE):
                ok = left >= right
            elif isinstance(operator, ast.In):
                ok = left in right
            elif isinstance(operator, ast.NotIn):
                ok = left not in right
            else:
                raise ValueError("unsupported comparison")
            if not ok:
                return False
            left = right
        return True
    raise ValueError("unsupported expression")


def _release_version(content: str) -> str:
    for line in content.splitlines():
        if line.strip().startswith("version:"):
            return line.split(":", 1)[1].strip()
    raise github_controller_error("F5-B release authority has no version field.")


def _comment_snapshot(item: Mapping[str, Any]) -> dict[str, Any]:
    user = item.get("user")
    return {
        "id": item.get("id"),
        "body": item.get("body"),
        "user": user.get("login") if isinstance(user, Mapping) else None,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _branch_sha(item: Mapping[str, Any]) -> str | None:
    commit = item.get("commit")
    if isinstance(commit, Mapping) and isinstance(commit.get("sha"), str):
        return commit.get("sha")
    return None


def _label_names(item: Mapping[str, Any]) -> set[str]:
    values = item.get("labels")
    if not isinstance(values, list):
        return set()
    return {
        str(value.get("name"))
        for value in values
        if isinstance(value, Mapping) and isinstance(value.get("name"), str)
    }


def _nested_optional_string(item: Mapping[str, Any], first: str, second: str) -> str | None:
    nested = item.get(first)
    if isinstance(nested, Mapping) and isinstance(nested.get(second), str):
        return nested.get(second)
    return None


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
        content=(json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
