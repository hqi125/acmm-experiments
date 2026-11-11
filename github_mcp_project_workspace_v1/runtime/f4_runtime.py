from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from acmm.experiment_api import captured_evidence, observed_environment, prepared_environment

from .controller import github_controller_client, github_controller_error, github_repository_identity
from .f4 import github_f4_a_materializer, github_f4_a_spec, github_f4_b_materializer, github_f4_b_spec


@dataclass(frozen=True)
class github_f4_a_run_handle:
    identity: github_repository_identity
    observations: dict[str, Any]
    initial_state: dict[str, Any]


@dataclass(frozen=True)
class github_f4_b_run_handle:
    identity: github_repository_identity
    observations: dict[str, Any]
    initial_state: dict[str, Any]


class github_f4_a_fixture:
    def __init__(self, client: github_controller_client, materializer: github_f4_a_materializer, spec: github_f4_a_spec) -> None:
        self._client = client
        self._materializer = materializer
        self._spec = spec

    def prepare(self, scenario, reset) -> prepared_environment:
        del reset
        if scenario.get("id") != "f4_a_failing_validation_diagnosis":
            raise ValueError("F4-A fixture received an unexpected scenario.")
        identity, observations = self._materializer.inspect()
        state = _snapshot_f4_a_state(self._client, identity, self._spec, observations)
        _assert_f4_a_pristine(state, self._spec, observations)
        return prepared_environment(
            handle=github_f4_a_run_handle(identity, dict(observations), state),
            provenance={"fixture": self._spec.fixture_id, "configuration": {"repository_name": identity.name}},
            evidence=(_json_evidence("initial_environment_state", "initial_environment_state", "evidence/initial_environment_state.json", state),),
            task_bindings={
                "repo_owner": identity.owner,
                "repo_name": identity.name,
                "diagnosis_pr_number": str(observations["diagnosis_pr_number"]),
                "ci_policy_path": self._spec.ci_policy_path,
            },
        )

    def observe(self, scenario, handle) -> observed_environment:
        del scenario
        if not isinstance(handle, github_f4_a_run_handle):
            raise TypeError("F4-A environment handle is invalid.")
        state = _snapshot_f4_a_state(self._client, handle.identity, self._spec, handle.observations)
        return observed_environment(evidence=(_json_evidence("final_environment_state", "final_environment_state", "evidence/final_environment_state.json", state),))


class github_f4_b_fixture:
    def __init__(self, client: github_controller_client, materializer: github_f4_b_materializer, spec: github_f4_b_spec) -> None:
        self._client = client
        self._materializer = materializer
        self._spec = spec

    def prepare(self, scenario, reset) -> prepared_environment:
        del reset
        if scenario.get("id") != "f4_b_superseded_failure_alert":
            raise ValueError("F4-B fixture received an unexpected scenario.")
        identity, observations = self._materializer.inspect()
        state = _snapshot_f4_b_state(self._client, identity, self._spec, observations)
        _assert_f4_b_pristine(state, self._spec, observations)
        return prepared_environment(
            handle=github_f4_b_run_handle(identity, dict(observations), state),
            provenance={"fixture": self._spec.fixture_id, "configuration": {"repository_name": identity.name}},
            evidence=(_json_evidence("initial_environment_state", "initial_environment_state", "evidence/initial_environment_state.json", state),),
            task_bindings={
                "repo_owner": identity.owner,
                "repo_name": identity.name,
                "candidate_pr_number": str(observations["candidate_pr_number"]),
                "ci_alert_issue_number": str(observations["ci_alert_issue_number"]),
                "ci_status_policy_path": self._spec.ci_status_policy_path,
            },
        )

    def observe(self, scenario, handle) -> observed_environment:
        del scenario
        if not isinstance(handle, github_f4_b_run_handle):
            raise TypeError("F4-B environment handle is invalid.")
        state = _snapshot_f4_b_state(self._client, handle.identity, self._spec, handle.observations)
        return observed_environment(evidence=(_json_evidence("final_environment_state", "final_environment_state", "evidence/final_environment_state.json", state),))


