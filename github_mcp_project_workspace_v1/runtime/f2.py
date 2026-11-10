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
class github_label_spec:
    name: str
    color: str
    description: str


@dataclass(frozen=True)
class github_issue_seed_spec:
    title: str
    marker: str
    body: str


@dataclass(frozen=True)
class github_f2_a_spec:
    fixture_id: str
    triage_policy_path: str
    triage_policy_content: str
    csv_test_path: str
    csv_test_content: str
    duplicate_label: github_label_spec
    needs_triage_label: github_label_spec
    confirmed_bug_label: github_label_spec
    incoming_issue: github_issue_seed_spec
    canonical_issue: github_issue_seed_spec
    decoy_issue: github_issue_seed_spec


@dataclass(frozen=True)
class github_f2_b_spec:
    fixture_id: str
    triage_policy_path: str
    triage_policy_content: str
    ready_label: github_label_spec
    blocked_label: github_label_spec
    dependency_issue: github_issue_seed_spec
    work_item: github_issue_seed_spec
    noise_issue: github_issue_seed_spec
    dependency_fix_branch: str
    dependency_fix_path: str
    dependency_fix_content: str
    dependency_pr_title: str
    dependency_pr_marker: str


class github_f2_a_materializer:
    description = "Materialize or verify the engineering-reference F2-A world."
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
        spec: github_f2_a_spec,
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
            identity, report=None, total=7, require_complete=True
        )
        if not discovered.get("complete"):
            raise github_controller_error("F2-A fixture is not fully materialized.")
        return identity, self._verify(identity, discovered)

    def _run(
        self,
        report: Callable[[apparatus_action_progress], None] | None,
    ) -> apparatus_action_result:
        total = 7
        _emit(report, 1, total, "verifying repository identity and trusted fixture base")
        identity = self._resolve_identity()
        _emit(report, 2, total, "discovering existing F2-A issue markers")
        discovered = self._discover_with_retry(identity, report=report, total=total)
        changed = False
        if not discovered["present"]:
            observations = self._materialize(identity, report=report, total=total)
            changed = True
            discovered = self._direct_discovery(identity, observations)
        else:
            _emit(report, 3, total, "skipped (already intact): F2-A labels and policy files")
            _emit(report, 4, total, "skipped (already intact): canonical regression issue")
            _emit(report, 5, total, "skipped (already intact): decoy regression issue")
            _emit(report, 6, total, "skipped (already intact): incoming regression issue")
        observations = self._verify(identity, discovered)
        _emit(report, 7, total, "F2-A fixture verification complete")
        return apparatus_action_result(
            changed=changed,
            detail=(
                "materialized trusted F2-A incoming-regression triage fixture"
                if changed
                else "F2-A trusted fixture already exists and matches package-owned state"
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
            label="F2-A",
        )

    def _discover_once(self, identity: github_repository_identity) -> dict[str, Any]:
        issues = tuple(
            item
            for item in self._client.list_issues(identity.owner, identity.name)
            if "pull_request" not in item
        )
        objects = {
            "incoming_issue": _find_marker(issues, self._spec.incoming_issue.marker, "F2-A"),
            "canonical_issue": _find_marker(issues, self._spec.canonical_issue.marker, "F2-A"),
            "decoy_issue": _find_marker(issues, self._spec.decoy_issue.marker, "F2-A"),
        }
        present_names = tuple(sorted(key for key, value in objects.items() if value is not None))
        return {
            "present": bool(present_names),
            "complete": len(present_names) == len(objects),
            "present_names": present_names,
            "missing_names": tuple(sorted(set(objects) - set(present_names))),
            **objects,
        }

    def _discover_with_retry(
        self,
        identity: github_repository_identity,
        *,
        report: Callable[[apparatus_action_progress], None] | None,
        total: int,
        require_complete: bool = False,
    ) -> dict[str, Any]:
        latest = self._discover_once(identity)
        if latest["complete"]:
            return latest
        if not require_complete and not latest["present"]:
            return latest
        delays = self._discovery_retry_delays
        for attempt, delay in enumerate(delays[1:], start=1):
            _emit(
                report,
                2,
                total,
                f"GitHub list views are incomplete; retrying F2-A discovery "
                f"({attempt}/{len(delays) - 1})",
            )
            if delay:
                time.sleep(delay)
            latest = self._discover_once(identity)
            if latest["complete"]:
                return latest
        raise github_controller_error(
            "F2-A fixture is only partially materialized; present="
            + ",".join(latest["present_names"])
            + "; missing="
            + ",".join(latest["missing_names"])
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

        _emit(report, 3, total, "seeding F2-A labels, triage policy, and CSV evidence")
        for label in (
            self._spec.duplicate_label,
            self._spec.needs_triage_label,
            self._spec.confirmed_bug_label,
        ):
            _ensure_label(self._client, identity, label)
        _ensure_file(
            self._client,
            identity,
            self._spec.triage_policy_path,
            self._spec.triage_policy_content,
            "F2-A: add repository triage policy",
        )
        _ensure_file(
            self._client,
            identity,
            self._spec.csv_test_path,
            self._spec.csv_test_content,
            "F2-A: add CSV regression examples",
        )

        _emit(report, 4, total, "creating the established canonical regression issue")
        canonical = self._client.create_issue(
            owner,
            repo,
            title=self._spec.canonical_issue.title,
            body=_marker_body(self._spec.canonical_issue.marker, self._spec.canonical_issue.body),
            labels=(self._spec.confirmed_bug_label.name,),
        )
        canonical_number = _required_int(canonical, "number", "F2-A canonical issue number")

        _emit(report, 5, total, "creating the semantically nearby decoy issue")
        decoy = self._client.create_issue(
            owner,
            repo,
            title=self._spec.decoy_issue.title,
            body=_marker_body(self._spec.decoy_issue.marker, self._spec.decoy_issue.body),
            labels=(self._spec.confirmed_bug_label.name,),
        )
        decoy_number = _required_int(decoy, "number", "F2-A decoy issue number")

        _emit(report, 6, total, "creating the incoming issue awaiting triage")
        incoming = self._client.create_issue(
            owner,
            repo,
            title=self._spec.incoming_issue.title,
            body=_marker_body(self._spec.incoming_issue.marker, self._spec.incoming_issue.body),
            labels=(self._spec.needs_triage_label.name,),
        )
        incoming_number = _required_int(incoming, "number", "F2-A incoming issue number")
        return {
            "incoming_issue_number": incoming_number,
            "canonical_issue_number": canonical_number,
            "decoy_issue_number": decoy_number,
            "default_branch": branch,
        }

    def _direct_discovery(
        self,
        identity: github_repository_identity,
        observations: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "present": True,
            "complete": True,
            "present_names": ("canonical_issue", "decoy_issue", "incoming_issue"),
            "missing_names": (),
            "incoming_issue": self._client.issue(
                identity.owner, identity.name, int(observations["incoming_issue_number"])
            ),
            "canonical_issue": self._client.issue(
                identity.owner, identity.name, int(observations["canonical_issue_number"])
            ),
            "decoy_issue": self._client.issue(
                identity.owner, identity.name, int(observations["decoy_issue_number"])
            ),
        }

    def _verify(
        self,
        identity: github_repository_identity,
        discovered: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not discovered.get("complete"):
            raise github_controller_error("F2-A fixture is incomplete.")
        incoming = _require_mapping(discovered, "incoming_issue", "F2-A incoming issue")
        canonical = _require_mapping(discovered, "canonical_issue", "F2-A canonical issue")
        decoy = _require_mapping(discovered, "decoy_issue", "F2-A decoy issue")
        if incoming.get("state") != "open":
            raise github_controller_error("F2-A incoming issue must begin open.")
        if _label_names(incoming) != [self._spec.needs_triage_label.name]:
            raise github_controller_error("F2-A incoming issue labels do not match the pristine fixture.")
        for issue, expected in (
            (canonical, self._spec.canonical_issue),
            (decoy, self._spec.decoy_issue),
        ):
            if issue.get("state") != "open" or self._spec.confirmed_bug_label.name not in _label_names(issue):
                raise github_controller_error(f"F2-A issue '{expected.title}' is not in the expected state.")
        if self._client.issue_comments(
            identity.owner, identity.name, _required_int(incoming, "number", "F2-A incoming issue")
        ):
            raise github_controller_error("F2-A incoming issue must not have a seeded disposition comment.")
        _verify_file(self._client, identity, self._spec.triage_policy_path, self._spec.triage_policy_content)
        _verify_file(self._client, identity, self._spec.csv_test_path, self._spec.csv_test_content)
        return {
            "incoming_issue_number": _required_int(incoming, "number", "F2-A incoming issue number"),
            "canonical_issue_number": _required_int(canonical, "number", "F2-A canonical issue number"),
            "decoy_issue_number": _required_int(decoy, "number", "F2-A decoy issue number"),
            "default_branch": identity.default_branch,
        }


class github_f2_b_materializer:
    description = "Materialize or verify the engineering-reference F2-B world."
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
        spec: github_f2_b_spec,
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
            identity, report=None, total=8, require_complete=True
        )
        if not discovered.get("complete"):
            raise github_controller_error("F2-B fixture is not fully materialized.")
        return identity, self._verify(identity, discovered)

    def _run(
        self,
        report: Callable[[apparatus_action_progress], None] | None,
    ) -> apparatus_action_result:
        total = 8
        _emit(report, 1, total, "verifying repository identity and trusted fixture base")
        identity = self._resolve_identity()
        _emit(report, 2, total, "discovering existing F2-B fixture markers")
        discovered = self._discover_with_retry(identity, report=report, total=total)
        changed = False
        if not discovered["present"]:
            observations = self._materialize(identity, report=report, total=total)
            changed = True
            discovered = self._direct_discovery(identity, observations)
        else:
            for step, label in (
                (3, "F2-B labels and maintenance policy"),
                (4, "dependency issue and blocked work item"),
                (5, "historical blocked comment"),
                (6, "dependency implementation and merged PR"),
                (7, "aligned ready-state maintenance and noise issue"),
            ):
                _emit(report, step, total, f"skipped (already intact): {label}")
        observations = self._verify(identity, discovered)
        _emit(report, 8, total, "F2-B fixture verification complete")
        return apparatus_action_result(
            changed=changed,
            detail=(
                "materialized trusted F2-B stale-work-item maintenance fixture"
                if changed
                else "F2-B trusted fixture already exists and matches package-owned state"
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
            label="F2-B",
        )

    def _discover_once(self, identity: github_repository_identity) -> dict[str, Any]:
        issues = tuple(
            item
            for item in self._client.list_issues(identity.owner, identity.name)
            if "pull_request" not in item
        )
        pulls = self._client.list_pull_requests(identity.owner, identity.name)
        objects = {
            "dependency_issue": _find_marker(issues, self._spec.dependency_issue.marker, "F2-B"),
            "work_item": _find_marker(issues, self._spec.work_item.marker, "F2-B"),
            "noise_issue": _find_marker(issues, self._spec.noise_issue.marker, "F2-B"),
            "dependency_pr": _find_marker(pulls, self._spec.dependency_pr_marker, "F2-B"),
        }
        present_names = tuple(sorted(key for key, value in objects.items() if value is not None))
        return {
            "present": bool(present_names),
            "complete": len(present_names) == len(objects),
            "present_names": present_names,
            "missing_names": tuple(sorted(set(objects) - set(present_names))),
            **objects,
        }

    def _discover_with_retry(
        self,
        identity: github_repository_identity,
        *,
        report: Callable[[apparatus_action_progress], None] | None,
        total: int,
        require_complete: bool = False,
    ) -> dict[str, Any]:
        latest = self._discover_once(identity)
        if latest["complete"]:
            return latest
        if not require_complete and not latest["present"]:
            return latest
        delays = self._discovery_retry_delays
        for attempt, delay in enumerate(delays[1:], start=1):
            _emit(
                report,
                2,
                total,
                f"GitHub list views are incomplete; retrying F2-B discovery "
                f"({attempt}/{len(delays) - 1})",
            )
            if delay:
                time.sleep(delay)
            latest = self._discover_once(identity)
            if latest["complete"]:
                return latest
        raise github_controller_error(
            "F2-B fixture is only partially materialized; present="
            + ",".join(latest["present_names"])
            + "; missing="
            + ",".join(latest["missing_names"])
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

        _emit(report, 3, total, "seeding F2-B labels and repository maintenance policy")
        for label in (self._spec.ready_label, self._spec.blocked_label):
            _ensure_label(self._client, identity, label)
        _ensure_file(
            self._client,
            identity,
            self._spec.triage_policy_path,
            self._spec.triage_policy_content,
            "F2-B: add work-item maintenance policy",
        )

        _emit(report, 4, total, "creating dependency issue and initially blocked work item")
        dependency = self._client.create_issue(
            owner,
            repo,
            title=self._spec.dependency_issue.title,
            body=_marker_body(self._spec.dependency_issue.marker, self._spec.dependency_issue.body),
        )
        dependency_number = _required_int(dependency, "number", "F2-B dependency issue number")
        work_item = self._client.create_issue(
            owner,
            repo,
            title=self._spec.work_item.title,
            body=_marker_body(self._spec.work_item.marker, self._spec.work_item.body),
            labels=(self._spec.blocked_label.name,),
        )
        work_item_number = _required_int(work_item, "number", "F2-B work item number")

        _emit(report, 5, total, "recording historical blocked-state audit context")
        old_comment = self._client.create_issue_comment(
            owner,
            repo,
            work_item_number,
            f"Blocked until dependency issue #{dependency_number} is implemented and lands on `{branch}`.",
        )
        old_comment_id = _required_int(old_comment, "id", "F2-B historical comment id")

        _emit(report, 6, total, "creating and merging the dependency implementation")
        base_sha = _nested_string(
            self._client.ref(owner, repo, f"heads/{branch}"),
            "object",
            "sha",
        )
        self._client.create_ref(owner, repo, self._spec.dependency_fix_branch, base_sha)
        fix_result = self._client.create_or_update_file(
            owner,
            repo,
            self._spec.dependency_fix_path,
            message="F2-B: implement blocking dependency",
            content=self._spec.dependency_fix_content,
            branch=self._spec.dependency_fix_branch,
        )
        fix_commit = _nested_string(fix_result, "commit", "sha")
        dependency_pr = self._client.create_pull_request(
            owner,
            repo,
            title=self._spec.dependency_pr_title,
            head=self._spec.dependency_fix_branch,
            base=branch,
            body=_marker_body(
                self._spec.dependency_pr_marker,
                f"Implements the dependency tracked by issue #{dependency_number}.",
            ),
        )
        dependency_pr_number = _required_int(
            dependency_pr,
            "number",
            "F2-B dependency PR number",
        )
        merged = self._client.merge_pull_request(
            owner,
            repo,
            dependency_pr_number,
            commit_title="F2-B: merge blocking dependency",
        )
        if merged.get("merged") is not True:
            raise github_controller_error("GitHub did not merge the F2-B dependency PR.")
        merge_commit = _required_string(merged, "sha", "F2-B dependency merge commit")

        _emit(report, 7, total, "aligning current work-item status and seeding a blocked decoy")
        self._client.update_issue(owner, repo, dependency_number, {"state": "closed"})
        self._client.update_issue(
            owner,
            repo,
            work_item_number,
            {"labels": [self._spec.ready_label.name]},
        )
        ready_comment = self._client.create_issue_comment(
            owner,
            repo,
            work_item_number,
            (
                f"Dependency #{dependency_number} landed via pull request #{dependency_pr_number}; "
                "current status is ready and the historical blocked note remains for audit context."
            ),
        )
        ready_comment_id = _required_int(ready_comment, "id", "F2-B ready comment id")
        noise = self._client.create_issue(
            owner,
            repo,
            title=self._spec.noise_issue.title,
            body=_marker_body(self._spec.noise_issue.marker, self._spec.noise_issue.body),
            labels=(self._spec.blocked_label.name,),
        )
        noise_number = _required_int(noise, "number", "F2-B noise issue number")
        return {
            "work_item_number": work_item_number,
            "dependency_issue_number": dependency_number,
            "dependency_pr_number": dependency_pr_number,
            "noise_issue_number": noise_number,
            "dependency_fix_commit": fix_commit,
            "dependency_merge_commit": merge_commit,
            "historical_comment_id": old_comment_id,
            "ready_comment_id": ready_comment_id,
        }

    def _direct_discovery(
        self,
        identity: github_repository_identity,
        observations: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "present": True,
            "complete": True,
            "present_names": ("dependency_issue", "dependency_pr", "noise_issue", "work_item"),
            "missing_names": (),
            "dependency_issue": self._client.issue(
                identity.owner, identity.name, int(observations["dependency_issue_number"])
            ),
            "work_item": self._client.issue(
                identity.owner, identity.name, int(observations["work_item_number"])
            ),
            "noise_issue": self._client.issue(
                identity.owner, identity.name, int(observations["noise_issue_number"])
            ),
            "dependency_pr": self._client.pull_request(
                identity.owner, identity.name, int(observations["dependency_pr_number"])
            ),
            "observations": dict(observations),
        }

    def _verify(
        self,
        identity: github_repository_identity,
        discovered: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not discovered.get("complete"):
            raise github_controller_error("F2-B fixture is incomplete.")
        dependency = _require_mapping(discovered, "dependency_issue", "F2-B dependency issue")
        work_item = _require_mapping(discovered, "work_item", "F2-B work item")
        noise = _require_mapping(discovered, "noise_issue", "F2-B noise issue")
        dependency_pr = _require_mapping(discovered, "dependency_pr", "F2-B dependency PR")
        dependency_number = _required_int(dependency, "number", "F2-B dependency issue number")
        work_item_number = _required_int(work_item, "number", "F2-B work item number")
        dependency_pr_number = _required_int(dependency_pr, "number", "F2-B dependency PR number")
        if dependency.get("state") != "closed":
            raise github_controller_error("F2-B dependency issue must be closed.")
        if work_item.get("state") != "open" or _label_names(work_item) != [self._spec.ready_label.name]:
            raise github_controller_error("F2-B work item current labels/state are not aligned.")
        if self._spec.blocked_label.name not in _label_names(noise):
            raise github_controller_error("F2-B blocked-label decoy issue is missing.")
        full_pr = self._client.pull_request(identity.owner, identity.name, dependency_pr_number)
        if full_pr.get("merged") is not True:
            raise github_controller_error("F2-B dependency pull request must be merged.")
        comments = tuple(self._client.issue_comments(identity.owner, identity.name, work_item_number))
        if len(comments) != 2:
            raise github_controller_error("F2-B work item must contain exactly two seeded audit comments.")
        bodies = [str(item.get("body", "")) for item in comments]
        if not any(f"#{dependency_number}" in body and "Blocked" in body for body in bodies):
            raise github_controller_error("F2-B historical blocked comment is missing.")
        if not any(f"#{dependency_number}" in body and f"#{dependency_pr_number}" in body for body in bodies):
            raise github_controller_error("F2-B current ready-state comment is missing.")
        _verify_file(self._client, identity, self._spec.triage_policy_path, self._spec.triage_policy_content)
        commits = self._client.list_commits(identity.owner, identity.name, sha=identity.default_branch)
        commit_shas = {item.get("sha") for item in commits if isinstance(item.get("sha"), str)}
        observations = discovered.get("observations")
        fix_commit = (
            observations.get("dependency_fix_commit")
            if isinstance(observations, Mapping)
            else None
        )
        merge_commit = (
            observations.get("dependency_merge_commit")
            if isinstance(observations, Mapping)
            else None
        )
        if not isinstance(fix_commit, str) or not fix_commit:
            fix_commit = _dependency_fix_commit_from_pr(
                self._client,
                identity,
                dependency_pr,
                self._spec.dependency_fix_path,
            )
        if fix_commit not in commit_shas:
            raise github_controller_error("F2-B dependency fix commit is not present on the default branch.")
        if not isinstance(merge_commit, str) or not merge_commit:
            merge_commit = _optional_string(full_pr, "merge_commit_sha")
        if not isinstance(merge_commit, str) or not merge_commit:
            raise github_controller_error("F2-B dependency merge commit is unavailable.")
        comment_ids = sorted(
            int(item["id"])
            for item in comments
            if isinstance(item.get("id"), int)
        )
        return {
            "work_item_number": work_item_number,
            "dependency_issue_number": dependency_number,
            "dependency_pr_number": dependency_pr_number,
            "noise_issue_number": _required_int(noise, "number", "F2-B noise issue number"),
            "dependency_fix_commit": fix_commit,
            "dependency_merge_commit": merge_commit,
            "historical_comment_id": comment_ids[0],
            "ready_comment_id": comment_ids[-1],
        }


def load_f2_a_spec(value: Mapping[str, Any]) -> github_f2_a_spec:
    _require_schema(value, "F2-A")
    return github_f2_a_spec(
        fixture_id="github_workspace_f2_a",
        triage_policy_path=_required_string(value, "triage_policy_path", "F2-A triage policy path"),
        triage_policy_content=_required_string(value, "triage_policy_content", "F2-A triage policy content"),
        csv_test_path=_required_string(value, "csv_test_path", "F2-A CSV test path"),
        csv_test_content=_required_string(value, "csv_test_content", "F2-A CSV test content"),
        duplicate_label=_load_label(value, "duplicate_label", "F2-A"),
        needs_triage_label=_load_label(value, "needs_triage_label", "F2-A"),
        confirmed_bug_label=_load_label(value, "confirmed_bug_label", "F2-A"),
        incoming_issue=_load_issue_seed(value, "incoming_issue", "F2-A"),
        canonical_issue=_load_issue_seed(value, "canonical_issue", "F2-A"),
        decoy_issue=_load_issue_seed(value, "decoy_issue", "F2-A"),
    )


def load_f2_b_spec(value: Mapping[str, Any]) -> github_f2_b_spec:
    _require_schema(value, "F2-B")
    fix = _require_mapping(value, "dependency_fix", "F2-B dependency_fix")
    pr = _require_mapping(value, "dependency_pr", "F2-B dependency_pr")
    return github_f2_b_spec(
        fixture_id="github_workspace_f2_b",
        triage_policy_path=_required_string(value, "triage_policy_path", "F2-B triage policy path"),
        triage_policy_content=_required_string(value, "triage_policy_content", "F2-B triage policy content"),
        ready_label=_load_label(value, "ready_label", "F2-B"),
        blocked_label=_load_label(value, "blocked_label", "F2-B"),
        dependency_issue=_load_issue_seed(value, "dependency_issue", "F2-B"),
        work_item=_load_issue_seed(value, "work_item", "F2-B"),
        noise_issue=_load_issue_seed(value, "noise_issue", "F2-B"),
        dependency_fix_branch=_required_string(fix, "branch", "F2-B dependency fix branch"),
        dependency_fix_path=_required_string(fix, "path", "F2-B dependency fix path"),
        dependency_fix_content=_required_string(fix, "content", "F2-B dependency fix content"),
        dependency_pr_title=_required_string(pr, "title", "F2-B dependency PR title"),
        dependency_pr_marker=_required_string(pr, "marker", "F2-B dependency PR marker"),
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
    spec: github_label_spec,
) -> None:
    labels = tuple(client.list_labels(identity.owner, identity.name))
    match = next((item for item in labels if item.get("name") == spec.name), None)
    if match is None:
        created = client.create_label(
            identity.owner,
            identity.name,
            label=spec.name,
            color=spec.color,
            description=spec.description,
        )
        _require_label_definition(created, spec)
        return
    if _label_matches(match, spec):
        return

    # Newly created GitHub repositories may already contain platform-default labels
    # such as ``duplicate``.  A same-name default is ambient repository state, not
    # evidence of a partially materialized ACMM fixture.  Converge it to the
    # package-owned definition before any subject receives access to the repository.
    updated = client.update_label(
        identity.owner,
        identity.name,
        spec.name,
        new_name=spec.name,
        color=spec.color,
        description=spec.description,
    )
    _require_label_definition(updated, spec)


def _label_matches(value: Mapping[str, Any], spec: github_label_spec) -> bool:
    return (
        value.get("name") == spec.name
        and str(value.get("color", "")).lower() == spec.color.lower()
        and value.get("description") == spec.description
    )


def _require_label_definition(value: Mapping[str, Any], spec: github_label_spec) -> None:
    if not _label_matches(value, spec):
        raise github_controller_error(
            f"Label '{spec.name}' could not be converged to the F2 fixture definition."
        )


def _ensure_file(
    client: github_controller_client,
    identity: github_repository_identity,
    path: str,
    content: str,
    message: str,
) -> None:
    existing = client.contents_optional(identity.owner, identity.name, path, ref=identity.default_branch)
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
    _verify_file(client, identity, path, content)


def _verify_file(
    client: github_controller_client,
    identity: github_repository_identity,
    path: str,
    content: str,
) -> None:
    actual = client.read_text_file(identity.owner, identity.name, path, ref=identity.default_branch)
    if actual != content:
        raise github_controller_error(f"F2 fixture file '{path}' does not match package-owned content.")


def _dependency_fix_commit_from_pr(
    client: github_controller_client,
    identity: github_repository_identity,
    pull: Mapping[str, Any],
    path: str,
) -> str:
    head = pull.get("head")
    head_sha = head.get("sha") if isinstance(head, Mapping) else None
    if isinstance(head_sha, str) and head_sha:
        return head_sha
    commits = client.list_commits(identity.owner, identity.name, sha=identity.default_branch, path=path)
    if not commits:
        raise github_controller_error("F2-B cannot recover the dependency fix commit identity.")
    return _required_string(commits[0], "sha", "F2-B dependency fix commit")


def _load_label(value: Mapping[str, Any], key: str, label: str) -> github_label_spec:
    item = _require_mapping(value, key, f"{label} {key}")
    return github_label_spec(
        name=_required_string(item, "name", f"{label} {key}.name"),
        color=_required_string(item, "color", f"{label} {key}.color"),
        description=_required_string(item, "description", f"{label} {key}.description"),
    )


def _load_issue_seed(value: Mapping[str, Any], key: str, label: str) -> github_issue_seed_spec:
    item = _require_mapping(value, key, f"{label} {key}")
    return github_issue_seed_spec(
        title=_required_string(item, "title", f"{label} {key}.title"),
        marker=_required_string(item, "marker", f"{label} {key}.marker"),
        body=_required_string(item, "body", f"{label} {key}.body"),
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
    matches = [item for item in values if isinstance(item.get("body"), str) and needle in str(item.get("body"))]
    if len(matches) > 1:
        raise github_controller_error(f"{label} fixture marker '{marker}' is duplicated.")
    return matches[0] if matches else None


def _label_names(issue: Mapping[str, Any]) -> list[str]:
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return []
    result: list[str] = []
    for item in labels:
        if isinstance(item, Mapping) and isinstance(item.get("name"), str):
            result.append(str(item["name"]))
        elif isinstance(item, str):
            result.append(item)
    return sorted(result)


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


def _optional_string(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    return item if isinstance(item, str) and item else None


def _nested_string(value: Mapping[str, Any], *keys: str) -> str:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            raise github_controller_error("F2 GitHub response is missing required nested data.")
        current = current.get(key)
    if not isinstance(current, str) or not current:
        raise github_controller_error("F2 GitHub response is missing required nested data.")
    return current


def _emit(
    report: Callable[[apparatus_action_progress], None] | None,
    step: int,
    total: int,
    message: str,
) -> None:
    if report is not None:
        report(apparatus_action_progress(step=step, total=total, message=message))
