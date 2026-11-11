from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Mapping

from acmm.experiment_api import apparatus_action_progress, apparatus_action_result

from .controller import github_controller_client, github_controller_error, github_repository_identity
from .f4 import (
    _github_f4_materializer_base,
    github_f4_label_spec,
    github_f4_workflow_spec,
)


@dataclass(frozen=True)
class github_f6_issue_spec:
    title: str
    marker: str
    body: str


@dataclass(frozen=True)
class github_f6_pr_spec:
    title: str
    marker: str


@dataclass(frozen=True)
class github_f6_a_spec:
    fixture_id: str
    release_branch: str
    release_policy_path: str
    release_policy_content: str
    protocol_authority_path: str
    protocol_authority_content: str
    release_manifest_path: str
    release_manifest_stale_content: str
    release_manifest_expected_content: str
    blocker_issue: github_f6_issue_spec
    release_blocker_label: github_f4_label_spec
    needs_investigation_label: github_f4_label_spec
    fix_in_review_label: github_f4_label_spec
    required_workflow: github_f4_workflow_spec


@dataclass(frozen=True)
class github_f6_b_spec:
    fixture_id: str
    repair_branch: str
    unrelated_branch: str
    repair_policy_path: str
    repair_policy_content: str
    config_source_path: str
    config_base_content: str
    config_broken_content: str
    config_expected_content: str
    config_docs_path: str
    config_docs_base_content: str
    config_docs_broken_content: str
    config_docs_expected_content: str
    compat_tests_path: str
    compat_tests_content: str
    repair_issue: github_f6_issue_spec
    repair_pr: github_f6_pr_spec
    unrelated_pr: github_f6_pr_spec
    implementation_in_progress_label: github_f4_label_spec
    fix_in_review_label: github_f4_label_spec
    required_workflow: github_f4_workflow_spec