def _snapshot_f4_a_state(client: github_controller_client, identity: github_repository_identity, spec: github_f4_a_spec, observations: Mapping[str, Any]) -> dict[str, Any]:
    pr_number = int(observations["diagnosis_pr_number"])
    pr = _pull_snapshot(client, identity, pr_number)
    head = str(observations["diagnosis_head"])
    run = _workflow_run_snapshot(client, identity, int(observations["required_run"]["id"]))
    state = {
        **_snapshot_common(client, identity),
        "files": {
            spec.ci_policy_path: client.read_text_file(identity.owner, identity.name, spec.ci_policy_path, ref=head),
            spec.protocol_source_path: client.read_text_file(identity.owner, identity.name, spec.protocol_source_path, ref=head),
            spec.release_manifest_path: client.read_text_file(identity.owner, identity.name, spec.release_manifest_path, ref=head),
            spec.required_workflow.path: client.read_text_file(identity.owner, identity.name, spec.required_workflow.path, ref=head),
        },
        "diagnosis_pr": pr,
        "diagnosis_pr_comments": [_comment_snapshot(item) for item in client.issue_comments(identity.owner, identity.name, pr_number)],
        "required_run": run,
        "actions_inventory": _actions_inventory(client, identity),
        "fixture_aliases": {
            "diagnosis_pr_number": pr_number,
            "diagnosis_head": head,
            "required_workflow_id": int(observations["required_workflow_id"]),
            "required_workflow_name": str(observations["required_workflow_name"]),
            "required_run_id": int(observations["required_run"]["id"]),
            "protocol_source_path": spec.protocol_source_path,
            "release_manifest_path": spec.release_manifest_path,
            "ci_policy_path": spec.ci_policy_path,
        },
    }
    protected = dict(state)
    protected.pop("diagnosis_pr_comments", None)
    protected.pop("fixture_aliases", None)
    state["protected_digest"] = _digest(protected)
    state["full_digest"] = _digest(state)
    return state


def _snapshot_f4_b_state(client: github_controller_client, identity: github_repository_identity, spec: github_f4_b_spec, observations: Mapping[str, Any]) -> dict[str, Any]:
    pr_number = int(observations["candidate_pr_number"])
    issue_number = int(observations["ci_alert_issue_number"])
    current_head = str(observations["current_head"])
    issue = _issue_snapshot(client, identity, issue_number)
    state = {
        **_snapshot_common(client, identity),
        "files": {
            spec.ci_status_policy_path: client.read_text_file(identity.owner, identity.name, spec.ci_status_policy_path, ref=current_head),
            spec.candidate_state_path: client.read_text_file(identity.owner, identity.name, spec.candidate_state_path, ref=current_head),
            spec.required_workflow.path: client.read_text_file(identity.owner, identity.name, spec.required_workflow.path, ref=current_head),
            spec.advisory_workflow.path: client.read_text_file(identity.owner, identity.name, spec.advisory_workflow.path, ref=current_head),
        },
        "candidate_pr": _pull_snapshot(client, identity, pr_number),
        "ci_alert_issue": issue,
        "old_required_run": _workflow_run_snapshot(client, identity, int(observations["old_required_run"]["id"])),
        "current_required_run": _workflow_run_snapshot(client, identity, int(observations["current_required_run"]["id"])),
        "current_advisory_run": _workflow_run_snapshot(client, identity, int(observations["current_advisory_run"]["id"])),
        "actions_inventory": _actions_inventory(client, identity),
        "fixture_aliases": {
            "candidate_pr_number": pr_number,
            "ci_alert_issue_number": issue_number,
            "old_head": str(observations["old_head"]),
            "current_head": current_head,
            "required_workflow_id": int(observations["required_workflow_id"]),
            "required_workflow_name": str(observations["required_workflow_name"]),
            "advisory_workflow_id": int(observations["advisory_workflow_id"]),
            "advisory_workflow_name": str(observations["advisory_workflow_name"]),
            "old_required_run_id": int(observations["old_required_run"]["id"]),
            "current_required_run_id": int(observations["current_required_run"]["id"]),
            "current_advisory_run_id": int(observations["current_advisory_run"]["id"]),
            "ci_blocked_label": spec.ci_blocked_label.name,
            "ci_resolved_label": spec.ci_resolved_label.name,
            "ci_status_policy_path": spec.ci_status_policy_path,
        },
    }
    protected = dict(state)
    protected_issue = dict(issue)
    protected_issue.pop("state", None)
    protected_issue.pop("labels", None)
    protected_issue.pop("comments", None)
    protected["ci_alert_issue"] = protected_issue
    issues = dict(protected.get("issues", {}))
    issues.pop(str(issue_number), None)
    protected["issues"] = issues
    protected.pop("fixture_aliases", None)
    state["protected_digest"] = _digest(protected)
    state["full_digest"] = _digest(state)
    return state


