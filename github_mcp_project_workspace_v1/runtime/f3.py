from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable, Mapping

from acmm.experiment_api import apparatus_action_progress, apparatus_action_result

from .controller import (
    github_controller_client,
    github_controller_error,
    github_fixture_base_file,
    github_repository_identity,
)


@dataclass(frozen=True)
class github_f3_label_spec:
    name: str
    color: str
    description: str


@dataclass(frozen=True)
class github_f3_issue_spec:
    title: str
    marker: str
    body: str


@dataclass(frozen=True)
class github_f3_pr_spec:
    title: str
    marker: str
    branch: str


@dataclass(frozen=True)
class github_f3_a_spec:
    fixture_id: str
    project_record_policy_path: str
    project_record_policy_content: str
    target_implementation_path: str
    target_initial_content: str
    target_delivered_content: str
    decoy_support_path: str
    decoy_support_content: str
    implemented_label: github_f3_label_spec
    linkage_audit_label: github_f3_label_spec
    implementation_issue: github_f3_issue_spec
    implementation_pr: github_f3_pr_spec
    decoy_pr: github_f3_pr_spec


@dataclass(frozen=True)
class github_f3_b_spec:
    fixture_id: str
    release_status_policy_path: str
    release_status_policy_content: str
    target_fix_path: str
    target_initial_content: str
    target_old_fix_content: str
    target_reverted_content: str
    target_revised_fix_content: str
    release_blocker_label: github_f3_label_spec
    ready_label: github_f3_label_spec
    blocked_label: github_f3_label_spec
    tracking_issue: github_f3_issue_spec
    old_fix_pr: github_f3_pr_spec
    revert_pr: github_f3_pr_spec
    replacement_pr: github_f3_pr_spec