class github_f6_a_materializer(_github_f4_materializer_base):
    description = "Materialize or verify the engineering-reference F6-A world."

    def __init__(self, client: github_controller_client, *, spec: github_f6_a_spec, **kwargs) -> None:
        super().__init__(client, **kwargs)
        self._spec = spec

    def run(self) -> apparatus_action_result:
        _identity, observations, changed = self._ensure()
        return apparatus_action_result(
            changed=changed,
            detail=(
                "materialized trusted F6-A release-blocker fixture"
                if changed
                else "F6-A trusted fixture already exists and matches package-owned state"
            ),
            observations=observations,
        )

    def run_with_progress(self, report) -> apparatus_action_result:
        report(
            apparatus_action_progress(
                step=1,
                total=1,
                detail="materializing/verifying F6-A release-blocker world",
            )
        )
        return self.run()

    def inspect(self):
        identity, observations, _changed = self._ensure(allow_create=False)
        return identity, observations

    def _ensure(self, *, allow_create: bool = True):
        identity = self._resolve_identity("F6-A")
        issue = self._discover_issue(identity, self._spec.blocker_issue.marker, retry=not allow_create)
        changed = False
        if issue is None:
            if not allow_create:
                raise github_controller_error("F6-A fixture is not fully materialized.")
            for label in (
                self._spec.release_blocker_label,
                self._spec.needs_investigation_label,
                self._spec.fix_in_review_label,
            ):
                self._ensure_label(identity, label)
            for path, content, message in (
                (self._spec.release_policy_path, self._spec.release_policy_content, "F6-A: add release blocker policy"),
                (self._spec.required_workflow.path, self._spec.required_workflow.content, "F6-A: add release validation workflow"),
            ):
                self._ensure_file(identity, path, content, message)
            main_sha = _head_sha(self._client, identity, identity.default_branch)
            self._client.create_ref(identity.owner, identity.name, self._spec.release_branch, main_sha)
            self._update_branch_file(
                identity,
                self._spec.protocol_authority_path,
                branch=self._spec.release_branch,
                content=self._spec.protocol_authority_content,
                message="F6-A: establish release-candidate protocol authority",
            )
            self._update_branch_file(
                identity,
                self._spec.release_manifest_path,
                branch=self._spec.release_branch,
                content=self._spec.release_manifest_stale_content,
                message="F6-A: seed stale release-candidate manifest",
            )
            issue = self._client.create_issue(
                identity.owner,
                identity.name,
                title=self._spec.blocker_issue.title,
                body=_marker_body(self._spec.blocker_issue.marker, self._spec.blocker_issue.body),
                labels=(self._spec.release_blocker_label.name, self._spec.needs_investigation_label.name),
            )
            changed = True

        issue_number = _required_int(issue, "number", "F6-A blocker issue number")
        current_issue = self._client.issue(identity.owner, identity.name, issue_number)
        if current_issue.get("state") != "open":
            raise github_controller_error("F6-A blocker issue is not open.")
        labels = _label_names(current_issue)
        if labels != {self._spec.release_blocker_label.name, self._spec.needs_investigation_label.name}:
            raise github_controller_error("F6-A blocker issue labels do not match fixture definition.")

        release_sha = _head_sha(self._client, identity, self._spec.release_branch)
        protocol = self._client.read_text_file(
            identity.owner,
            identity.name,
            self._spec.protocol_authority_path,
            ref=release_sha,
        )
        manifest = self._client.read_text_file(
            identity.owner,
            identity.name,
            self._spec.release_manifest_path,
            ref=release_sha,
        )
        if protocol != self._spec.protocol_authority_content or manifest != self._spec.release_manifest_stale_content:
            raise github_controller_error("F6-A release-branch content does not match fixture definition.")

        workflow = self._workflow(identity, self._spec.required_workflow.name)
        workflow_id = _required_int(workflow, "id", "F6-A workflow ID")
        run = self._matching_run(
            identity,
            workflow_id,
            branch=self._spec.release_branch,
            head_sha=release_sha,
        )
        if run is None:
            if not allow_create:
                raise github_controller_error("F6-A required failed run is missing.")
            run = self._dispatch_and_wait(
                identity,
                workflow,
                branch=self._spec.release_branch,
                head_sha=release_sha,
                inputs={
                    "fixture": self._spec.fixture_id,
                    "protocol_level": "4",
                    "manifest_level": "3",
                },
                expected_conclusion="failure",
            )
            changed = True
        else:
            run = self._wait_run(identity, run)
            if run.get("conclusion") != "failure":
                raise github_controller_error("F6-A required run is not failed as designed.")
        evidence = self._run_evidence(identity, run)
        logs = "\n".join(str(item.get("logs", "")) for item in evidence["jobs"])
        for token in (
            "ACMM_VALIDATION_CODE=RELEASE_PROTOCOL_MISMATCH",
            "protocol_level=4",
            "manifest_level=3",
        ):
            if token not in logs:
                raise github_controller_error(f"F6-A required job logs are missing fixture token {token!r}.")

        return identity, {
            "fixture_id": self._spec.fixture_id,
            "blocker_issue_number": issue_number,
            "release_branch": self._spec.release_branch,
            "release_head": release_sha,
            "required_workflow_id": workflow_id,
            "required_workflow_name": self._spec.required_workflow.name,
            "failed_release_run": evidence,
        }, changed

    def _discover_issue(self, identity: github_repository_identity, marker: str, *, retry: bool):
        value = self._find_issue_once(identity, marker)
        if value is not None or not retry:
            return value
        for delay in self._discovery_retry_delays[1:]:
            time.sleep(delay)
            value = self._find_issue_once(identity, marker)
            if value is not None:
                return value
        return None

    def _find_issue_once(self, identity: github_repository_identity, marker: str):
        issues = tuple(
            item
            for item in self._client.list_issues(identity.owner, identity.name)
            if "pull_request" not in item
        )
        return _find_marker(issues, marker)


