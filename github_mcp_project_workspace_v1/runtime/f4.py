from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable, Mapping

from acmm.experiment_api import apparatus_action_progress, apparatus_action_result

from .controller import (
    github_api_error,
    github_controller_client,
    github_controller_error,
    github_fixture_base_file,
    github_repository_identity,
)


@dataclass(frozen=True)
class github_f4_label_spec:
    name: str
    color: str
    description: str


@dataclass(frozen=True)
class github_f4_issue_spec:
    title: str
    marker: str
    body: str


@dataclass(frozen=True)
class github_f4_pr_spec:
    title: str
    marker: str
    branch: str


@dataclass(frozen=True)
class github_f4_workflow_spec:
    name: str
    path: str
    content: str


@dataclass(frozen=True)
class github_f4_a_spec:
    fixture_id: str
    ci_policy_path: str
    ci_policy_content: str
    protocol_source_path: str
    protocol_initial_content: str
    protocol_pr_content: str
    release_manifest_path: str
    release_manifest_content: str
    diagnosis_pr: github_f4_pr_spec
    required_workflow: github_f4_workflow_spec


@dataclass(frozen=True)
class github_f4_b_spec:
    fixture_id: str
    ci_status_policy_path: str
    ci_status_policy_content: str
    candidate_state_path: str
    candidate_base_content: str
    candidate_old_content: str
    candidate_current_content: str
    candidate_pr: github_f4_pr_spec
    alert_issue: github_f4_issue_spec
    ci_blocked_label: github_f4_label_spec
    ci_resolved_label: github_f4_label_spec
    required_workflow: github_f4_workflow_spec
    advisory_workflow: github_f4_workflow_spec