def _assert_f4_a_pristine(state: Mapping[str, Any], spec: github_f4_a_spec, observations: Mapping[str, Any]) -> None:
    if state["files"][spec.ci_policy_path] != spec.ci_policy_content:
        raise github_controller_error("F4-A CI policy content does not match package-owned content.")
    if state["files"][spec.protocol_source_path] != spec.protocol_pr_content:
        raise github_controller_error("F4-A protocol source content does not match PR-head fixture content.")
    if state["files"][spec.release_manifest_path] != spec.release_manifest_content:
        raise github_controller_error("F4-A release manifest content does not match fixture content.")
    pr = state["diagnosis_pr"]
    if pr.get("state") != "open" or pr.get("merged") is True or pr.get("head") != observations["diagnosis_head"]:
        raise github_controller_error("F4-A diagnosis PR is not pristine.")
    if state["diagnosis_pr_comments"]:
        raise github_controller_error("F4-A diagnosis PR already contains comments.")
    run = state["required_run"]
    if run.get("head_sha") != observations["diagnosis_head"] or run.get("conclusion") != "failure":
        raise github_controller_error("F4-A required run does not match current PR-head failure.")


def _assert_f4_b_pristine(state: Mapping[str, Any], spec: github_f4_b_spec, observations: Mapping[str, Any]) -> None:
    if state["files"][spec.ci_status_policy_path] != spec.ci_status_policy_content:
        raise github_controller_error("F4-B CI status policy content does not match package-owned content.")
    if state["files"][spec.candidate_state_path] != spec.candidate_current_content:
        raise github_controller_error("F4-B current candidate content does not match package-owned content.")
    pr = state["candidate_pr"]
    if pr.get("state") != "open" or pr.get("merged") is True or pr.get("head") != observations["current_head"]:
        raise github_controller_error("F4-B candidate PR is not pristine.")
    issue = state["ci_alert_issue"]
    if issue.get("state") != "open" or spec.ci_blocked_label.name not in issue.get("labels", []) or spec.ci_resolved_label.name in issue.get("labels", []):
        raise github_controller_error("F4-B CI alert issue is not pristine.")
    if issue.get("comments"):
        raise github_controller_error("F4-B CI alert issue unexpectedly contains comments.")
    if state["old_required_run"].get("conclusion") != "failure" or state["old_required_run"].get("head_sha") != observations["old_head"]:
        raise github_controller_error("F4-B old required run is not pristine.")
    if state["current_required_run"].get("conclusion") != "success" or state["current_required_run"].get("head_sha") != observations["current_head"]:
        raise github_controller_error("F4-B current required run is not pristine.")
    if state["current_advisory_run"].get("conclusion") != "failure" or state["current_advisory_run"].get("head_sha") != observations["current_head"]:
        raise github_controller_error("F4-B advisory run is not pristine.")


def _snapshot_common(client: github_controller_client, identity: github_repository_identity) -> dict[str, Any]:
    branches = tuple(client.list_branches(identity.owner, identity.name))
    issues = tuple(item for item in client.list_issues(identity.owner, identity.name) if "pull_request" not in item)
    pulls = tuple(client.list_pull_requests(identity.owner, identity.name))
    labels = tuple(client.list_labels(identity.owner, identity.name))
    return {
        "authoritative_source": "github_rest_api",
        "repository": {"id": identity.repository_id, "full_name": identity.full_name, "default_branch": identity.default_branch},
        "branches": sorted(({"name": str(item.get("name")), "sha": _branch_sha(item), "protected": bool(item.get("protected", False))} for item in branches), key=lambda item: item["name"]),
        "repository_labels": sorted(({"name": item.get("name"), "color": item.get("color"), "description": item.get("description")} for item in labels), key=lambda item: str(item["name"])),
        "issues": {str(int(item["number"])): _issue_snapshot(client, identity, int(item["number"])) for item in issues if isinstance(item.get("number"), int)},
        "pull_requests": {str(int(item["number"])): _pull_snapshot(client, identity, int(item["number"])) for item in pulls if isinstance(item.get("number"), int)},
    }