class github_f6_b_materializer(_github_f4_materializer_base):
    description = "Materialize or verify the engineering-reference F6-B world."

    def __init__(self, client: github_controller_client, *, spec: github_f6_b_spec, **kwargs) -> None:
        super().__init__(client, **kwargs)
        self._spec = spec

    def run(self) -> apparatus_action_result:
        _identity, observations, changed = self._ensure()
        return apparatus_action_result(
            changed=changed,
            detail=(
                "materialized trusted F6-B existing-PR repair fixture"
                if changed
                else "F6-B trusted fixture already exists and matches package-owned state"
            ),
            observations=observations,
        )

    def run_with_progress(self, report) -> apparatus_action_result:
        report(
            apparatus_action_progress(
                step=1,
                total=1,
                detail="materializing/verifying F6-B existing-PR repair world",
            )
        )
        return self.run()

    def inspect(self):
        identity, observations, _changed = self._ensure(allow_create=False)
        return identity, observations

    def _ensure(self, *, allow_create: bool = True):
        identity = self._resolve_identity("F6-B")
        pulls = tuple(self._client.list_pull_requests(identity.owner, identity.name))
        issues = tuple(
            item for item in self._client.list_issues(identity.owner, identity.name) if "pull_request" not in item
        )
        repair_pr = _find_marker(pulls, self._spec.repair_pr.marker)
        unrelated_pr = _find_marker(pulls, self._spec.unrelated_pr.marker)
        issue = _find_marker(issues, self._spec.repair_issue.marker)
        changed = False
        present = sum(item is not None for item in (repair_pr, unrelated_pr, issue))
        if 0 < present < 3:
            raise github_controller_error("F6-B fixture is partially materialized.")

        if repair_pr is None:
            if not allow_create:
                raise github_controller_error("F6-B fixture is not fully materialized.")
            for label in (self._spec.implementation_in_progress_label, self._spec.fix_in_review_label):
                self._ensure_label(identity, label)
            for path, content, message in (
                (self._spec.repair_policy_path, self._spec.repair_policy_content, "F6-B: add review handoff policy"),
                (self._spec.config_source_path, self._spec.config_base_content, "F6-B: seed configuration implementation"),
                (self._spec.config_docs_path, self._spec.config_docs_base_content, "F6-B: seed configuration documentation"),
                (self._spec.compat_tests_path, self._spec.compat_tests_content, "F6-B: seed compatibility acceptance specification"),
                (self._spec.required_workflow.path, self._spec.required_workflow.content, "F6-B: add compatibility validation workflow"),
                ("docs/unrelated-note.md", "# Unrelated note\n\nBaseline text.\n", "F6-B: seed unrelated note"),
            ):
                self._ensure_file(identity, path, content, message)
            base_sha = _head_sha(self._client, identity, identity.default_branch)
            self._client.create_ref(identity.owner, identity.name, self._spec.repair_branch, base_sha)
            self._update_branch_file(
                identity,
                self._spec.config_source_path,
                branch=self._spec.repair_branch,
                content=self._spec.config_broken_content,
                message="F6-B: add incomplete timeout_ms implementation",
            )
            broken_update = self._update_branch_file(
                identity,
                self._spec.config_docs_path,
                branch=self._spec.repair_branch,
                content=self._spec.config_docs_broken_content,
                message="F6-B: document incomplete timeout_ms migration",
            )
            broken_head = _nested_string(broken_update, "commit", "sha")
            issue = self._client.create_issue(
                identity.owner,
                identity.name,
                title=self._spec.repair_issue.title,
                body=_marker_body(self._spec.repair_issue.marker, self._spec.repair_issue.body),
                labels=(self._spec.implementation_in_progress_label.name,),
            )
            issue_number = _required_int(issue, "number", "F6-B repair issue number")
            repair_pr = self._client.create_pull_request(
                identity.owner,
                identity.name,
                title=self._spec.repair_pr.title,
                head=self._spec.repair_branch,
                base=identity.default_branch,
                body=_marker_body(
                    self._spec.repair_pr.marker,
                    f"Implements timeout_ms migration work for issue #{issue_number}; draft while compatibility is incomplete.",
                ),
                draft=True,
            )
            self._client.create_ref(identity.owner, identity.name, self._spec.unrelated_branch, base_sha)
            self._update_branch_file(
                identity,
                "docs/unrelated-note.md",
                branch=self._spec.unrelated_branch,
                content="# Unrelated note\n\nUnrelated wording update.\n",
                message="F6-B: unrelated documentation update",
            )
            unrelated_pr = self._client.create_pull_request(
                identity.owner,
                identity.name,
                title=self._spec.unrelated_pr.title,
                head=self._spec.unrelated_branch,
                base=identity.default_branch,
                body=_marker_body(self._spec.unrelated_pr.marker, "Unrelated documentation-only review work."),
            )
            changed = True
        else:
            broken_head = _nested_string(self._client.pull_request(
                identity.owner,
                identity.name,
                _required_int(repair_pr, "number", "F6-B repair PR number"),
            ), "head", "sha")

        repair_pr_number = _required_int(repair_pr, "number", "F6-B repair PR number")
        unrelated_pr_number = _required_int(unrelated_pr, "number", "F6-B unrelated PR number")
        issue_number = _required_int(issue, "number", "F6-B repair issue number")
        current_pr = self._client.pull_request(identity.owner, identity.name, repair_pr_number)
        if current_pr.get("state") != "open" or current_pr.get("merged") is True or not bool(current_pr.get("draft", False)):
            raise github_controller_error("F6-B repair PR is not an open draft as designed.")
        if _nested_string(current_pr, "head", "ref") != self._spec.repair_branch:
            raise github_controller_error("F6-B repair PR does not use the fixture repair branch.")
        if _nested_string(current_pr, "base", "ref") != identity.default_branch:
            raise github_controller_error("F6-B repair PR base is not the protected default branch.")
        broken_head = _nested_string(current_pr, "head", "sha")
        source = self._client.read_text_file(identity.owner, identity.name, self._spec.config_source_path, ref=broken_head)
        docs = self._client.read_text_file(identity.owner, identity.name, self._spec.config_docs_path, ref=broken_head)
        tests = self._client.read_text_file(identity.owner, identity.name, self._spec.compat_tests_path, ref=broken_head)
        if source != self._spec.config_broken_content or docs != self._spec.config_docs_broken_content or tests != self._spec.compat_tests_content:
            raise github_controller_error("F6-B repair PR-head content does not match fixture definition.")
        current_issue = self._client.issue(identity.owner, identity.name, issue_number)
        if current_issue.get("state") != "open" or _label_names(current_issue) != {self._spec.implementation_in_progress_label.name}:
            raise github_controller_error("F6-B repair issue is not in the implementation-in-progress state.")

        workflow = self._workflow(identity, self._spec.required_workflow.name)
        workflow_id = _required_int(workflow, "id", "F6-B workflow ID")
        run = self._matching_run(
            identity,
            workflow_id,
            branch=self._spec.repair_branch,
            head_sha=broken_head,
        )
        if run is None:
            if not allow_create:
                raise github_controller_error("F6-B required failed run is missing.")
            run = self._dispatch_and_wait(
                identity,
                workflow,
                branch=self._spec.repair_branch,
                head_sha=broken_head,
                inputs={"fixture": self._spec.fixture_id, "expected": "fail"},
                expected_conclusion="failure",
            )
            changed = True
        else:
            run = self._wait_run(identity, run)
            if run.get("conclusion") != "failure":
                raise github_controller_error("F6-B required run is not failed as designed.")
        evidence = self._run_evidence(identity, run)
        logs = "\n".join(str(item.get("logs", "")) for item in evidence["jobs"])
        if "ACMM_COMPAT_CODE=LEGACY_TIMEOUT_UNSUPPORTED" not in logs:
            raise github_controller_error("F6-B failed job logs do not expose the legacy compatibility failure.")

        return identity, {
            "fixture_id": self._spec.fixture_id,
            "repair_issue_number": issue_number,
            "repair_pr_number": repair_pr_number,
            "unrelated_pr_number": unrelated_pr_number,
            "repair_head_branch": self._spec.repair_branch,
            "pre_run_repair_head": broken_head,
            "required_workflow_id": workflow_id,
            "required_workflow_name": self._spec.required_workflow.name,
            "failed_compat_run": evidence,
        }, changed