class _github_f4_materializer_base:
    mutates_external_state = True

    def __init__(
        self,
        client: github_controller_client,
        *,
        repository_name: str,
        expected_repository_full_name: str,
        expected_repository_id: int,
        expected_default_branch: str,
        fixture_base_files: tuple[github_fixture_base_file, ...],
    ) -> None:
        self._client = client
        self._repository_name = repository_name
        self._expected_repository_full_name = expected_repository_full_name
        self._expected_repository_id = expected_repository_id
        self._expected_default_branch = expected_default_branch
        self._fixture_base_files = tuple(fixture_base_files)
        self._discovery_retry_delays = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)
        self._workflow_retry_delays = (0.0, 1.0, 2.0, 4.0, 8.0, 15.0, 20.0, 30.0, 30.0)

    def _resolve_identity(self, label: str) -> github_repository_identity:
        identity = self._client.resolve_repository(self._repository_name)
        if (
            identity.full_name != self._expected_repository_full_name
            or identity.repository_id != self._expected_repository_id
        ):
            raise github_controller_error(
                f"{label} fixture target does not match the pinned repository."
            )
        if identity.default_branch != self._expected_default_branch:
            raise github_controller_error(
                f"{label} fixture requires default branch '{self._expected_default_branch}', "
                f"got '{identity.default_branch}'."
            )
        self._client.ref(identity.owner, identity.name, f"heads/{identity.default_branch}")
        for item in self._fixture_base_files:
            actual = self._client.read_text_file(
                identity.owner,
                identity.name,
                item.path,
                ref=identity.default_branch,
            )
            if actual != item.content:
                raise github_controller_error(
                    f"Trusted fixture base file '{item.path}' does not match package-owned seed content."
                )
        return identity

    def _ensure_file(
        self,
        identity: github_repository_identity,
        path: str,
        content: str,
        message: str,
    ) -> Mapping[str, Any] | None:
        existing = self._client.contents_optional(
            identity.owner,
            identity.name,
            path,
            ref=identity.default_branch,
        )
        if isinstance(existing, Mapping):
            actual = self._client.read_text_file(
                identity.owner,
                identity.name,
                path,
                ref=identity.default_branch,
            )
            if actual == content:
                return None
            sha = existing.get("sha")
            if not isinstance(sha, str):
                raise github_controller_error(
                    f"Existing fixture file '{path}' has no blob SHA."
                )
            return self._client.create_or_update_file(
                identity.owner,
                identity.name,
                path,
                message=message,
                content=content,
                branch=identity.default_branch,
                sha=sha,
            )
        return self._client.create_or_update_file(
            identity.owner,
            identity.name,
            path,
            message=message,
            content=content,
            branch=identity.default_branch,
        )

    def _update_branch_file(
        self,
        identity: github_repository_identity,
        path: str,
        *,
        branch: str,
        content: str,
        message: str,
    ) -> Mapping[str, Any]:
        existing = self._client.contents_optional(
            identity.owner,
            identity.name,
            path,
            ref=branch,
        )
        sha = existing.get("sha") if isinstance(existing, Mapping) else None
        if existing is not None and not isinstance(sha, str):
            raise github_controller_error(
                f"Existing branch file '{path}' has no blob SHA."
            )
        return self._client.create_or_update_file(
            identity.owner,
            identity.name,
            path,
            message=message,
            content=content,
            branch=branch,
            sha=sha if isinstance(sha, str) else None,
        )

    def _ensure_label(
        self,
        identity: github_repository_identity,
        spec: github_f4_label_spec,
    ) -> None:
        labels = tuple(self._client.list_labels(identity.owner, identity.name))
        match = next((item for item in labels if item.get("name") == spec.name), None)
        if match is None:
            value = self._client.create_label(
                identity.owner,
                identity.name,
                label=spec.name,
                color=spec.color,
                description=spec.description,
            )
        elif (
            str(match.get("color", "")).lower() == spec.color.lower()
            and match.get("description") == spec.description
        ):
            return
        else:
            value = self._client.update_label(
                identity.owner,
                identity.name,
                spec.name,
                new_name=spec.name,
                color=spec.color,
                description=spec.description,
            )
        if (
            value.get("name") != spec.name
            or str(value.get("color", "")).lower() != spec.color.lower()
            or value.get("description") != spec.description
        ):
            raise github_controller_error(
                f"Label '{spec.name}' could not be converged to the F4 fixture definition."
            )

    def _workflow(self, identity: github_repository_identity, name: str) -> Mapping[str, Any]:
        latest: Mapping[str, Any] | None = None
        for delay in self._discovery_retry_delays:
            if delay > 0:
                time.sleep(delay)
            value = self._client.list_workflows(identity.owner, identity.name)
            rows = value.get("workflows")
            if not isinstance(rows, list):
                raise github_controller_error("GitHub workflows response is malformed.")
            matches = [item for item in rows if isinstance(item, Mapping) and item.get("name") == name]
            if len(matches) == 1:
                latest = matches[0]
                break
            if len(matches) > 1:
                raise github_controller_error(f"Workflow '{name}' is duplicated.")
        if latest is None:
            raise github_controller_error(f"Workflow '{name}' did not become discoverable.")
        return latest

    def _matching_run(
        self,
        identity: github_repository_identity,
        workflow_id: int,
        *,
        branch: str,
        head_sha: str,
    ) -> Mapping[str, Any] | None:
        value = self._client.list_workflow_runs_for_workflow(
            identity.owner,
            identity.name,
            workflow_id,
            branch=branch,
            event="workflow_dispatch",
            per_page=100,
        )
        rows = value.get("workflow_runs")
        if not isinstance(rows, list):
            raise github_controller_error("GitHub workflow-runs response is malformed.")
        matches = [
            item
            for item in rows
            if isinstance(item, Mapping)
            and item.get("head_sha") == head_sha
            and item.get("head_branch") == branch
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return dict(matches[0])

    def _wait_run(
        self,
        identity: github_repository_identity,
        run: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        run_id = run.get("id")
        if not isinstance(run_id, int):
            raise github_controller_error("Workflow run does not expose a numeric ID.")
        current = dict(run)
        for delay in self._workflow_retry_delays:
            if current.get("status") == "completed":
                return current
            if delay > 0:
                time.sleep(delay)
            current = dict(self._client.workflow_run(identity.owner, identity.name, run_id))
        raise github_controller_error(f"Workflow run {run_id} did not complete in time.")

    def _dispatch_and_wait(
        self,
        identity: github_repository_identity,
        workflow: Mapping[str, Any],
        *,
        branch: str,
        head_sha: str,
        inputs: Mapping[str, str],
        expected_conclusion: str,
    ) -> Mapping[str, Any]:
        workflow_id = workflow.get("id")
        if not isinstance(workflow_id, int):
            raise github_controller_error("Workflow does not expose a numeric ID.")
        existing = self._matching_run(
            identity,
            workflow_id,
            branch=branch,
            head_sha=head_sha,
        )
        if existing is None:
            self._client.dispatch_workflow(
                identity.owner,
                identity.name,
                workflow_id,
                ref=branch,
                inputs=inputs,
            )
            for delay in self._workflow_retry_delays[1:]:
                if delay > 0:
                    time.sleep(delay)
                existing = self._matching_run(
                    identity,
                    workflow_id,
                    branch=branch,
                    head_sha=head_sha,
                )
                if existing is not None:
                    break
        if existing is None:
            raise github_controller_error(
                f"Dispatched workflow '{workflow.get('name')}' did not become visible."
            )
        completed = self._wait_run(identity, existing)
        if completed.get("conclusion") != expected_conclusion:
            raise github_controller_error(
                f"Workflow '{workflow.get('name')}' completed with conclusion "
                f"{completed.get('conclusion')!r}; expected {expected_conclusion!r}."
            )
        if completed.get("head_sha") != head_sha:
            raise github_controller_error("Workflow run does not belong to the expected head SHA.")
        return completed

    def _run_evidence(
        self,
        identity: github_repository_identity,
        run: Mapping[str, Any],
    ) -> dict[str, Any]:
        run_id = run.get("id")
        if not isinstance(run_id, int):
            raise github_controller_error("Workflow run does not expose a numeric ID.")
        jobs_value = self._client.workflow_run_jobs(identity.owner, identity.name, run_id)
        jobs = jobs_value.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise github_controller_error(f"Workflow run {run_id} exposes no jobs.")
        snapshots: list[dict[str, Any]] = []
        for item in jobs:
            if not isinstance(item, Mapping):
                continue
            job_id = item.get("id")
            if not isinstance(job_id, int):
                continue
            logs = self._job_logs_with_retry(identity, job_id)
            snapshots.append(
                {
                    "id": job_id,
                    "name": item.get("name"),
                    "status": item.get("status"),
                    "conclusion": item.get("conclusion"),
                    "logs": logs,
                }
            )
        if not snapshots:
            raise github_controller_error(f"Workflow run {run_id} exposes no usable job records.")
        return {
            "id": run_id,
            "name": run.get("name"),
            "workflow_id": run.get("workflow_id"),
            "head_branch": run.get("head_branch"),
            "head_sha": run.get("head_sha"),
            "event": run.get("event"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "jobs": snapshots,
        }

    def _job_logs_with_retry(
        self,
        identity: github_repository_identity,
        job_id: int,
    ) -> str:
        last: Exception | None = None
        for delay in self._discovery_retry_delays:
            if delay > 0:
                time.sleep(delay)
            try:
                return self._client.workflow_job_logs(identity.owner, identity.name, job_id)
            except github_api_error as exc:
                last = exc
                if exc.status not in {404, 409}:
                    raise
        if last is not None:
            raise github_controller_error(
                f"Workflow job {job_id} logs did not become available: {last}"
            ) from last
        raise github_controller_error(f"Workflow job {job_id} logs did not become available.")


class github_f4_a_materializer(_github_f4_materializer_base):
    description = "Materialize or verify the engineering-reference F4-A world."

    def __init__(self, client: github_controller_client, *, spec: github_f4_a_spec, **kwargs) -> None:
        super().__init__(client, **kwargs)
        self._spec = spec

    def run(self) -> apparatus_action_result:
        identity, observations, changed = self._ensure()
        return apparatus_action_result(
            changed=changed,
            detail="materialized trusted F4-A CI-diagnosis fixture" if changed else "F4-A trusted fixture already exists and matches package-owned state",
            observations=observations,
        )

    def run_with_progress(self, report: Callable[[apparatus_action_progress], None]) -> apparatus_action_result:
        report(apparatus_action_progress(step=1, total=1, detail="materializing/verifying F4-A CI evidence"))
        return self.run()

    def inspect(self):
        identity, observations, _changed = self._ensure(allow_create=False)
        return identity, observations

    def _ensure(self, *, allow_create: bool = True):
        identity = self._resolve_identity("F4-A")
        pulls = tuple(self._client.list_pull_requests(identity.owner, identity.name))
        pr = _find_marker(pulls, self._spec.diagnosis_pr.marker)
        changed = False
        if pr is None:
            if not allow_create:
                raise github_controller_error("F4-A fixture is not fully materialized.")
            for path, content, message in (
                (self._spec.ci_policy_path, self._spec.ci_policy_content, "F4-A: add CI diagnosis policy"),
                (self._spec.protocol_source_path, self._spec.protocol_initial_content, "F4-A: seed protocol source"),
                (self._spec.release_manifest_path, self._spec.release_manifest_content, "F4-A: seed release manifest"),
                (self._spec.required_workflow.path, self._spec.required_workflow.content, "F4-A: add required validation workflow"),
            ):
                self._ensure_file(identity, path, content, message)
            base_sha = _head_sha(self._client, identity, identity.default_branch)
            self._client.create_ref(identity.owner, identity.name, self._spec.diagnosis_pr.branch, base_sha)
            update = self._update_branch_file(
                identity,
                self._spec.protocol_source_path,
                branch=self._spec.diagnosis_pr.branch,
                content=self._spec.protocol_pr_content,
                message="F4-A: advance project protocol level",
            )
            diagnosis_head = _nested_string(update, "commit", "sha")
            pr = self._client.create_pull_request(
                identity.owner,
                identity.name,
                title=self._spec.diagnosis_pr.title,
                head=self._spec.diagnosis_pr.branch,
                base=identity.default_branch,
                body=_marker_body(
                    self._spec.diagnosis_pr.marker,
                    "Advance the project protocol declaration for the pending candidate.",
                ),
            )
            changed = True
        pr_number = _required_int(pr, "number", "F4-A diagnosis PR number")
        current_pr = self._client.pull_request(identity.owner, identity.name, pr_number)
        diagnosis_head = _nested_string(current_pr, "head", "sha")
        if current_pr.get("state") != "open" or current_pr.get("merged") is True:
            raise github_controller_error("F4-A diagnosis PR is not open and unmerged.")
        protocol = self._client.read_text_file(
            identity.owner, identity.name, self._spec.protocol_source_path, ref=diagnosis_head
        )
        manifest = self._client.read_text_file(
            identity.owner, identity.name, self._spec.release_manifest_path, ref=diagnosis_head
        )
        if protocol != self._spec.protocol_pr_content or manifest != self._spec.release_manifest_content:
            raise github_controller_error("F4-A PR-head project values do not match fixture definition.")
        workflow = self._workflow(identity, self._spec.required_workflow.name)
        run = self._matching_run(
            identity,
            _required_int(workflow, "id", "F4-A workflow ID"),
            branch=self._spec.diagnosis_pr.branch,
            head_sha=diagnosis_head,
        )
        if run is None:
            if not allow_create:
                raise github_controller_error("F4-A required failed run is missing.")
            run = self._dispatch_and_wait(
                identity,
                workflow,
                branch=self._spec.diagnosis_pr.branch,
                head_sha=diagnosis_head,
                inputs={
                    "fixture": self._spec.fixture_id,
                    "project_level": "4",
                    "manifest_level": "3",
                },
                expected_conclusion="failure",
            )
            changed = True
        else:
            run = self._wait_run(identity, run)
            if run.get("conclusion") != "failure":
                raise github_controller_error("F4-A required run is not failed as designed.")
        evidence = self._run_evidence(identity, run)
        logs = "\n".join(str(job.get("logs", "")) for job in evidence["jobs"])
        for token in ("ACMM_VALIDATION_CODE=PROTOCOL_MANIFEST_MISMATCH", "project_protocol=4", "release_manifest=3"):
            if token not in logs:
                raise github_controller_error(f"F4-A required job logs are missing fixture token {token!r}.")
        return identity, {
            "fixture_id": self._spec.fixture_id,
            "diagnosis_pr_number": pr_number,
            "diagnosis_head": diagnosis_head,
            "required_workflow_id": _required_int(workflow, "id", "F4-A workflow ID"),
            "required_workflow_name": self._spec.required_workflow.name,
            "required_run": evidence,
        }, changed


class github_f4_b_materializer(_github_f4_materializer_base):
    description = "Materialize or verify the engineering-reference F4-B world."

    def __init__(self, client: github_controller_client, *, spec: github_f4_b_spec, **kwargs) -> None:
        super().__init__(client, **kwargs)
        self._spec = spec

    def run(self) -> apparatus_action_result:
        identity, observations, changed = self._ensure()
        return apparatus_action_result(
            changed=changed,
            detail="materialized trusted F4-B superseded-alert fixture" if changed else "F4-B trusted fixture already exists and matches package-owned state",
            observations=observations,
        )

    def run_with_progress(self, report: Callable[[apparatus_action_progress], None]) -> apparatus_action_result:
        report(apparatus_action_progress(step=1, total=1, detail="materializing/verifying F4-B CI evidence"))
        return self.run()

    def inspect(self):
        identity, observations, _changed = self._ensure(allow_create=False)
        return identity, observations

    def _ensure(self, *, allow_create: bool = True):
        identity = self._resolve_identity("F4-B")
        pulls = tuple(self._client.list_pull_requests(identity.owner, identity.name))
        issues = tuple(
            item for item in self._client.list_issues(identity.owner, identity.name) if "pull_request" not in item
        )
        pr = _find_marker(pulls, self._spec.candidate_pr.marker)
        issue = _find_marker(issues, self._spec.alert_issue.marker)
        changed = False
        if pr is None and issue is not None:
            raise github_controller_error("F4-B fixture is partially materialized.")
        if pr is None:
            if not allow_create:
                raise github_controller_error("F4-B fixture is not fully materialized.")
            for label in (self._spec.ci_blocked_label, self._spec.ci_resolved_label):
                self._ensure_label(identity, label)
            for path, content, message in (
                (self._spec.ci_status_policy_path, self._spec.ci_status_policy_content, "F4-B: add CI status policy"),
                (self._spec.candidate_state_path, self._spec.candidate_base_content, "F4-B: seed candidate validation state"),
                (self._spec.required_workflow.path, self._spec.required_workflow.content, "F4-B: add required validation workflow"),
                (self._spec.advisory_workflow.path, self._spec.advisory_workflow.content, "F4-B: add advisory workflow"),
            ):
                self._ensure_file(identity, path, content, message)
            base_sha = _head_sha(self._client, identity, identity.default_branch)
            self._client.create_ref(identity.owner, identity.name, self._spec.candidate_pr.branch, base_sha)
            old_update = self._update_branch_file(
                identity,
                self._spec.candidate_state_path,
                branch=self._spec.candidate_pr.branch,
                content=self._spec.candidate_old_content,
                message="F4-B: introduce old-head validation failure",
            )
            old_head = _nested_string(old_update, "commit", "sha")
            pr = self._client.create_pull_request(
                identity.owner,
                identity.name,
                title=self._spec.candidate_pr.title,
                head=self._spec.candidate_pr.branch,
                base=identity.default_branch,
                body=_marker_body(self._spec.candidate_pr.marker, "Candidate validation work with historical CI evidence."),
            )
            required_workflow = self._workflow(identity, self._spec.required_workflow.name)
            old_run = self._dispatch_and_wait(
                identity,
                required_workflow,
                branch=self._spec.candidate_pr.branch,
                head_sha=old_head,
                inputs={"fixture": self._spec.fixture_id, "expected": "fail"},
                expected_conclusion="failure",
            )
            old_run_id = _required_int(old_run, "id", "F4-B old required run ID")
            issue_body = (
                f"<!-- {self._spec.alert_issue.marker} -->\n\n{self._spec.alert_issue.body}\n\n"
                f"Historical required failure: run {old_run_id} on head `{old_head}`."
            )
            issue = self._client.create_issue(
                identity.owner,
                identity.name,
                title=self._spec.alert_issue.title,
                body=issue_body,
                labels=(self._spec.ci_blocked_label.name,),
            )
            current_update = self._update_branch_file(
                identity,
                self._spec.candidate_state_path,
                branch=self._spec.candidate_pr.branch,
                content=self._spec.candidate_current_content,
                message="F4-B: advance candidate to current valid state",
            )
            current_head = _nested_string(current_update, "commit", "sha")
            current_run = self._dispatch_and_wait(
                identity,
                required_workflow,
                branch=self._spec.candidate_pr.branch,
                head_sha=current_head,
                inputs={"fixture": self._spec.fixture_id, "expected": "pass"},
                expected_conclusion="success",
            )
            advisory_workflow = self._workflow(identity, self._spec.advisory_workflow.name)
            advisory_run = self._dispatch_and_wait(
                identity,
                advisory_workflow,
                branch=self._spec.candidate_pr.branch,
                head_sha=current_head,
                inputs={"fixture": self._spec.fixture_id},
                expected_conclusion="failure",
            )
            changed = True
        if issue is None:
            raise github_controller_error("F4-B CI alert issue is missing.")
        pr_number = _required_int(pr, "number", "F4-B candidate PR number")
        issue_number = _required_int(issue, "number", "F4-B alert issue number")
        current_pr = self._client.pull_request(identity.owner, identity.name, pr_number)
        current_head = _nested_string(current_pr, "head", "sha")
        if current_pr.get("state") != "open" or current_pr.get("merged") is True:
            raise github_controller_error("F4-B candidate PR is not open and unmerged.")
        issue_current = self._client.issue(identity.owner, identity.name, issue_number)
        labels = _label_names(issue_current)
        if issue_current.get("state") != "open" or self._spec.ci_blocked_label.name not in labels or self._spec.ci_resolved_label.name in labels:
            raise github_controller_error("F4-B alert issue is not in its pristine blocked state.")
        body = str(issue_current.get("body", ""))
        old_run_id, old_head = _parse_historical_run(body)
        required_workflow = self._workflow(identity, self._spec.required_workflow.name)
        advisory_workflow = self._workflow(identity, self._spec.advisory_workflow.name)
        old_run = self._client.workflow_run(identity.owner, identity.name, old_run_id)
        if old_run.get("head_sha") != old_head or old_run.get("conclusion") != "failure":
            raise github_controller_error("F4-B historical required run does not match alert history.")
        current_run = self._matching_run(
            identity,
            _required_int(required_workflow, "id", "F4-B required workflow ID"),
            branch=self._spec.candidate_pr.branch,
            head_sha=current_head,
        )
        advisory_run = self._matching_run(
            identity,
            _required_int(advisory_workflow, "id", "F4-B advisory workflow ID"),
            branch=self._spec.candidate_pr.branch,
            head_sha=current_head,
        )
        if current_run is None or advisory_run is None:
            raise github_controller_error("F4-B current workflow evidence is incomplete.")
        current_run = self._wait_run(identity, current_run)
        advisory_run = self._wait_run(identity, advisory_run)
        if current_run.get("conclusion") != "success" or advisory_run.get("conclusion") != "failure":
            raise github_controller_error("F4-B current workflow conclusions do not match fixture design.")
        current_content = self._client.read_text_file(
            identity.owner, identity.name, self._spec.candidate_state_path, ref=current_head
        )
        if current_content != self._spec.candidate_current_content:
            raise github_controller_error("F4-B current candidate content does not match fixture design.")
        old_evidence = self._run_evidence(identity, old_run)
        current_evidence = self._run_evidence(identity, current_run)
        advisory_evidence = self._run_evidence(identity, advisory_run)
        return identity, {
            "fixture_id": self._spec.fixture_id,
            "candidate_pr_number": pr_number,
            "ci_alert_issue_number": issue_number,
            "old_head": old_head,
            "current_head": current_head,
            "required_workflow_id": _required_int(required_workflow, "id", "F4-B required workflow ID"),
            "required_workflow_name": self._spec.required_workflow.name,
            "advisory_workflow_id": _required_int(advisory_workflow, "id", "F4-B advisory workflow ID"),
            "advisory_workflow_name": self._spec.advisory_workflow.name,
            "old_required_run": old_evidence,
            "current_required_run": current_evidence,
            "current_advisory_run": advisory_evidence,
        }, changed


def load_f4_a_spec(value: Mapping[str, Any], *, workflow_content: str) -> github_f4_a_spec:
    _require_schema(value, "F4-A")
    return github_f4_a_spec(
        fixture_id="github_workspace_f4_a",
        ci_policy_path=_required_string(value, "ci_policy_path", "F4-A CI policy path"),
        ci_policy_content=_required_string(value, "ci_policy_content", "F4-A CI policy content"),
        protocol_source_path=_required_string(value, "protocol_source_path", "F4-A protocol source path"),
        protocol_initial_content=_required_string(value, "protocol_initial_content", "F4-A protocol initial content"),
        protocol_pr_content=_required_string(value, "protocol_pr_content", "F4-A protocol PR content"),
        release_manifest_path=_required_string(value, "release_manifest_path", "F4-A release manifest path"),
        release_manifest_content=_required_string(value, "release_manifest_content", "F4-A release manifest content"),
        diagnosis_pr=_load_pr(value, "diagnosis_pr", "F4-A"),
        required_workflow=_load_workflow(value, "required_workflow", workflow_content, "F4-A"),
    )


def load_f4_b_spec(
    value: Mapping[str, Any],
    *,
    required_workflow_content: str,
    advisory_workflow_content: str,
) -> github_f4_b_spec:
    _require_schema(value, "F4-B")
    return github_f4_b_spec(
        fixture_id="github_workspace_f4_b",
        ci_status_policy_path=_required_string(value, "ci_status_policy_path", "F4-B CI status policy path"),
        ci_status_policy_content=_required_string(value, "ci_status_policy_content", "F4-B CI status policy content"),
        candidate_state_path=_required_string(value, "candidate_state_path", "F4-B candidate state path"),
        candidate_base_content=_required_string(value, "candidate_base_content", "F4-B candidate base content"),
        candidate_old_content=_required_string(value, "candidate_old_content", "F4-B candidate old content"),
        candidate_current_content=_required_string(value, "candidate_current_content", "F4-B candidate current content"),
        candidate_pr=_load_pr(value, "candidate_pr", "F4-B"),
        alert_issue=_load_issue(value, "alert_issue", "F4-B"),
        ci_blocked_label=_load_label(value, "ci_blocked_label", "F4-B"),
        ci_resolved_label=_load_label(value, "ci_resolved_label", "F4-B"),
        required_workflow=_load_workflow(value, "required_workflow", required_workflow_content, "F4-B"),
        advisory_workflow=_load_workflow(value, "advisory_workflow", advisory_workflow_content, "F4-B"),
    )


def _load_pr(value: Mapping[str, Any], key: str, label: str) -> github_f4_pr_spec:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"{label} {key} must contain an object.")
    return github_f4_pr_spec(
        title=_required_string(item, "title", f"{label} {key} title"),
        marker=_required_string(item, "marker", f"{label} {key} marker"),
        branch=_required_string(item, "branch", f"{label} {key} branch"),
    )


def _load_issue(value: Mapping[str, Any], key: str, label: str) -> github_f4_issue_spec:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"{label} {key} must contain an object.")
    return github_f4_issue_spec(
        title=_required_string(item, "title", f"{label} {key} title"),
        marker=_required_string(item, "marker", f"{label} {key} marker"),
        body=_required_string(item, "body", f"{label} {key} body"),
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


def _load_workflow(
    value: Mapping[str, Any],
    key: str,
    content: str,
    label: str,
) -> github_f4_workflow_spec:
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


def _find_marker(values: tuple[Mapping[str, Any], ...], marker: str) -> Mapping[str, Any] | None:
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


def _parse_historical_run(body: str) -> tuple[int, str]:
    marker = "Historical required failure: run "
    if marker not in body or " on head `" not in body:
        raise github_controller_error("F4-B alert issue does not record historical run identity.")
    tail = body.split(marker, 1)[1]
    run_text, head_tail = tail.split(" on head `", 1)
    head = head_tail.split("`", 1)[0]
    try:
        run_id = int(run_text.strip())
    except ValueError as exc:
        raise github_controller_error("F4-B alert issue historical run ID is invalid.") from exc
    if len(head) < 7:
        raise github_controller_error("F4-B alert issue historical head SHA is invalid.")
    return run_id, head
