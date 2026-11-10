from __future__ import annotations

from dataclasses import dataclass
import json
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
class github_f1_b_blocker_spec:
    issue_title: str
    issue_marker: str
    fix_branch: str
    fix_path: str
    fix_content: str
    pr_title: str
    pr_marker: str


@dataclass(frozen=True)
class github_f1_b_spec:
    fixture_id: str
    release_branch: str
    candidate_path: str
    candidate_version: str
    release_pr_title: str
    release_pr_marker: str
    milestone_title: str
    milestone_marker: str
    blocker_label_name: str
    blocker_label_color: str
    blocker_label_description: str
    included: github_f1_b_blocker_spec
    missing: github_f1_b_blocker_spec
    noise_issue_title: str
    noise_issue_marker: str
    workflow_path: str
    workflow_content: str
    workflow_name: str
    workflow_input_key: str
    workflow_input_value: str


class github_f1_b_materializer:
    description = "Materialize or verify the engineering-reference F1-B world."
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
        spec: github_f1_b_spec,
    ) -> None:
        self._client = client
        self._repository_name = repository_name
        self._expected_repository_full_name = expected_repository_full_name
        self._expected_repository_id = expected_repository_id
        self._expected_default_branch = expected_default_branch
        self._fixture_base_files = tuple(fixture_base_files)
        self._spec = spec
        self._discovery_retry_delays = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)
        self._workflow_retry_delays = (
            0.0,
            1.0,
            2.0,
            4.0,
            8.0,
            15.0,
            20.0,
            30.0,
            30.0,
        )

    def run(self) -> apparatus_action_result:
        return self._run(None)

    def inspect(self):
        identity = self._resolve_identity()
        discovered = self._discover_with_retry(
            identity, report=None, total=12, require_complete=True
        )
        if not discovered.get("complete"):
            raise github_controller_error("F1-B fixture is not fully materialized.")
        observations = self._verify_static(identity, discovered)
        run, _changed = self._ensure_required_check(
            identity,
            observations,
            report=None,
            total=12,
            allow_dispatch=False,
        )
        return identity, self._verify(identity, discovered, observations, run)

    def run_with_progress(
        self,
        report: Callable[[apparatus_action_progress], None],
    ) -> apparatus_action_result:
        return self._run(report)

    def _run(
        self,
        report: Callable[[apparatus_action_progress], None] | None,
    ) -> apparatus_action_result:
        total = 12
        _emit(report, 1, total, "verifying pinned repository identity and trusted fixture base")
        identity = self._resolve_identity()

        _emit(report, 2, total, "discovering existing F1-B fixture markers")
        discovered = self._discover_with_retry(identity, report=report, total=total)
        changed = False
        if discovered["present"]:
            _emit_existing_fixture_skips(report, total)
            observations = self._verify_static(identity, discovered)
        else:
            observations = self._materialize(identity, report=report, total=total)
            changed = True
            discovered = self._direct_discovery(identity, observations)
            observations = self._verify_static(identity, discovered)

        run, check_changed = self._ensure_required_check(
            identity,
            observations,
            report=report,
            total=total,
            allow_dispatch=True,
        )
        changed = changed or check_changed

        _emit(report, 11, total, "verifying authoritative F1-B release topology and check state")
        observations = self._verify(identity, discovered, observations, run)
        _emit(report, 12, total, "F1-B fixture verification complete")
        return apparatus_action_result(
            changed=changed,
            detail=(
                "materialized trusted F1-B release-candidate fixture"
                if changed
                else "F1-B trusted fixture already exists and matches package-owned state"
            ),
            observations=observations,
        )

    def _resolve_identity(self) -> github_repository_identity:
        identity = self._client.resolve_repository(self._repository_name)
        if (
            identity.full_name != self._expected_repository_full_name
            or identity.repository_id != self._expected_repository_id
        ):
            raise github_controller_error(
                "F1-B fixture target does not match the pinned experimental repository."
            )
        if identity.default_branch != self._expected_default_branch:
            raise github_controller_error(
                f"F1-B fixture requires default branch '{self._expected_default_branch}', "
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
                    f"Trusted fixture base file '{item.path}' does not match "
                    "package-owned seed content."
                )
        return identity

    def _discover_once(self, identity: github_repository_identity) -> dict[str, Any]:
        issues = tuple(
            item
            for item in self._client.list_issues(identity.owner, identity.name)
            if "pull_request" not in item
        )
        pulls = self._client.list_pull_requests(identity.owner, identity.name)
        objects = {
            "included_issue": _find_marker(issues, self._spec.included.issue_marker),
            "included_pr": _find_marker(pulls, self._spec.included.pr_marker),
            "missing_issue": _find_marker(issues, self._spec.missing.issue_marker),
            "missing_pr": _find_marker(pulls, self._spec.missing.pr_marker),
            "release_pr": _find_marker(pulls, self._spec.release_pr_marker),
            "noise_issue": _find_marker(issues, self._spec.noise_issue_marker),
        }
        present_names = tuple(sorted(key for key, value in objects.items() if value is not None))
        missing_names = tuple(sorted(set(objects) - set(present_names)))
        return {
            "present": bool(present_names),
            "complete": len(present_names) == len(objects),
            "present_names": present_names,
            "missing_names": missing_names,
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
                (
                    "GitHub list views are temporarily incomplete; retrying F1-B "
                    f"fixture discovery ({attempt}/{len(delays) - 1})"
                ),
            )
            if delay > 0:
                time.sleep(delay)
            latest = self._discover_once(identity)
            if latest["complete"]:
                return latest

        raise github_controller_error(
            "F1-B fixture is only partially materialized after bounded discovery retries; "
            "present="
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
        main = identity.default_branch

        _emit(report, 3, total, "establishing release label, milestone, and required-check workflow")
        self._ensure_blocker_label(identity)
        milestone = self._ensure_milestone(identity)
        milestone_number = _required_int(milestone, "number", "F1-B release milestone number")
        self._ensure_workflow_file(identity)

        _emit(report, 4, total, "creating the blocker whose fix will be included in the candidate")
        included_issue = self._client.create_issue(
            owner,
            repo,
            title=self._spec.included.issue_title,
            body=_blocker_issue_body(self._spec.included),
            labels=(self._spec.blocker_label_name,),
            milestone=milestone_number,
        )
        included_issue_number = _required_int(
            included_issue,
            "number",
            "F1-B included blocker issue number",
        )

        _emit(report, 5, total, "creating and merging the included blocker fix")
        included_base = _nested_string(
            self._client.ref(owner, repo, f"heads/{main}"),
            "object",
            "sha",
        )
        self._client.create_ref(owner, repo, self._spec.included.fix_branch, included_base)
        included_fix = self._client.create_or_update_file(
            owner,
            repo,
            self._spec.included.fix_path,
            message="F1-B: implement included release blocker fix",
            content=self._spec.included.fix_content,
            branch=self._spec.included.fix_branch,
        )
        included_fix_commit = _nested_string(included_fix, "commit", "sha")
        included_pr = self._client.create_pull_request(
            owner,
            repo,
            title=self._spec.included.pr_title,
            head=self._spec.included.fix_branch,
            base=main,
            body=_fix_pr_body(self._spec.included, included_issue_number),
        )
        included_pr_number = _required_int(
            included_pr,
            "number",
            "F1-B included blocker fix PR number",
        )
        included_merge = self._client.merge_pull_request(
            owner,
            repo,
            included_pr_number,
            commit_title="F1-B: merge included release blocker fix",
        )
        if included_merge.get("merged") is not True:
            raise github_controller_error("GitHub did not merge the F1-B included blocker fix PR.")
        included_merge_commit = _required_string(
            included_merge,
            "sha",
            "F1-B included blocker merge commit",
        )

        _emit(report, 6, total, "creating the release candidate branch and open release pull request")
        release_base = _nested_string(
            self._client.ref(owner, repo, f"heads/{main}"),
            "object",
            "sha",
        )
        self._client.create_ref(owner, repo, self._spec.release_branch, release_base)
        candidate = self._client.create_or_update_file(
            owner,
            repo,
            self._spec.candidate_path,
            message="F1-B: prepare release candidate metadata",
            content=_candidate_text(self._spec.candidate_version),
            branch=self._spec.release_branch,
        )
        candidate_head = _nested_string(candidate, "commit", "sha")
        release_pr = self._client.create_pull_request(
            owner,
            repo,
            title=self._spec.release_pr_title,
            head=self._spec.release_branch,
            base=main,
            body=_release_pr_body(self._spec, milestone_number),
        )
        release_pr_number = _required_int(
            release_pr,
            "number",
            "F1-B release PR number",
        )

        _emit(report, 7, total, "creating and merging the blocker fix that remains absent from the candidate")
        missing_issue = self._client.create_issue(
            owner,
            repo,
            title=self._spec.missing.issue_title,
            body=_blocker_issue_body(self._spec.missing),
            labels=(self._spec.blocker_label_name,),
            milestone=milestone_number,
        )
        missing_issue_number = _required_int(
            missing_issue,
            "number",
            "F1-B missing blocker issue number",
        )
        missing_base = _nested_string(
            self._client.ref(owner, repo, f"heads/{main}"),
            "object",
            "sha",
        )
        self._client.create_ref(owner, repo, self._spec.missing.fix_branch, missing_base)
        missing_fix = self._client.create_or_update_file(
            owner,
            repo,
            self._spec.missing.fix_path,
            message="F1-B: implement missing release blocker fix",
            content=self._spec.missing.fix_content,
            branch=self._spec.missing.fix_branch,
        )
        missing_fix_commit = _nested_string(missing_fix, "commit", "sha")
        missing_pr = self._client.create_pull_request(
            owner,
            repo,
            title=self._spec.missing.pr_title,
            head=self._spec.missing.fix_branch,
            base=main,
            body=_fix_pr_body(self._spec.missing, missing_issue_number),
        )
        missing_pr_number = _required_int(
            missing_pr,
            "number",
            "F1-B missing blocker fix PR number",
        )
        missing_merge = self._client.merge_pull_request(
            owner,
            repo,
            missing_pr_number,
            commit_title="F1-B: merge missing release blocker fix to default branch",
        )
        if missing_merge.get("merged") is not True:
            raise github_controller_error("GitHub did not merge the F1-B missing blocker fix PR.")
        missing_merge_commit = _required_string(
            missing_merge,
            "sha",
            "F1-B missing blocker merge commit",
        )

        _emit(report, 8, total, "closing both blocker issues while preserving their release requirement")
        self._client.update_issue(
            owner,
            repo,
            included_issue_number,
            {
                "body": _blocker_issue_body(
                    self._spec.included,
                    pull_number=included_pr_number,
                    fix_commit=included_fix_commit,
                ),
                "state": "closed",
                "labels": [self._spec.blocker_label_name],
                "milestone": milestone_number,
            },
        )
        self._client.update_issue(
            owner,
            repo,
            missing_issue_number,
            {
                "body": _blocker_issue_body(
                    self._spec.missing,
                    pull_number=missing_pr_number,
                    fix_commit=missing_fix_commit,
                ),
                "state": "closed",
                "labels": [self._spec.blocker_label_name],
                "milestone": milestone_number,
            },
        )

        _emit(report, 9, total, "creating unrelated milestone issue noise")
        noise_issue = self._client.create_issue(
            owner,
            repo,
            title=self._spec.noise_issue_title,
            body=_marker_body(
                self._spec.noise_issue_marker,
                "Release-note wording cleanup for the same milestone; this is not a release blocker.",
            ),
            milestone=milestone_number,
        )
        noise_issue_number = _required_int(
            noise_issue,
            "number",
            "F1-B noise issue number",
        )

        return {
            "milestone_number": milestone_number,
            "included_issue_number": included_issue_number,
            "included_pr_number": included_pr_number,
            "included_fix_commit": included_fix_commit,
            "included_merge_commit": included_merge_commit,
            "release_pr_number": release_pr_number,
            "candidate_head": candidate_head,
            "missing_issue_number": missing_issue_number,
            "missing_pr_number": missing_pr_number,
            "missing_fix_commit": missing_fix_commit,
            "missing_merge_commit": missing_merge_commit,
            "noise_issue_number": noise_issue_number,
        }

    def _direct_discovery(
        self,
        identity: github_repository_identity,
        observations: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "present": True,
            "complete": True,
            "present_names": (
                "included_issue",
                "included_pr",
                "missing_issue",
                "missing_pr",
                "noise_issue",
                "release_pr",
            ),
            "missing_names": (),
            "included_issue": self._client.issue(
                identity.owner,
                identity.name,
                int(observations["included_issue_number"]),
            ),
            "included_pr": self._client.pull_request(
                identity.owner,
                identity.name,
                int(observations["included_pr_number"]),
            ),
            "missing_issue": self._client.issue(
                identity.owner,
                identity.name,
                int(observations["missing_issue_number"]),
            ),
            "missing_pr": self._client.pull_request(
                identity.owner,
                identity.name,
                int(observations["missing_pr_number"]),
            ),
            "release_pr": self._client.pull_request(
                identity.owner,
                identity.name,
                int(observations["release_pr_number"]),
            ),
            "noise_issue": self._client.issue(
                identity.owner,
                identity.name,
                int(observations["noise_issue_number"]),
            ),
        }

    def _verify_static(
        self,
        identity: github_repository_identity,
        discovered: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not discovered.get("complete"):
            raise github_controller_error("F1-B fixture is not fully materialized.")

        included_issue_number = _required_int(
            discovered["included_issue"],
            "number",
            "F1-B included blocker issue number",
        )
        included_pr_number = _required_int(
            discovered["included_pr"],
            "number",
            "F1-B included blocker PR number",
        )
        missing_issue_number = _required_int(
            discovered["missing_issue"],
            "number",
            "F1-B missing blocker issue number",
        )
        missing_pr_number = _required_int(
            discovered["missing_pr"],
            "number",
            "F1-B missing blocker PR number",
        )
        release_pr_number = _required_int(
            discovered["release_pr"],
            "number",
            "F1-B release PR number",
        )
        noise_issue_number = _required_int(
            discovered["noise_issue"],
            "number",
            "F1-B noise issue number",
        )

        included_issue = self._client.issue(identity.owner, identity.name, included_issue_number)
        included_pr = self._client.pull_request(identity.owner, identity.name, included_pr_number)
        missing_issue = self._client.issue(identity.owner, identity.name, missing_issue_number)
        missing_pr = self._client.pull_request(identity.owner, identity.name, missing_pr_number)
        release_pr = self._client.pull_request(identity.owner, identity.name, release_pr_number)
        noise_issue = self._client.issue(identity.owner, identity.name, noise_issue_number)

        milestone = self._find_milestone(identity)
        milestone_number = _required_int(milestone, "number", "F1-B release milestone number")
        self._verify_label(identity)
        self._verify_workflow_file(identity)

        included_fix_commit = _nested_string(included_pr, "head", "sha")
        missing_fix_commit = _nested_string(missing_pr, "head", "sha")
        included_merge_commit = _required_string(
            included_pr,
            "merge_commit_sha",
            "F1-B included blocker merge commit",
        )
        missing_merge_commit = _required_string(
            missing_pr,
            "merge_commit_sha",
            "F1-B missing blocker merge commit",
        )
        candidate_head = _nested_string(release_pr, "head", "sha")

        self._verify_issue(
            included_issue,
            self._spec.included,
            milestone_number,
            included_pr_number,
            included_fix_commit,
        )
        self._verify_issue(
            missing_issue,
            self._spec.missing,
            milestone_number,
            missing_pr_number,
            missing_fix_commit,
        )
        self._verify_fix_pr(
            included_pr,
            self._spec.included,
            included_issue_number,
            identity.default_branch,
        )
        self._verify_fix_pr(
            missing_pr,
            self._spec.missing,
            missing_issue_number,
            identity.default_branch,
        )

        if noise_issue.get("title") != self._spec.noise_issue_title:
            raise github_controller_error("F1-B noise issue title does not match fixture spec.")
        if noise_issue.get("body") != _marker_body(
            self._spec.noise_issue_marker,
            "Release-note wording cleanup for the same milestone; this is not a release blocker.",
        ):
            raise github_controller_error("F1-B noise issue body does not match fixture spec.")
        if noise_issue.get("state") != "open":
            raise github_controller_error("F1-B noise issue is not open.")
        if _label_names(noise_issue):
            raise github_controller_error("F1-B noise issue unexpectedly has labels.")
        if _milestone_number(noise_issue) != milestone_number:
            raise github_controller_error("F1-B noise issue is not attached to the release milestone.")

        if release_pr.get("title") != self._spec.release_pr_title:
            raise github_controller_error("F1-B release PR title does not match fixture spec.")
        if release_pr.get("body") != _release_pr_body(self._spec, milestone_number):
            raise github_controller_error("F1-B release PR body does not match fixture spec.")
        if release_pr.get("state") != "open":
            raise github_controller_error("F1-B release PR is not open.")
        if bool(release_pr.get("draft", False)):
            raise github_controller_error("F1-B release PR is unexpectedly draft.")
        if release_pr.get("merged") is True or release_pr.get("merged_at") is not None:
            raise github_controller_error("F1-B release PR is unexpectedly merged.")
        if _nested_string(release_pr, "head", "ref") != self._spec.release_branch:
            raise github_controller_error("F1-B release PR head branch does not match fixture spec.")
        if _nested_string(release_pr, "base", "ref") != identity.default_branch:
            raise github_controller_error("F1-B release PR base branch does not match fixture spec.")

        candidate_text = self._client.read_text_file(
            identity.owner,
            identity.name,
            self._spec.candidate_path,
            ref=self._spec.release_branch,
        )
        if candidate_text != _candidate_text(self._spec.candidate_version):
            raise github_controller_error("F1-B candidate metadata does not match fixture spec.")
        included_text = self._client.read_text_file(
            identity.owner,
            identity.name,
            self._spec.included.fix_path,
            ref=self._spec.release_branch,
        )
        if included_text != self._spec.included.fix_content:
            raise github_controller_error("F1-B candidate does not contain the included blocker fix.")
        if self._client.contents_optional(
            identity.owner,
            identity.name,
            self._spec.missing.fix_path,
            ref=self._spec.release_branch,
        ) is not None:
            raise github_controller_error("F1-B candidate unexpectedly contains the missing blocker fix.")
        main_missing = self._client.read_text_file(
            identity.owner,
            identity.name,
            self._spec.missing.fix_path,
            ref=identity.default_branch,
        )
        if main_missing != self._spec.missing.fix_content:
            raise github_controller_error("F1-B default branch does not contain the missing blocker fix.")

        history = self._client.list_commits(
            identity.owner,
            identity.name,
            sha=self._spec.release_branch,
            per_page=100,
        )
        history_shas = {
            str(item.get("sha"))
            for item in history
            if isinstance(item.get("sha"), str)
        }
        if included_fix_commit not in history_shas:
            raise github_controller_error("F1-B included blocker fix is not in candidate history.")
        if missing_fix_commit in history_shas:
            raise github_controller_error("F1-B missing blocker fix is unexpectedly in candidate history.")

        return {
            "fixture_id": self._spec.fixture_id,
            "repository": identity.full_name,
            "default_branch": identity.default_branch,
            "release_branch": self._spec.release_branch,
            "release_milestone": self._spec.milestone_title,
            "milestone_number": milestone_number,
            "release_pr_number": release_pr_number,
            "candidate_head": candidate_head,
            "included_issue_number": included_issue_number,
            "included_pr_number": included_pr_number,
            "included_fix_commit": included_fix_commit,
            "included_merge_commit": included_merge_commit,
            "missing_issue_number": missing_issue_number,
            "missing_pr_number": missing_pr_number,
            "missing_fix_commit": missing_fix_commit,
            "missing_merge_commit": missing_merge_commit,
            "noise_issue_number": noise_issue_number,
        }

    def _ensure_required_check(
        self,
        identity: github_repository_identity,
        observations: Mapping[str, Any],
        *,
        report: Callable[[apparatus_action_progress], None] | None,
        total: int,
        allow_dispatch: bool,
    ) -> tuple[Mapping[str, Any], bool]:
        _emit(report, 10, total, "verifying deterministic passing required checks on the candidate head")
        workflow = self._find_workflow_with_retry(identity)
        workflow_id = workflow.get("id")
        if not isinstance(workflow_id, int):
            raise github_controller_error("F1-B workflow does not expose a numeric workflow ID.")
        candidate_head = str(observations["candidate_head"])
        existing = self._matching_workflow_run(identity, workflow_id, candidate_head)
        if existing is not None:
            completed = self._wait_for_workflow_run(identity, existing, report=report, total=total)
            if completed.get("conclusion") != "success":
                raise github_controller_error(
                    "F1-B required-check workflow exists for the candidate head but did not succeed."
                )
            return completed, False

        if not allow_dispatch:
            raise github_controller_error(
                "F1-B required-check workflow has no run for the candidate head."
            )

        _emit(report, 10, total, "dispatching deterministic required-check workflow for the candidate")
        dispatched = self._client.dispatch_workflow(
            identity.owner,
            identity.name,
            workflow_id,
            ref=self._spec.release_branch,
            inputs={self._spec.workflow_input_key: self._spec.workflow_input_value},
        )
        run_id = dispatched.get("workflow_run_id")
        run: Mapping[str, Any] | None = None
        if isinstance(run_id, int):
            run = self._client.workflow_run(identity.owner, identity.name, run_id)
        if run is None:
            for attempt, delay in enumerate(self._workflow_retry_delays[1:], start=1):
                if delay > 0:
                    time.sleep(delay)
                run = self._matching_workflow_run(identity, workflow_id, candidate_head)
                if run is not None:
                    break
                _emit(
                    report,
                    10,
                    total,
                    (
                        "waiting for dispatched required-check run to become visible "
                        f"({attempt}/{len(self._workflow_retry_delays) - 1})"
                    ),
                )
        if run is None:
            raise github_controller_error(
                "F1-B dispatched required-check workflow did not become visible."
            )
        completed = self._wait_for_workflow_run(identity, run, report=report, total=total)
        if completed.get("conclusion") != "success":
            raise github_controller_error(
                "F1-B required-check workflow did not complete successfully."
            )
        return completed, True

    def _matching_workflow_run(
        self,
        identity: github_repository_identity,
        workflow_id: int,
        candidate_head: str,
    ) -> Mapping[str, Any] | None:
        value = self._client.list_workflow_runs_for_workflow(
            identity.owner,
            identity.name,
            workflow_id,
            branch=self._spec.release_branch,
            event="workflow_dispatch",
            per_page=100,
        )
        runs = value.get("workflow_runs")
        if not isinstance(runs, list):
            raise github_controller_error("F1-B workflow-runs response is malformed.")
        matches = [
            item
            for item in runs
            if isinstance(item, Mapping)
            and item.get("head_sha") == candidate_head
            and item.get("head_branch") == self._spec.release_branch
        ]
        if not matches:
            return None
        return dict(matches[0])

    def _wait_for_workflow_run(
        self,
        identity: github_repository_identity,
        run: Mapping[str, Any],
        *,
        report: Callable[[apparatus_action_progress], None] | None,
        total: int,
    ) -> Mapping[str, Any]:
        run_id = run.get("id")
        if not isinstance(run_id, int):
            raise github_controller_error("F1-B workflow run does not expose a numeric ID.")
        current = dict(run)
        for attempt, delay in enumerate(self._workflow_retry_delays):
            if current.get("status") == "completed":
                return current
            if delay > 0:
                time.sleep(delay)
            _emit(
                report,
                10,
                total,
                (
                    "waiting for required-check workflow completion "
                    f"({attempt + 1}/{len(self._workflow_retry_delays)})"
                ),
            )
            current = dict(
                self._client.workflow_run(identity.owner, identity.name, run_id)
            )
            if current.get("status") == "completed":
                return current
        raise github_controller_error("F1-B required-check workflow did not complete in time.")

    def _verify(
        self,
        identity: github_repository_identity,
        discovered: Mapping[str, Any],
        observations: Mapping[str, Any],
        workflow_run: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del discovered
        if workflow_run.get("status") != "completed":
            raise github_controller_error("F1-B required-check workflow is not completed.")
        if workflow_run.get("conclusion") != "success":
            raise github_controller_error("F1-B required-check workflow is not successful.")
        if workflow_run.get("head_sha") != observations["candidate_head"]:
            raise github_controller_error("F1-B required-check run does not belong to candidate head.")
        if workflow_run.get("head_branch") != self._spec.release_branch:
            raise github_controller_error("F1-B required-check run does not belong to release branch.")
        if workflow_run.get("event") != "workflow_dispatch":
            raise github_controller_error("F1-B required-check run has an unexpected trigger event.")
        value = dict(observations)
        value.update(
            {
                "required_workflow_name": self._spec.workflow_name,
                "required_workflow_run_id": workflow_run.get("id"),
                "required_workflow_status": workflow_run.get("status"),
                "required_workflow_conclusion": workflow_run.get("conclusion"),
            }
        )
        return value

    def _ensure_blocker_label(self, identity: github_repository_identity) -> None:
        labels = self._client.list_labels(identity.owner, identity.name)
        matches = [
            item for item in labels if item.get("name") == self._spec.blocker_label_name
        ]
        if not matches:
            self._client.create_label(
                identity.owner,
                identity.name,
                label=self._spec.blocker_label_name,
                color=self._spec.blocker_label_color,
                description=self._spec.blocker_label_description,
            )
            return
        if len(matches) != 1:
            raise github_controller_error("F1-B blocker label is duplicated.")
        item = matches[0]
        if str(item.get("color", "")).lower() != self._spec.blocker_label_color.lower():
            raise github_controller_error("F1-B blocker label color does not match fixture spec.")
        if item.get("description") != self._spec.blocker_label_description:
            raise github_controller_error("F1-B blocker label description does not match fixture spec.")

    def _verify_label(self, identity: github_repository_identity) -> None:
        labels = self._client.list_labels(identity.owner, identity.name)
        matches = [
            item for item in labels if item.get("name") == self._spec.blocker_label_name
        ]
        if len(matches) != 1:
            raise github_controller_error(
                "F1-B blocker label is missing or duplicated."
            )
        item = matches[0]
        if str(item.get("color", "")).lower() != self._spec.blocker_label_color.lower():
            raise github_controller_error("F1-B blocker label color does not match fixture spec.")
        if item.get("description") != self._spec.blocker_label_description:
            raise github_controller_error("F1-B blocker label description does not match fixture spec.")

    def _ensure_milestone(self, identity: github_repository_identity) -> Mapping[str, Any]:
        matches = [
            item
            for item in self._client.list_milestones(identity.owner, identity.name)
            if item.get("title") == self._spec.milestone_title
        ]
        expected_description = _marker_body(
            self._spec.milestone_marker,
            "Release milestone used by the ACMM F1-B release-candidate fixture.",
        )
        if not matches:
            return self._client.create_milestone(
                identity.owner,
                identity.name,
                title=self._spec.milestone_title,
                description=expected_description,
            )
        if len(matches) != 1:
            raise github_controller_error("F1-B release milestone is duplicated.")
        milestone = matches[0]
        if milestone.get("description") != expected_description:
            raise github_controller_error("F1-B release milestone description does not match fixture spec.")
        if milestone.get("state") != "open":
            raise github_controller_error("F1-B release milestone is not open.")
        return milestone

    def _find_milestone(self, identity: github_repository_identity) -> Mapping[str, Any]:
        matches = [
            item
            for item in self._client.list_milestones(identity.owner, identity.name)
            if item.get("title") == self._spec.milestone_title
        ]
        if len(matches) != 1:
            raise github_controller_error(
                "F1-B release milestone is missing or duplicated."
            )
        milestone = matches[0]
        expected_description = _marker_body(
            self._spec.milestone_marker,
            "Release milestone used by the ACMM F1-B release-candidate fixture.",
        )
        if milestone.get("description") != expected_description:
            raise github_controller_error(
                "F1-B release milestone description does not match fixture spec."
            )
        if milestone.get("state") != "open":
            raise github_controller_error("F1-B release milestone is not open.")
        return milestone

    def _ensure_workflow_file(self, identity: github_repository_identity) -> None:
        existing = self._client.contents_optional(
            identity.owner,
            identity.name,
            self._spec.workflow_path,
            ref=identity.default_branch,
        )
        expected = self._spec.workflow_content
        if existing is None:
            self._client.create_or_update_file(
                identity.owner,
                identity.name,
                self._spec.workflow_path,
                message="F1-B: add deterministic required release checks",
                content=expected,
                branch=identity.default_branch,
            )
            return
        actual = self._client.read_text_file(
            identity.owner,
            identity.name,
            self._spec.workflow_path,
            ref=identity.default_branch,
        )
        if actual != expected:
            raise github_controller_error("F1-B required-check workflow file does not match fixture spec.")

    def _verify_workflow_file(self, identity: github_repository_identity) -> None:
        actual = self._client.read_text_file(
            identity.owner,
            identity.name,
            self._spec.workflow_path,
            ref=identity.default_branch,
        )
        if actual != self._spec.workflow_content:
            raise github_controller_error("F1-B required-check workflow file does not match fixture spec.")

    def _find_workflow_with_retry(self, identity: github_repository_identity) -> Mapping[str, Any]:
        delays = self._discovery_retry_delays
        for attempt, delay in enumerate(delays):
            value = self._client.list_workflows(identity.owner, identity.name)
            workflows = value.get("workflows")
            if not isinstance(workflows, list):
                raise github_controller_error("F1-B workflow catalog response is malformed.")
            matches = [
                item
                for item in workflows
                if isinstance(item, Mapping)
                and item.get("path") == self._spec.workflow_path
                and item.get("name") == self._spec.workflow_name
            ]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise github_controller_error("F1-B required-check workflow is duplicated.")
            if attempt + 1 < len(delays) and delay > 0:
                time.sleep(delay)
        raise github_controller_error("F1-B required-check workflow is not visible to Actions.")

    def _verify_issue(
        self,
        issue: Mapping[str, Any],
        blocker: github_f1_b_blocker_spec,
        milestone_number: int,
        pull_number: int,
        fix_commit: str,
    ) -> None:
        if issue.get("title") != blocker.issue_title:
            raise github_controller_error("F1-B blocker issue title does not match fixture spec.")
        if issue.get("body") != _blocker_issue_body(
            blocker,
            pull_number=pull_number,
            fix_commit=fix_commit,
        ):
            raise github_controller_error("F1-B blocker issue body does not match fixture spec.")
        if issue.get("state") != "closed":
            raise github_controller_error("F1-B blocker issue is not closed.")
        if _label_names(issue) != [self._spec.blocker_label_name]:
            raise github_controller_error("F1-B blocker issue labels do not match fixture spec.")
        if _milestone_number(issue) != milestone_number:
            raise github_controller_error("F1-B blocker issue milestone does not match fixture spec.")

    def _verify_fix_pr(
        self,
        pull: Mapping[str, Any],
        blocker: github_f1_b_blocker_spec,
        issue_number: int,
        default_branch: str,
    ) -> None:
        if pull.get("title") != blocker.pr_title:
            raise github_controller_error("F1-B blocker fix PR title does not match fixture spec.")
        if pull.get("body") != _fix_pr_body(blocker, issue_number):
            raise github_controller_error("F1-B blocker fix PR body does not match fixture spec.")
        if pull.get("merged") is not True and pull.get("merged_at") is None:
            raise github_controller_error("F1-B blocker fix PR is not merged.")
        if _nested_string(pull, "head", "ref") != blocker.fix_branch:
            raise github_controller_error("F1-B blocker fix PR head branch does not match fixture spec.")
        if _nested_string(pull, "base", "ref") != default_branch:
            raise github_controller_error("F1-B blocker fix PR base branch does not match fixture spec.")


def load_f1_b_spec(value: Mapping[str, Any], *, workflow_content: str) -> github_f1_b_spec:
    if value.get("schema_version") != "0.1":
        raise ValueError("F1-B fixture schema_version must be '0.1'.")
    included = _load_blocker(value.get("included_blocker"), "included_blocker")
    missing = _load_blocker(value.get("missing_blocker"), "missing_blocker")
    release_pr = _object(value, "release_pr")
    milestone = _object(value, "release_milestone")
    label = _object(value, "blocker_label")
    noise = _object(value, "noise_issue")
    workflow = _object(value, "required_workflow")
    return github_f1_b_spec(
        fixture_id=_required_string(value, "fixture_id", "F1-B fixture_id"),
        release_branch=_required_string(value, "release_branch", "F1-B release_branch"),
        candidate_path=_required_string(value, "candidate_path", "F1-B candidate_path"),
        candidate_version=_required_string(value, "candidate_version", "F1-B candidate_version"),
        release_pr_title=_required_string(release_pr, "title", "F1-B release PR title"),
        release_pr_marker=_required_string(release_pr, "marker", "F1-B release PR marker"),
        milestone_title=_required_string(milestone, "title", "F1-B milestone title"),
        milestone_marker=_required_string(milestone, "marker", "F1-B milestone marker"),
        blocker_label_name=_required_string(label, "name", "F1-B blocker label name"),
        blocker_label_color=_required_string(label, "color", "F1-B blocker label color"),
        blocker_label_description=_required_string(
            label,
            "description",
            "F1-B blocker label description",
        ),
        included=included,
        missing=missing,
        noise_issue_title=_required_string(noise, "title", "F1-B noise issue title"),
        noise_issue_marker=_required_string(noise, "marker", "F1-B noise issue marker"),
        workflow_path=_required_string(workflow, "path", "F1-B workflow path"),
        workflow_content=workflow_content.replace("\r\n", "\n"),
        workflow_name=_required_string(workflow, "name", "F1-B workflow name"),
        workflow_input_key=_required_string(
            workflow,
            "dispatch_input_key",
            "F1-B workflow input key",
        ),
        workflow_input_value=_required_string(
            workflow,
            "dispatch_input_value",
            "F1-B workflow input value",
        ),
    )


def _load_blocker(value: Any, label: str) -> github_f1_b_blocker_spec:
    if not isinstance(value, Mapping):
        raise ValueError(f"F1-B {label} must be an object.")
    return github_f1_b_blocker_spec(
        issue_title=_required_string(value, "issue_title", f"F1-B {label} issue title"),
        issue_marker=_required_string(value, "issue_marker", f"F1-B {label} issue marker"),
        fix_branch=_required_string(value, "fix_branch", f"F1-B {label} fix branch"),
        fix_path=_required_string(value, "fix_path", f"F1-B {label} fix path"),
        fix_content=_required_string(value, "fix_content", f"F1-B {label} fix content"),
        pr_title=_required_string(value, "pr_title", f"F1-B {label} PR title"),
        pr_marker=_required_string(value, "pr_marker", f"F1-B {label} PR marker"),
    )


def _object(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"F1-B fixture field '{key}' must be an object.")
    return item


def _candidate_text(version: str) -> str:
    return json.dumps(
        {"release_candidate": version},
        indent=2,
        sort_keys=True,
    ) + "\n"


def _blocker_issue_body(
    blocker: github_f1_b_blocker_spec,
    *,
    pull_number: int | None = None,
    fix_commit: str | None = None,
) -> str:
    details = "This issue is a required release blocker for the assigned milestone."
    if pull_number is not None and fix_commit is not None:
        details += f"\n\nRequired fix: pull request #{pull_number}, commit `{fix_commit}`."
    return _marker_body(blocker.issue_marker, details)


def _fix_pr_body(blocker: github_f1_b_blocker_spec, issue_number: int) -> str:
    return _marker_body(
        blocker.pr_marker,
        f"Implements the required release-blocker fix tracked by issue #{issue_number}.",
    )


def _release_pr_body(spec: github_f1_b_spec, milestone_number: int) -> str:
    return _marker_body(
        spec.release_pr_marker,
        (
            f"Release candidate `{spec.candidate_version}` from `{spec.release_branch}`.\n\n"
            f"Release milestone: #{milestone_number}."
        ),
    )


def _marker_body(marker: str, body: str) -> str:
    return f"<!-- {marker} -->\n\n{body}\n"


def _find_marker(
    values: tuple[Mapping[str, Any], ...],
    marker: str,
) -> Mapping[str, Any] | None:
    needle = f"<!-- {marker} -->"
    matches = [
        item
        for item in values
        if isinstance(item.get("body"), str) and needle in str(item.get("body"))
    ]
    if len(matches) > 1:
        raise github_controller_error(f"F1-B fixture marker '{marker}' is duplicated.")
    return matches[0] if matches else None


def _label_names(issue: Mapping[str, Any]) -> list[str]:
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return []
    names = []
    for item in labels:
        if isinstance(item, Mapping) and isinstance(item.get("name"), str):
            names.append(str(item["name"]))
        elif isinstance(item, str):
            names.append(item)
    return sorted(names)


def _milestone_number(issue: Mapping[str, Any]) -> int | None:
    milestone = issue.get("milestone")
    if not isinstance(milestone, Mapping):
        return None
    number = milestone.get("number")
    return int(number) if isinstance(number, int) else None


def _required_int(value: Mapping[str, Any], key: str, label: str) -> int:
    item = value.get(key)
    if not isinstance(item, int):
        raise github_controller_error(f"{label} is missing or invalid.")
    return item


def _required_string(value: Mapping[str, Any], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise github_controller_error(f"{label} is missing or invalid.")
    return item


def _nested_string(value: Mapping[str, Any], *keys: str) -> str:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            raise github_controller_error(
                "F1-B GitHub response is missing required nested string data."
            )
        current = current.get(key)
    if not isinstance(current, str) or not current:
        raise github_controller_error(
            "F1-B GitHub response is missing required nested string data."
        )
    return current


def _emit_existing_fixture_skips(
    report: Callable[[apparatus_action_progress], None] | None,
    total: int,
) -> None:
    messages = {
        3: "release label, milestone, and required-check workflow",
        4: "included blocker issue",
        5: "included blocker fix and merge",
        6: "release candidate branch and open release pull request",
        7: "missing blocker fix merged only to the default branch",
        8: "closed blocker lifecycle state",
        9: "unrelated milestone issue noise",
    }
    for step, label in messages.items():
        _emit(report, step, total, f"skipped (already intact): {label}")


def _emit(
    report: Callable[[apparatus_action_progress], None] | None,
    step: int,
    total: int,
    message: str,
) -> None:
    if report is not None:
        report(apparatus_action_progress(step=step, total=total, message=message))