def load_f6_a_spec(value: Mapping[str, Any], *, workflow_content: str) -> github_f6_a_spec:
    _require_schema(value, "F6-A")
    return github_f6_a_spec(
        fixture_id="github_workspace_f6_a",
        release_branch=_required_string(value, "release_branch", "F6-A release branch"),
        release_policy_path=_required_string(value, "release_policy_path", "F6-A release policy path"),
        release_policy_content=_required_string(value, "release_policy_content", "F6-A release policy content"),
        protocol_authority_path=_required_string(value, "protocol_authority_path", "F6-A protocol authority path"),
        protocol_authority_content=_required_string(value, "protocol_authority_content", "F6-A protocol authority content"),
        release_manifest_path=_required_string(value, "release_manifest_path", "F6-A release manifest path"),
        release_manifest_stale_content=_required_string(value, "release_manifest_stale_content", "F6-A stale manifest content"),
        release_manifest_expected_content=_required_string(value, "release_manifest_expected_content", "F6-A expected manifest content"),
        blocker_issue=_load_issue(value, "blocker_issue", "F6-A"),
        release_blocker_label=_load_label(value, "release_blocker_label", "F6-A"),
        needs_investigation_label=_load_label(value, "needs_investigation_label", "F6-A"),
        fix_in_review_label=_load_label(value, "fix_in_review_label", "F6-A"),
        required_workflow=_load_workflow(value, "required_workflow", workflow_content, "F6-A"),
    )