class github_f3_a_materializer:
    description = "Materialize or verify the engineering-reference F3-A world."
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
        spec: github_f3_a_spec,
    ) -> None:
        self._client = client
        self._repository_name = repository_name
        self._expected_repository_full_name = expected_repository_full_name
        self._expected_repository_id = expected_repository_id
        self._expected_default_branch = expected_default_branch
        self._fixture_base_files = tuple(fixture_base_files)
        self._spec = spec
        self._discovery_retry_delays = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)

    def run(self) -> apparatus_action_result:
        return self._run(None)

    def run_with_progress(
        self,
        report: Callable[[apparatus_action_progress], None],
    ) -> apparatus_action_result:
        return self._run(report)

    def inspect(self):
        identity = self._resolve_identity()
        discovered = self._discover_with_retry(
            identity,
            report=None,
            total=8,
            require_complete=True,
        )
        return identity, self._verify(identity, discovered)

    def _run(
        self,
        report: Callable[[apparatus_action_progress], None] | None,
    ) -> apparatus_action_result:
        total = 8
        _emit(report, 1, total, "verifying repository identity and trusted fixture base")
        identity = self._resolve_identity()
        _emit(report, 2, total, "discovering existing F3-A fixture markers")
        discovered = self._discover_with_retry(identity, report=report, total=total)
        changed = False
        if not discovered["present"]:
            observations = self._materialize(identity, report=report, total=total)
            changed = True
            discovered = self._direct_discovery(identity, observations)
        else:
            for step, label in (
                (3, "F3-A labels, policy, and target baseline"),
                (4, "actual implementation pull request"),
                (5, "later documentation decoy pull request"),
                (6, "closed implementation issue"),
                (7, "historical stale provenance comment"),
            ):
                _emit(report, step, total, f"skipped (already intact): {label}")
        observations = self._verify(identity, discovered)
        _emit(report, 8, total, "F3-A fixture verification complete")
        return apparatus_action_result(
            changed=changed,
            detail=(
                "materialized trusted F3-A implementation-provenance fixture"
                if changed
                else "F3-A trusted fixture already exists and matches package-owned state"
            ),
            observations=observations,
        )

    def _resolve_identity(self) -> github_repository_identity:
        return _resolve_identity(
            self._client,
            repository_name=self._repository_name,
            expected_repository_full_name=self._expected_repository_full_name,
            expected_repository_id=self._expected_repository_id,
            expected_default_branch=self._expected_default_branch,
            fixture_base_files=self._fixture_base_files,
            label="F3-A",
        )

    def _discover_once(self, identity: github_repository_identity) -> dict[str, Any]:
        issues = tuple(
            item
            for item in self._client.list_issues(identity.owner, identity.name)
            if "pull_request" not in item
        )
        pulls = tuple(self._client.list_pull_requests(identity.owner, identity.name))
        objects = {
            "implementation_issue": _find_marker(
                issues,
                self._spec.implementation_issue.marker,
                "F3-A",
            ),
            "implementation_pr": _find_marker(
                pulls,
                self._spec.implementation_pr.marker,
                "F3-A",
            ),
            "decoy_pr": _find_marker(pulls, self._spec.decoy_pr.marker, "F3-A"),
        }
        return _discovery(objects)

    def _discover_with_retry(
        self,
        identity: github_repository_identity,
        *,
        report: Callable[[apparatus_action_progress], None] | None,
        total: int,
        require_complete: bool = False,
    ) -> dict[str, Any]:
        return _discover_with_retry(
            self._client,
            self._discover_once,
            identity,
            label="F3-A",
            report=report,
            total=total,
            require_complete=require_complete,
            delays=self._discovery_retry_delays,
        )

    def _materialize(
        self,
        identity: github_repository_identity,
        *,
        report: Callable[[apparatus_action_progress], None] | None,
        total: int,
    ) -> Mapping[str, Any]:
        owner = identity.owner
        repo = identity.name
        branch = identity.default_branch

        _emit(report, 3, total, "seeding F3-A labels, policy, and target baseline")
        for label in (self._spec.implemented_label, self._spec.linkage_audit_label):
            _ensure_label(self._client, identity, label, "F3-A")
        with self._client.git_publish_batch(owner, repo):
            _ensure_file(
                self._client,
                identity,
                self._spec.project_record_policy_path,
                self._spec.project_record_policy_content,
                "F3-A: add project-record policy",
                "F3-A",
            )
            _ensure_file(
                self._client,
                identity,
                self._spec.target_implementation_path,
                self._spec.target_initial_content,
                "F3-A: seed implementation target",
                "F3-A",
            )

        _emit(report, 4, total, "creating and merging the actual implementation pull request")
        implementation_base = _head_sha(self._client, identity)
        self._client.create_ref(
            owner,
            repo,
            self._spec.implementation_pr.branch,
            implementation_base,
        )
        implementation_change = _create_or_update_branch_file(
            self._client,
            identity,
            self._spec.target_implementation_path,
            message="F3-A: deliver quoted empty-field normalization",
            content=self._spec.target_delivered_content,
            branch=self._spec.implementation_pr.branch,
            label="F3-A implementation change",
        )
        delivery_commit = _nested_string(implementation_change, "commit", "sha", label="F3-A")
        implementation_pr = self._client.create_pull_request(
            owner,
            repo,
            title=self._spec.implementation_pr.title,
            head=self._spec.implementation_pr.branch,
            base=branch,
            body=_marker_body(
                self._spec.implementation_pr.marker,
                "Implements the requested export-normalization behavior.",
            ),
        )
        implementation_pr_number = _required_int(
            implementation_pr,
            "number",
            "F3-A implementation PR number",
        )
        implementation_merge = self._client.merge_pull_request(
            owner,
            repo,
            implementation_pr_number,
            commit_title="F3-A: merge export-normalization implementation",
        )
        if implementation_merge.get("merged") is not True:
            raise github_controller_error("GitHub did not merge the F3-A implementation PR.")
        implementation_merge_commit = _required_string(
            implementation_merge,
            "sha",
            "F3-A implementation merge commit",
        )

        _emit(report, 5, total, "creating and merging the later documentation decoy pull request")
        decoy_base = _head_sha(self._client, identity)
        self._client.create_ref(owner, repo, self._spec.decoy_pr.branch, decoy_base)
        decoy_change = _create_or_update_branch_file(
            self._client,
            identity,
            self._spec.decoy_support_path,
            message="F3-A: document export normalization",
            content=self._spec.decoy_support_content,
            branch=self._spec.decoy_pr.branch,
            label="F3-A decoy documentation change",
        )
        decoy_commit = _nested_string(decoy_change, "commit", "sha", label="F3-A")
        decoy_pr = self._client.create_pull_request(
            owner,
            repo,
            title=self._spec.decoy_pr.title,
            head=self._spec.decoy_pr.branch,
            base=branch,
            body=_marker_body(
                self._spec.decoy_pr.marker,
                "Documents the same feature area after implementation landed.",
            ),
        )
        decoy_pr_number = _required_int(decoy_pr, "number", "F3-A decoy PR number")
        decoy_merge = self._client.merge_pull_request(
            owner,
            repo,
            decoy_pr_number,
            commit_title="F3-A: merge export-normalization documentation",
        )
        if decoy_merge.get("merged") is not True:
            raise github_controller_error("GitHub did not merge the F3-A decoy PR.")
        decoy_merge_commit = _required_string(
            decoy_merge,
            "sha",
            "F3-A decoy merge commit",
        )

        _emit(report, 6, total, "creating the completed implementation issue")
        issue = self._client.create_issue(
            owner,
            repo,
            title=self._spec.implementation_issue.title,
            body=_marker_body(
                self._spec.implementation_issue.marker,
                self._spec.implementation_issue.body,
            ),
            labels=(
                self._spec.implemented_label.name,
                self._spec.linkage_audit_label.name,
            ),
        )
        issue_number = _required_int(issue, "number", "F3-A implementation issue number")
        self._client.update_issue(owner, repo, issue_number, {"state": "closed"})

        _emit(report, 7, total, "recording the stale historical delivery linkage")
        historical = self._client.create_issue_comment(
            owner,
            repo,
            issue_number,
            (
                f"Implementation was delivered by pull request #{decoy_pr_number}; "
                "this linkage is retained as historical project-record context."
            ),
        )
        historical_comment_id = _required_int(
            historical,
            "id",
            "F3-A historical comment id",
        )
        return {
            "implementation_issue_number": issue_number,
            "implementation_pr_number": implementation_pr_number,
            "decoy_pr_number": decoy_pr_number,
            "delivery_commit": delivery_commit,
            "decoy_commit": decoy_commit,
            "implementation_merge_commit": implementation_merge_commit,
            "decoy_merge_commit": decoy_merge_commit,
            "historical_comment_id": historical_comment_id,
        }

    def _direct_discovery(
        self,
        identity: github_repository_identity,
        observations: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "present": True,
            "complete": True,
            "present_names": ("decoy_pr", "implementation_issue", "implementation_pr"),
            "missing_names": (),
            "implementation_issue": self._client.issue(
                identity.owner,
                identity.name,
                int(observations["implementation_issue_number"]),
            ),
            "implementation_pr": self._client.pull_request(
                identity.owner,
                identity.name,
                int(observations["implementation_pr_number"]),
            ),
            "decoy_pr": self._client.pull_request(
                identity.owner,
                identity.name,
                int(observations["decoy_pr_number"]),
            ),
            "observations": dict(observations),
        }

    def _verify(
        self,
        identity: github_repository_identity,
        discovered: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not discovered.get("complete"):
            raise github_controller_error("F3-A fixture is incomplete.")
        issue = _require_mapping(discovered, "implementation_issue", "F3-A implementation issue")
        implementation_pr = _require_mapping(discovered, "implementation_pr", "F3-A implementation PR")
        decoy_pr = _require_mapping(discovered, "decoy_pr", "F3-A decoy PR")
        issue_number = _required_int(issue, "number", "F3-A implementation issue number")
        implementation_pr_number = _required_int(
            implementation_pr,
            "number",
            "F3-A implementation PR number",
        )
        decoy_pr_number = _required_int(decoy_pr, "number", "F3-A decoy PR number")
        if issue.get("state") != "closed":
            raise github_controller_error("F3-A implementation issue must begin closed.")
        if _label_names(issue) != sorted(
            [self._spec.implemented_label.name, self._spec.linkage_audit_label.name]
        ):
            raise github_controller_error("F3-A implementation issue labels are not pristine.")
        full_implementation_pr = self._client.pull_request(
            identity.owner,
            identity.name,
            implementation_pr_number,
        )
        full_decoy_pr = self._client.pull_request(identity.owner, identity.name, decoy_pr_number)
        if full_implementation_pr.get("merged") is not True or full_decoy_pr.get("merged") is not True:
            raise github_controller_error("F3-A requires both candidate pull requests to be merged.")
        delivery_commit = _nested_string(
            full_implementation_pr,
            "head",
            "sha",
            label="F3-A",
        )
        decoy_commit = _nested_string(full_decoy_pr, "head", "sha", label="F3-A")
        comments = tuple(self._client.issue_comments(identity.owner, identity.name, issue_number))
        if len(comments) != 1:
            raise github_controller_error("F3-A implementation issue must contain one historical comment.")
        historical_body = str(comments[0].get("body", ""))
        if f"#{decoy_pr_number}" not in historical_body or f"#{implementation_pr_number}" in historical_body:
            raise github_controller_error("F3-A historical provenance comment is not the intended stale linkage.")
        default_head = _head_sha(self._client, identity)
        _verify_file(
            self._client,
            identity,
            self._spec.project_record_policy_path,
            self._spec.project_record_policy_content,
            "F3-A",
            ref=default_head,
        )
        _verify_file(
            self._client,
            identity,
            self._spec.target_implementation_path,
            self._spec.target_delivered_content,
            "F3-A",
            ref=default_head,
        )
        _verify_file(
            self._client,
            identity,
            self._spec.decoy_support_path,
            self._spec.decoy_support_content,
            "F3-A",
            ref=default_head,
        )
        commits = self._client.list_commits(
            identity.owner,
            identity.name,
            sha=identity.default_branch,
        )
        reachable = {item.get("sha") for item in commits if isinstance(item.get("sha"), str)}
        if delivery_commit not in reachable or decoy_commit not in reachable:
            raise github_controller_error("F3-A merged pull-request head commits are not reachable from the default branch.")
        return {
            "implementation_issue_number": issue_number,
            "implementation_pr_number": implementation_pr_number,
            "decoy_pr_number": decoy_pr_number,
            "delivery_commit": delivery_commit,
            "decoy_commit": decoy_commit,
            "implementation_merge_commit": _required_string(
                full_implementation_pr,
                "merge_commit_sha",
                "F3-A implementation merge commit",
            ),
            "decoy_merge_commit": _required_string(
                full_decoy_pr,
                "merge_commit_sha",
                "F3-A decoy merge commit",
            ),
            "historical_comment_id": _required_int(
                comments[0],
                "id",
                "F3-A historical comment id",
            ),
        }


class github_f3_b_materializer:
    description = "Materialize or verify the engineering-reference F3-B world."
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
        spec: github_f3_b_spec,
    ) -> None:
        self._client = client
        self._repository_name = repository_name
        self._expected_repository_full_name = expected_repository_full_name
        self._expected_repository_id = expected_repository_id
        self._expected_default_branch = expected_default_branch
        self._fixture_base_files = tuple(fixture_base_files)
        self._spec = spec
        self._discovery_retry_delays = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)

    def run(self) -> apparatus_action_result:
        return self._run(None)

    def run_with_progress(
        self,
        report: Callable[[apparatus_action_progress], None],
    ) -> apparatus_action_result:
        return self._run(report)

    def inspect(self):
        identity = self._resolve_identity()
        discovered = self._discover_with_retry(
            identity,
            report=None,
            total=9,
            require_complete=True,
        )
        return identity, self._verify(identity, discovered)

    def _run(
        self,
        report: Callable[[apparatus_action_progress], None] | None,
    ) -> apparatus_action_result:
        total = 9
        _emit(report, 1, total, "verifying repository identity and trusted fixture base")
        identity = self._resolve_identity()
        _emit(report, 2, total, "discovering existing F3-B fixture markers")
        discovered = self._discover_with_retry(identity, report=report, total=total)
        changed = False
        if not discovered["present"]:
            observations = self._materialize(identity, report=report, total=total)
            changed = True
            discovered = self._direct_discovery(identity, observations)
        else:
            for step, label in (
                (3, "F3-B labels, release policy, and target baseline"),
                (4, "merged historical fix"),
                (5, "merged revert"),
                (6, "open replacement pull request"),
                (7, "stale release-blocker tracking record"),
                (8, "historical delivery comment"),
            ):
                _emit(report, step, total, f"skipped (already intact): {label}")
        observations = self._verify(identity, discovered)
        _emit(report, 9, total, "F3-B fixture verification complete")
        return apparatus_action_result(
            changed=changed,
            detail=(
                "materialized trusted F3-B reverted-fix status fixture"
                if changed
                else "F3-B trusted fixture already exists and matches package-owned state"
            ),
            observations=observations,
        )

    def _resolve_identity(self) -> github_repository_identity:
        return _resolve_identity(
            self._client,
            repository_name=self._repository_name,
            expected_repository_full_name=self._expected_repository_full_name,
            expected_repository_id=self._expected_repository_id,
            expected_default_branch=self._expected_default_branch,
            fixture_base_files=self._fixture_base_files,
            label="F3-B",
        )

    def _discover_once(self, identity: github_repository_identity) -> dict[str, Any]:
        issues = tuple(
            item
            for item in self._client.list_issues(identity.owner, identity.name)
            if "pull_request" not in item
        )
        pulls = tuple(self._client.list_pull_requests(identity.owner, identity.name))
        objects = {
            "tracking_issue": _find_marker(issues, self._spec.tracking_issue.marker, "F3-B"),
            "old_fix_pr": _find_marker(pulls, self._spec.old_fix_pr.marker, "F3-B"),
            "revert_pr": _find_marker(pulls, self._spec.revert_pr.marker, "F3-B"),
            "replacement_pr": _find_marker(pulls, self._spec.replacement_pr.marker, "F3-B"),
        }
        return _discovery(objects)

    def _discover_with_retry(
        self,
        identity: github_repository_identity,
        *,
        report: Callable[[apparatus_action_progress], None] | None,
        total: int,
        require_complete: bool = False,
    ) -> dict[str, Any]:
        return _discover_with_retry(
            self._client,
            self._discover_once,
            identity,
            label="F3-B",
            report=report,
            total=total,
            require_complete=require_complete,
            delays=self._discovery_retry_delays,
        )

    def _materialize(
        self,
        identity: github_repository_identity,
        *,
        report: Callable[[apparatus_action_progress], None] | None,
        total: int,
    ) -> Mapping[str, Any]:
        owner = identity.owner
        repo = identity.name
        branch = identity.default_branch

        _emit(report, 3, total, "seeding F3-B labels, release policy, and target baseline")
        for label in (
            self._spec.release_blocker_label,
            self._spec.ready_label,
            self._spec.blocked_label,
        ):
            _ensure_label(self._client, identity, label, "F3-B")
        with self._client.git_publish_batch(owner, repo):
            _ensure_file(
                self._client,
                identity,
                self._spec.release_status_policy_path,
                self._spec.release_status_policy_content,
                "F3-B: add release-status policy",
                "F3-B",
            )
            _ensure_file(
                self._client,
                identity,
                self._spec.target_fix_path,
                self._spec.target_initial_content,
                "F3-B: seed protocol-guard baseline",
                "F3-B",
            )

        _emit(report, 4, total, "creating and merging the historical fix")
        old_fix_base = _head_sha(self._client, identity)
        self._client.create_ref(owner, repo, self._spec.old_fix_pr.branch, old_fix_base)
        old_fix_change = _create_or_update_branch_file(
            self._client,
            identity,
            self._spec.target_fix_path,
            message="F3-B: implement protocol guard",
            content=self._spec.target_old_fix_content,
            branch=self._spec.old_fix_pr.branch,
            label="F3-B old-fix change",
        )
        old_fix_commit = _nested_string(old_fix_change, "commit", "sha", label="F3-B")
        old_fix_pr = self._client.create_pull_request(
            owner,
            repo,
            title=self._spec.old_fix_pr.title,
            head=self._spec.old_fix_pr.branch,
            base=branch,
            body=_marker_body(
                self._spec.old_fix_pr.marker,
                "Delivers the original protocol-guard fix.",
            ),
        )
        old_fix_pr_number = _required_int(old_fix_pr, "number", "F3-B old fix PR number")
        old_fix_merge = self._client.merge_pull_request(
            owner,
            repo,
            old_fix_pr_number,
            commit_title="F3-B: merge protocol-guard fix",
        )
        if old_fix_merge.get("merged") is not True:
            raise github_controller_error("GitHub did not merge the F3-B old-fix PR.")

        _emit(report, 5, total, "creating and merging the explicit revert")
        revert_base = _head_sha(self._client, identity)
        self._client.create_ref(owner, repo, self._spec.revert_pr.branch, revert_base)
        revert_change = _create_or_update_branch_file(
            self._client,
            identity,
            self._spec.target_fix_path,
            message="F3-B: revert protocol guard after compatibility regression",
            content=self._spec.target_reverted_content,
            branch=self._spec.revert_pr.branch,
            label="F3-B revert change",
        )
        revert_commit = _nested_string(revert_change, "commit", "sha", label="F3-B")
        revert_pr = self._client.create_pull_request(
            owner,
            repo,
            title=self._spec.revert_pr.title,
            head=self._spec.revert_pr.branch,
            base=branch,
            body=_marker_body(
                self._spec.revert_pr.marker,
                f"Reverts the behavior delivered by pull request #{old_fix_pr_number}.",
            ),
        )
        revert_pr_number = _required_int(revert_pr, "number", "F3-B revert PR number")
        revert_merge = self._client.merge_pull_request(
            owner,
            repo,
            revert_pr_number,
            commit_title="F3-B: merge protocol-guard revert",
        )
        if revert_merge.get("merged") is not True:
            raise github_controller_error("GitHub did not merge the F3-B revert PR.")

        _emit(report, 6, total, "creating the open replacement pull request")
        replacement_base = _head_sha(self._client, identity)
        self._client.create_ref(
            owner,
            repo,
            self._spec.replacement_pr.branch,
            replacement_base,
        )
        replacement_change = _create_or_update_branch_file(
            self._client,
            identity,
            self._spec.target_fix_path,
            message="F3-B: prepare compatibility-safe protocol guard",
            content=self._spec.target_revised_fix_content,
            branch=self._spec.replacement_pr.branch,
            label="F3-B replacement change",
        )
        revised_fix_commit = _nested_string(
            replacement_change,
            "commit",
            "sha",
            label="F3-B",
        )
        replacement_pr = self._client.create_pull_request(
            owner,
            repo,
            title=self._spec.replacement_pr.title,
            head=self._spec.replacement_pr.branch,
            base=branch,
            body=_marker_body(
                self._spec.replacement_pr.marker,
                "Proposes a revised compatibility-safe replacement for the reverted guard.",
            ),
        )
        replacement_pr_number = _required_int(
            replacement_pr,
            "number",
            "F3-B replacement PR number",
        )

        _emit(report, 7, total, "creating the stale release-blocker tracking record")
        tracking = self._client.create_issue(
            owner,
            repo,
            title=self._spec.tracking_issue.title,
            body=_marker_body(self._spec.tracking_issue.marker, self._spec.tracking_issue.body),
            labels=(self._spec.release_blocker_label.name, self._spec.ready_label.name),
        )
        tracking_issue_number = _required_int(
            tracking,
            "number",
            "F3-B tracking issue number",
        )

        _emit(report, 8, total, "recording historically correct original-fix provenance")
        historical = self._client.create_issue_comment(
            owner,
            repo,
            tracking_issue_number,
            (
                f"Original fix delivered by pull request #{old_fix_pr_number} "
                f"at commit `{old_fix_commit}`; historical delivery record retained."
            ),
        )
        historical_comment_id = _required_int(
            historical,
            "id",
            "F3-B historical comment id",
        )
        return {
            "tracking_issue_number": tracking_issue_number,
            "old_fix_pr_number": old_fix_pr_number,
            "revert_pr_number": revert_pr_number,
            "replacement_pr_number": replacement_pr_number,
            "old_fix_commit": old_fix_commit,
            "revert_commit": revert_commit,
            "revised_fix_commit": revised_fix_commit,
            "old_fix_merge_commit": _required_string(
                old_fix_merge,
                "sha",
                "F3-B old fix merge commit",
            ),
            "revert_merge_commit": _required_string(
                revert_merge,
                "sha",
                "F3-B revert merge commit",
            ),
            "historical_comment_id": historical_comment_id,
        }

    def _direct_discovery(
        self,
        identity: github_repository_identity,
        observations: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "present": True,
            "complete": True,
            "present_names": ("old_fix_pr", "replacement_pr", "revert_pr", "tracking_issue"),
            "missing_names": (),
            "tracking_issue": self._client.issue(
                identity.owner,
                identity.name,
                int(observations["tracking_issue_number"]),
            ),
            "old_fix_pr": self._client.pull_request(
                identity.owner,
                identity.name,
                int(observations["old_fix_pr_number"]),
            ),
            "revert_pr": self._client.pull_request(
                identity.owner,
                identity.name,
                int(observations["revert_pr_number"]),
            ),
            "replacement_pr": self._client.pull_request(
                identity.owner,
                identity.name,
                int(observations["replacement_pr_number"]),
            ),
            "observations": dict(observations),
        }

    def _verify(
        self,
        identity: github_repository_identity,
        discovered: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not discovered.get("complete"):
            raise github_controller_error("F3-B fixture is incomplete.")
        tracking = _require_mapping(discovered, "tracking_issue", "F3-B tracking issue")
        old_fix_pr = _require_mapping(discovered, "old_fix_pr", "F3-B old fix PR")
        revert_pr = _require_mapping(discovered, "revert_pr", "F3-B revert PR")
        replacement_pr = _require_mapping(discovered, "replacement_pr", "F3-B replacement PR")
        tracking_number = _required_int(tracking, "number", "F3-B tracking issue number")
        old_fix_pr_number = _required_int(old_fix_pr, "number", "F3-B old fix PR number")
        revert_pr_number = _required_int(revert_pr, "number", "F3-B revert PR number")
        replacement_pr_number = _required_int(
            replacement_pr,
            "number",
            "F3-B replacement PR number",
        )
        if tracking.get("state") != "open":
            raise github_controller_error("F3-B tracking issue must begin open.")
        if _label_names(tracking) != sorted(
            [self._spec.release_blocker_label.name, self._spec.ready_label.name]
        ):
            raise github_controller_error("F3-B tracking issue labels are not the intended stale state.")
        full_old_fix = self._client.pull_request(identity.owner, identity.name, old_fix_pr_number)
        full_revert = self._client.pull_request(identity.owner, identity.name, revert_pr_number)
        full_replacement = self._client.pull_request(
            identity.owner,
            identity.name,
            replacement_pr_number,
        )
        if full_old_fix.get("merged") is not True or full_revert.get("merged") is not True:
            raise github_controller_error("F3-B old-fix and revert pull requests must be merged.")
        if full_replacement.get("state") != "open" or full_replacement.get("merged") is True:
            raise github_controller_error("F3-B replacement pull request must remain open and unmerged.")
        old_fix_commit = _nested_string(full_old_fix, "head", "sha", label="F3-B")
        revert_commit = _nested_string(full_revert, "head", "sha", label="F3-B")
        revised_fix_commit = _nested_string(full_replacement, "head", "sha", label="F3-B")
        default_head = _head_sha(self._client, identity)
        _verify_file(
            self._client,
            identity,
            self._spec.release_status_policy_path,
            self._spec.release_status_policy_content,
            "F3-B",
            ref=default_head,
        )
        _verify_file(
            self._client,
            identity,
            self._spec.target_fix_path,
            self._spec.target_reverted_content,
            "F3-B",
            ref=default_head,
        )
        replacement_head = _nested_string(
            self._client.ref(
                identity.owner,
                identity.name,
                f"heads/{self._spec.replacement_pr.branch}",
            ),
            "object",
            "sha",
            label="F3-B replacement branch",
        )
        replacement_content = self._client.read_text_file(
            identity.owner,
            identity.name,
            self._spec.target_fix_path,
            ref=replacement_head,
        )
        if replacement_content != self._spec.target_revised_fix_content:
            raise github_controller_error("F3-B replacement branch does not contain the revised fix.")
        commits = self._client.list_commits(
            identity.owner,
            identity.name,
            sha=identity.default_branch,
        )
        reachable = {item.get("sha") for item in commits if isinstance(item.get("sha"), str)}
        if old_fix_commit not in reachable or revert_commit not in reachable:
            raise github_controller_error("F3-B historical fix/revert commits are not reachable from the default branch.")
        if revised_fix_commit in reachable:
            raise github_controller_error("F3-B replacement commit must not be reachable from the default branch.")
        comments = tuple(self._client.issue_comments(identity.owner, identity.name, tracking_number))
        if len(comments) != 1:
            raise github_controller_error("F3-B tracking issue must contain one historical delivery comment.")
        body = str(comments[0].get("body", ""))
        if f"#{old_fix_pr_number}" not in body or old_fix_commit not in body:
            raise github_controller_error("F3-B historical old-fix delivery comment is missing.")
        return {
            "tracking_issue_number": tracking_number,
            "old_fix_pr_number": old_fix_pr_number,
            "revert_pr_number": revert_pr_number,
            "replacement_pr_number": replacement_pr_number,
            "old_fix_commit": old_fix_commit,
            "revert_commit": revert_commit,
            "revised_fix_commit": revised_fix_commit,
            "old_fix_merge_commit": _required_string(
                full_old_fix,
                "merge_commit_sha",
                "F3-B old fix merge commit",
            ),
            "revert_merge_commit": _required_string(
                full_revert,
                "merge_commit_sha",
                "F3-B revert merge commit",
            ),
            "historical_comment_id": _required_int(
                comments[0],
                "id",
                "F3-B historical comment id",
            ),
        }


def load_f3_a_spec(value: Mapping[str, Any]) -> github_f3_a_spec:
    _require_schema(value, "F3-A")
    return github_f3_a_spec(
        fixture_id="github_workspace_f3_a",
        project_record_policy_path=_required_string(
            value,
            "project_record_policy_path",
            "F3-A project-record policy path",
        ),
        project_record_policy_content=_required_string(
            value,
            "project_record_policy_content",
            "F3-A project-record policy content",
        ),
        target_implementation_path=_required_string(
            value,
            "target_implementation_path",
            "F3-A target implementation path",
        ),
        target_initial_content=_required_string(
            value,
            "target_initial_content",
            "F3-A target initial content",
        ),
        target_delivered_content=_required_string(
            value,
            "target_delivered_content",
            "F3-A target delivered content",
        ),
        decoy_support_path=_required_string(
            value,
            "decoy_support_path",
            "F3-A decoy support path",
        ),
        decoy_support_content=_required_string(
            value,
            "decoy_support_content",
            "F3-A decoy support content",
        ),
        implemented_label=_load_label(value, "implemented_label", "F3-A"),
        linkage_audit_label=_load_label(value, "linkage_audit_label", "F3-A"),
        implementation_issue=_load_issue(value, "implementation_issue", "F3-A"),
        implementation_pr=_load_pr(value, "implementation_pr", "F3-A"),
        decoy_pr=_load_pr(value, "decoy_pr", "F3-A"),
    )


def load_f3_b_spec(value: Mapping[str, Any]) -> github_f3_b_spec:
    _require_schema(value, "F3-B")
    return github_f3_b_spec(
        fixture_id="github_workspace_f3_b",
        release_status_policy_path=_required_string(
            value,
            "release_status_policy_path",
            "F3-B release-status policy path",
        ),
        release_status_policy_content=_required_string(
            value,
            "release_status_policy_content",
            "F3-B release-status policy content",
        ),
        target_fix_path=_required_string(value, "target_fix_path", "F3-B target fix path"),
        target_initial_content=_required_string(
            value,
            "target_initial_content",
            "F3-B target initial content",
        ),
        target_old_fix_content=_required_string(
            value,
            "target_old_fix_content",
            "F3-B old fix content",
        ),
        target_reverted_content=_required_string(
            value,
            "target_reverted_content",
            "F3-B reverted content",
        ),
        target_revised_fix_content=_required_string(
            value,
            "target_revised_fix_content",
            "F3-B revised fix content",
        ),
        release_blocker_label=_load_label(value, "release_blocker_label", "F3-B"),
        ready_label=_load_label(value, "ready_label", "F3-B"),
        blocked_label=_load_label(value, "blocked_label", "F3-B"),
        tracking_issue=_load_issue(value, "tracking_issue", "F3-B"),
        old_fix_pr=_load_pr(value, "old_fix_pr", "F3-B"),
        revert_pr=_load_pr(value, "revert_pr", "F3-B"),
        replacement_pr=_load_pr(value, "replacement_pr", "F3-B"),
    )


def _resolve_identity(
    client: github_controller_client,
    *,
    repository_name: str,
    expected_repository_full_name: str,
    expected_repository_id: int,
    expected_default_branch: str,
    fixture_base_files: tuple[github_fixture_base_file, ...],
    label: str,
) -> github_repository_identity:
    identity = client.resolve_repository(repository_name)
    if identity.full_name != expected_repository_full_name or identity.repository_id != expected_repository_id:
        raise github_controller_error(f"{label} fixture target does not match the pinned repository.")
    if identity.default_branch != expected_default_branch:
        raise github_controller_error(
            f"{label} fixture requires default branch '{expected_default_branch}', got '{identity.default_branch}'."
        )
    client.ref(identity.owner, identity.name, f"heads/{identity.default_branch}")
    for item in fixture_base_files:
        actual = client.read_text_file(identity.owner, identity.name, item.path, ref=identity.default_branch)
        if actual != item.content:
            raise github_controller_error(
                f"Trusted fixture base file '{item.path}' does not match package-owned seed content."
            )
    return identity


def _ensure_label(
    client: github_controller_client,
    identity: github_repository_identity,
    spec: github_f3_label_spec,
    label: str,
) -> None:
    labels = tuple(client.list_labels(identity.owner, identity.name))
    match = next((item for item in labels if item.get("name") == spec.name), None)
    if match is None:
        value = client.create_label(
            identity.owner,
            identity.name,
            label=spec.name,
            color=spec.color,
            description=spec.description,
        )
    elif _label_matches(match, spec):
        return
    else:
        value = client.update_label(
            identity.owner,
            identity.name,
            spec.name,
            new_name=spec.name,
            color=spec.color,
            description=spec.description,
        )
    if not _label_matches(value, spec):
        raise github_controller_error(f"Label '{spec.name}' could not be converged to the {label} fixture definition.")


def _label_matches(value: Mapping[str, Any], spec: github_f3_label_spec) -> bool:
    return (
        value.get("name") == spec.name
        and str(value.get("color", "")).lower() == spec.color.lower()
        and value.get("description") == spec.description
    )


def _create_or_update_branch_file(
    client: github_controller_client,
    identity: github_repository_identity,
    path: str,
    *,
    message: str,
    content: str,
    branch: str,
    label: str,
) -> Mapping[str, Any]:
    existing = client.contents_optional(
        identity.owner,
        identity.name,
        path,
        ref=branch,
    )
    sha: str | None = None
    if existing is not None:
        sha = _required_string(existing, "sha", f"{label} existing file SHA")
    return client.create_or_update_file(
        identity.owner,
        identity.name,
        path,
        message=message,
        content=content,
        branch=branch,
        sha=sha,
    )


def _ensure_file(
    client: github_controller_client,
    identity: github_repository_identity,
    path: str,
    content: str,
    message: str,
    label: str,
) -> None:
    existing = client.contents_optional(
        identity.owner,
        identity.name,
        path,
        ref=identity.default_branch,
    )
    if existing is None:
        client.create_or_update_file(
            identity.owner,
            identity.name,
            path,
            message=message,
            content=content,
            branch=identity.default_branch,
        )
        return
    _verify_file(client, identity, path, content, label)


def _verify_file(
    client: github_controller_client,
    identity: github_repository_identity,
    path: str,
    content: str,
    label: str,
    *,
    ref: str | None = None,
) -> None:
    resolved_ref = ref or identity.default_branch
    actual = client.read_text_file(
        identity.owner,
        identity.name,
        path,
        ref=resolved_ref,
    )
    if actual != content:
        raise github_controller_error(
            f"{label} fixture file '{path}' at ref '{resolved_ref}' does not match "
            "package-owned content."
        )


def _head_sha(client: github_controller_client, identity: github_repository_identity) -> str:
    return _nested_string(
        client.ref(identity.owner, identity.name, f"heads/{identity.default_branch}"),
        "object",
        "sha",
        label="F3",
    )


def _discovery(objects: Mapping[str, Mapping[str, Any] | None]) -> dict[str, Any]:
    present_names = tuple(sorted(key for key, value in objects.items() if value is not None))
    return {
        "present": bool(present_names),
        "complete": len(present_names) == len(objects),
        "present_names": present_names,
        "missing_names": tuple(sorted(set(objects) - set(present_names))),
        **objects,
    }


def _discover_with_retry(
    client: github_controller_client,
    discover_once,
    identity: github_repository_identity,
    *,
    label: str,
    report: Callable[[apparatus_action_progress], None] | None,
    total: int,
    require_complete: bool,
    delays: tuple[float, ...],
) -> dict[str, Any]:
    latest = discover_once(identity)
    if latest["complete"]:
        return latest
    if not require_complete and not latest["present"]:
        return latest
    for attempt, delay in enumerate(delays[1:], start=1):
        _emit(
            report,
            2,
            total,
            f"GitHub list views are incomplete; retrying {label} discovery ({attempt}/{len(delays) - 1})",
        )
        if delay:
            client.wait_for_poll(
                max(2.0, float(delay)),
                "issue.list",
                "pull_request.list",
            )
        latest = discover_once(identity)
        if latest["complete"]:
            return latest
    raise github_controller_error(
        f"{label} fixture is only partially materialized; present="
        + ",".join(latest["present_names"])
        + "; missing="
        + ",".join(latest["missing_names"])
    )


def _load_label(value: Mapping[str, Any], key: str, label: str) -> github_f3_label_spec:
    item = _require_mapping(value, key, f"{label} {key}")
    return github_f3_label_spec(
        name=_required_string(item, "name", f"{label} {key}.name"),
        color=_required_string(item, "color", f"{label} {key}.color"),
        description=_required_string(item, "description", f"{label} {key}.description"),
    )


def _load_issue(value: Mapping[str, Any], key: str, label: str) -> github_f3_issue_spec:
    item = _require_mapping(value, key, f"{label} {key}")
    return github_f3_issue_spec(
        title=_required_string(item, "title", f"{label} {key}.title"),
        marker=_required_string(item, "marker", f"{label} {key}.marker"),
        body=_required_string(item, "body", f"{label} {key}.body"),
    )


def _load_pr(value: Mapping[str, Any], key: str, label: str) -> github_f3_pr_spec:
    item = _require_mapping(value, key, f"{label} {key}")
    return github_f3_pr_spec(
        title=_required_string(item, "title", f"{label} {key}.title"),
        marker=_required_string(item, "marker", f"{label} {key}.marker"),
        branch=_required_string(item, "branch", f"{label} {key}.branch"),
    )


def _require_schema(value: Mapping[str, Any], label: str) -> None:
    if value.get("schema_version") != "0.1":
        raise ValueError(f"{label} fixture schema_version must be '0.1'.")


def _marker_body(marker: str, body: str) -> str:
    return f"<!-- {marker} -->\n\n{body.rstrip()}\n"


def _find_marker(
    values: tuple[Mapping[str, Any], ...],
    marker: str,
    label: str,
) -> Mapping[str, Any] | None:
    needle = f"<!-- {marker} -->"
    matches = [
        item
        for item in values
        if isinstance(item.get("body"), str) and needle in str(item.get("body"))
    ]
    if len(matches) > 1:
        raise github_controller_error(f"{label} fixture marker '{marker}' is duplicated.")
    return matches[0] if matches else None


def _label_names(issue: Mapping[str, Any]) -> list[str]:
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return []
    values: list[str] = []
    for item in labels:
        if isinstance(item, Mapping) and isinstance(item.get("name"), str):
            values.append(str(item["name"]))
        elif isinstance(item, str):
            values.append(item)
    return sorted(values)


def _require_mapping(value: Mapping[str, Any], key: str, label: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise github_controller_error(f"{label} is missing or invalid.")
    return item


def _required_int(value: Mapping[str, Any], key: str, label: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise github_controller_error(f"{label} is missing or invalid.")
    return item


def _required_string(value: Mapping[str, Any], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise github_controller_error(f"{label} is missing or invalid.")
    return item


def _nested_string(
    value: Mapping[str, Any],
    *keys: str,
    label: str,
) -> str:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            raise github_controller_error(f"{label} GitHub response is missing required nested data.")
        current = current.get(key)
    if not isinstance(current, str) or not current:
        raise github_controller_error(f"{label} GitHub response is missing required nested data.")
    return current


def _emit(
    report: Callable[[apparatus_action_progress], None] | None,
    step: int,
    total: int,
    message: str,
) -> None:
    if report is not None:
        report(apparatus_action_progress(step=step, total=total, message=message))