def _issue_snapshot(client: github_controller_client, identity: github_repository_identity, number: int) -> dict[str, Any]:
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


def _pull_snapshot(client: github_controller_client, identity: github_repository_identity, number: int) -> dict[str, Any]:
    item = client.pull_request(identity.owner, identity.name, number)
    return {
        "number": number,
        "title": item.get("title"),
        "body": item.get("body"),
        "state": item.get("state"),
        "draft": bool(item.get("draft", False)),
        "merged": item.get("merged") is True,
        "head": _nested_optional_string(item, "head", "sha"),
        "base": _nested_optional_string(item, "base", "sha"),
        "labels": sorted(_label_names(item)),
    }


def _workflow_run_snapshot(client: github_controller_client, identity: github_repository_identity, run_id: int) -> dict[str, Any]:
    run = client.workflow_run(identity.owner, identity.name, run_id)
    jobs_value = client.workflow_run_jobs(identity.owner, identity.name, run_id)
    jobs = jobs_value.get("jobs") if isinstance(jobs_value, Mapping) else None
    job_rows: list[dict[str, Any]] = []
    if isinstance(jobs, list):
        for item in jobs:
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), int):
                continue
            job_id = int(item["id"])
            logs = client.workflow_job_logs(identity.owner, identity.name, job_id)
            job_rows.append({"id": job_id, "name": item.get("name"), "status": item.get("status"), "conclusion": item.get("conclusion"), "logs": logs})
    return {
        "id": run_id,
        "name": run.get("name"),
        "workflow_id": run.get("workflow_id"),
        "head_branch": run.get("head_branch"),
        "head_sha": run.get("head_sha"),
        "event": run.get("event"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "jobs": job_rows,
    }


def _actions_inventory(client: github_controller_client, identity: github_repository_identity) -> list[dict[str, Any]]:
    value = client.list_workflow_runs(identity.owner, identity.name, per_page=100)
    rows = value.get("workflow_runs") if isinstance(value, Mapping) else None
    if not isinstance(rows, list):
        raise github_controller_error("Actions run inventory is malformed.")
    result = []
    for item in rows:
        if not isinstance(item, Mapping) or not isinstance(item.get("id"), int):
            continue
        result.append({
            "id": int(item["id"]),
            "workflow_id": item.get("workflow_id"),
            "name": item.get("name"),
            "head_branch": item.get("head_branch"),
            "head_sha": item.get("head_sha"),
            "event": item.get("event"),
            "status": item.get("status"),
            "conclusion": item.get("conclusion"),
        })
    return sorted(result, key=lambda item: item["id"])


def _comment_snapshot(item: Mapping[str, Any]) -> dict[str, Any]:
    user = item.get("user")
    return {"id": item.get("id"), "body": item.get("body"), "user": user.get("login") if isinstance(user, Mapping) else None, "created_at": item.get("created_at"), "updated_at": item.get("updated_at")}


def _branch_sha(item: Mapping[str, Any]) -> str | None:
    commit = item.get("commit")
    return commit.get("sha") if isinstance(commit, Mapping) and isinstance(commit.get("sha"), str) else None


def _label_names(item: Mapping[str, Any]) -> set[str]:
    values = item.get("labels")
    if not isinstance(values, list):
        return set()
    return {str(value.get("name")) for value in values if isinstance(value, Mapping) and isinstance(value.get("name"), str)}


def _nested_optional_string(item: Mapping[str, Any], first: str, second: str) -> str | None:
    nested = item.get(first)
    return nested.get(second) if isinstance(nested, Mapping) and isinstance(nested.get(second), str) else None


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_evidence(evidence_id: str, channel: str, artifact: str, value: Any) -> captured_evidence:
    return captured_evidence(
        id=evidence_id,
        channel=channel,
        artifact=artifact,
        content=(json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