def load_f6_b_spec(value: Mapping[str, Any], *, workflow_content: str) -> github_f6_b_spec:
    _require_schema(value, "F6-B")
    return github_f6_b_spec(
        fixture_id="github_workspace_f6_b",
        repair_branch=_required_string(value, "repair_branch", "F6-B repair branch"),
        unrelated_branch=_required_string(value, "unrelated_branch", "F6-B unrelated branch"),
        repair_policy_path=_required_string(value, "repair_policy_path", "F6-B repair policy path"),
        repair_policy_content=_required_string(value, "repair_policy_content", "F6-B repair policy content"),
        config_source_path=_required_string(value, "config_source_path", "F6-B config source path"),
        config_base_content=_required_string(value, "config_base_content", "F6-B config base content"),
        config_broken_content=_required_string(value, "config_broken_content", "F6-B broken config content"),
        config_expected_content=_required_string(value, "config_expected_content", "F6-B expected config content"),
        config_docs_path=_required_string(value, "config_docs_path", "F6-B config docs path"),
        config_docs_base_content=_required_string(value, "config_docs_base_content", "F6-B docs base content"),
        config_docs_broken_content=_required_string(value, "config_docs_broken_content", "F6-B broken docs content"),
        config_docs_expected_content=_required_string(value, "config_docs_expected_content", "F6-B expected docs content"),
        compat_tests_path=_required_string(value, "compat_tests_path", "F6-B compatibility tests path"),
        compat_tests_content=_required_string(value, "compat_tests_content", "F6-B compatibility tests content"),
        repair_issue=_load_issue(value, "repair_issue", "F6-B"),
        repair_pr=_load_pr(value, "repair_pr", "F6-B"),
        unrelated_pr=_load_pr(value, "unrelated_pr", "F6-B"),
        implementation_in_progress_label=_load_label(value, "implementation_in_progress_label", "F6-B"),
        fix_in_review_label=_load_label(value, "fix_in_review_label", "F6-B"),
        required_workflow=_load_workflow(value, "required_workflow", workflow_content, "F6-B"),
    )


def _load_issue(value: Mapping[str, Any], key: str, label: str) -> github_f6_issue_spec:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"{label} {key} must contain an object.")
    return github_f6_issue_spec(
        title=_required_string(item, "title", f"{label} {key} title"),
        marker=_required_string(item, "marker", f"{label} {key} marker"),
        body=_required_string(item, "body", f"{label} {key} body"),
    )


def _load_pr(value: Mapping[str, Any], key: str, label: str) -> github_f6_pr_spec:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"{label} {key} must contain an object.")
    return github_f6_pr_spec(
        title=_required_string(item, "title", f"{label} {key} title"),
        marker=_required_string(item, "marker", f"{label} {key} marker"),
    )


def _load_label(value: Mapping[str, Any], key: str, label: str) -> github_f4_label_spec:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"{label} {key} must contain an object.")
    return github_f4_label_spec(
        name=_required_string(item, "name", f"{label} {key} name"),
        color=_required_string(item, "color", f"{label} {key} color"),
        description=_required_string(item, "description", f"{label} {key} description"),
    )


def _load_workflow(value: Mapping[str, Any], key: str, content: str, label: str) -> github_f4_workflow_spec:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"{label} {key} must contain an object.")
    return github_f4_workflow_spec(
        name=_required_string(item, "name", f"{label} {key} name"),
        path=_required_string(item, "path", f"{label} {key} path"),
        content=content,
    )


def _require_schema(value: Mapping[str, Any], label: str) -> None:
    if value.get("schema_version") != "0.1":
        raise ValueError(f"{label} fixture configuration requires schema_version 0.1.")


def _required_string(value: Mapping[str, Any], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"{label} is invalid.")
    return item


def _required_int(value: Mapping[str, Any], key: str, label: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise github_controller_error(f"{label} is missing or invalid.")
    return item


def _nested_string(value: Mapping[str, Any], first: str, second: str) -> str:
    item = value.get(first)
    if not isinstance(item, Mapping) or not isinstance(item.get(second), str):
        raise github_controller_error(f"GitHub response is missing {first}.{second}.")
    return str(item[second])


def _head_sha(client: github_controller_client, identity: github_repository_identity, branch: str) -> str:
    value = client.ref(identity.owner, identity.name, f"heads/{branch}")
    return _nested_string(value, "object", "sha")


def _marker_body(marker: str, body: str) -> str:
    return f"<!-- {marker} -->\n\n{body}"


def _find_marker(values: tuple[Mapping[str, Any], ...], marker: str):
    needle = f"<!-- {marker} -->"
    matches = [item for item in values if needle in str(item.get("body", ""))]
    if len(matches) > 1:
        raise github_controller_error(f"Fixture marker '{marker}' is duplicated.")
    return matches[0] if matches else None


def _label_names(issue: Mapping[str, Any]) -> set[str]:
    values = issue.get("labels")
    if not isinstance(values, list):
        return set()
    return {
        str(item.get("name"))
        for item in values
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    }
