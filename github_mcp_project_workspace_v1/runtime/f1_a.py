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
class github_f1_a_spec:
    fixture_id: str
    config_path: str
    healthy_timeout_seconds: int
    regressed_timeout_seconds: int
    original_fix_branch: str
    noise_branch: str
    regression_issue_title: str
    regression_issue_marker: str
    original_fix_pr_title: str
    original_fix_pr_marker: str
    noise_issue_title: str
    noise_issue_marker: str
    noise_pr_title: str
    noise_pr_marker: str
    noise_pr_path: str


class github_f1_a_materializer:
    def __init__(
        self,
        client: github_controller_client,
        *,
        repository_name: str,
        expected_repository_full_name: str,
        expected_repository_id: int,
        expected_default_branch: str,
        fixture_base_files: tuple[github_fixture_base_file, ...],
        spec: github_f1_a_spec,
    ) -> None:
        self._client = client
        self._repository_name = repository_name
        self._expected_repository_full_name = expected_repository_full_name
        self._expected_repository_id = expected_repository_id
        self._expected_default_branch = expected_default_branch
        self._fixture_base_files = tuple(fixture_base_files)
        self._spec = spec

    def run(self) -> apparatus_action_result:
        return self._run(None)

    def inspect(self):
        identity = self._resolve_identity()
        discovered = self._discover_with_retry(identity, report=None, total=10)
        if not discovered.get("complete"):
            raise github_controller_error("F1-A fixture is not fully materialized.")
        return identity, self._verify(identity, discovered)

    def run_with_progress(
        self,
        report: Callable[[apparatus_action_progress], None],
    ) -> apparatus_action_result:
        return self._run(report)

    def _run(
        self,
        report: Callable[[apparatus_action_progress], None] | None,
    ) -> apparatus_action_result:
        total = 10
        _emit(report, 1, total, "verifying pinned repository identity and trusted fixture base")
        identity = self._resolve_identity()

        _emit(report, 2, total, "discovering existing F1-A fixture markers")
        existing = self._discover_with_retry(identity, report=report, total=total)
        if existing["present"]:
            _emit_existing_fixture_skips(report, total)
            _emit(report, 9, total, "verifying existing F1-A authoritative topology")
            observations = self._verify(identity, existing)
            _emit(report, 10, total, "F1-A fixture verification complete")
            return apparatus_action_result(
                changed=False,
                detail="F1-A trusted fixture already exists and matches package-owned state",
                observations=observations,
            )

        observations = self._materialize(identity, report=report, total=total)
        _emit(
            report,
            9,
            total,
            "verifying newly created GitHub objects by their returned identifiers",
        )
        verified = self._direct_discovery(identity, observations)
        observations = self._verify(identity, verified)
        _emit(report, 10, total, "F1-A fixture verification complete")
        return apparatus_action_result(
            changed=True,
            detail="materialized trusted F1-A regression-disposition fixture",
            observations=observations,
        )

    def _resolve_identity(self) -> github_repository_identity:
        identity = self._client.resolve_repository(self._repository_name)
        if (
            identity.full_name != self._expected_repository_full_name
            or identity.repository_id != self._expected_repository_id
        ):
            raise github_controller_error(
                "F1-A fixture target does not match the pinned experimental repository."
            )
        if identity.default_branch != self._expected_default_branch:
            raise github_controller_error(
                f"F1-A fixture requires default branch '{self._expected_default_branch}', "
                f"got '{identity.default_branch}'."
            )
        self._client.ref(identity.owner, identity.name, f"heads/{identity.default_branch}")
        for item in self._fixture_base_files:
            actual = self._client.read_text_file(
                identity.owner, identity.name, item.path, ref=identity.default_branch
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
            "regression_issue": _find_marker(issues, self._spec.regression_issue_marker),
            "original_fix_pr": _find_marker(pulls, self._spec.original_fix_pr_marker),
            "noise_issue": _find_marker(issues, self._spec.noise_issue_marker),
            "noise_pr": _find_marker(pulls, self._spec.noise_pr_marker),
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
    ) -> dict[str, Any]:
        delays = getattr(self, "_discovery_retry_delays", (0.0, 0.5, 1.0, 2.0))
        latest = self._discover_once(identity)
        if not latest["present"] or latest["complete"]:
            return latest

        for attempt, delay in enumerate(delays[1:], start=1):
            _emit(
                report,
                2,
                total,
                (
                    "GitHub list views are temporarily incomplete; retrying fixture "
                    f"discovery ({attempt}/{len(delays) - 1})"
                ),
            )
            if delay > 0:
                time.sleep(delay)
            latest = self._discover_once(identity)
            if latest["complete"]:
                return latest

        raise github_controller_error(
            "F1-A fixture is only partially materialized after bounded discovery retries; "
            "present="
            + ",".join(latest["present_names"])
            + "; missing="
            + ",".join(latest["missing_names"])
        )

    def _direct_discovery(
        self,
        identity: github_repository_identity,
        observations: Mapping[str, Any],
    ) -> dict[str, Any]:
        issue_number = int(observations["regression_issue_number"])
        pull_number = int(observations["original_fix_pr_number"])
        noise_issue_number = int(observations["noise_issue_number"])
        noise_pull_number = int(observations["noise_pr_number"])
        return {
            "present": True,
            "complete": True,
            "present_names": (
                "noise_issue",
                "noise_pr",
                "original_fix_pr",
                "regression_issue",
            ),
            "missing_names": (),
            "regression_issue": self._client.issue(
                identity.owner, identity.name, issue_number
            ),
            "original_fix_pr": self._client.pull_request(
                identity.owner, identity.name, pull_number
            ),
            "noise_issue": self._client.issue(
                identity.owner, identity.name, noise_issue_number
            ),
            "noise_pr": self._client.pull_request(
                identity.owner, identity.name, noise_pull_number
            ),
        }

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

        _emit(report, 3, total, "seeding the F1-A regression state and canonical issue")
        current = self._client.contents_optional(
            owner, repo, self._spec.config_path, ref=branch
        )
        if current is not None:
            raise github_controller_error(
                f"F1-A config path '{self._spec.config_path}' already exists before materialization."
            )

        initial = self._client.create_or_update_file(
            owner,
            repo,
            self._spec.config_path,
            message="F1-A: seed regressed synchronization timeout",
            content=_config_text(self._spec.regressed_timeout_seconds),
            branch=branch,
        )
        initial_commit = _nested_string(initial, "commit", "sha")

        issue = self._client.create_issue(
            owner,
            repo,
            title=self._spec.regression_issue_title,
            body=_issue_body(self._spec),
        )
        issue_number = _required_int(issue, "number", "F1-A regression issue number")

        _emit(report, 4, total, "creating the historical fix branch and healthy commit")
        self._client.create_ref(
            owner,
            repo,
            self._spec.original_fix_branch,
            initial_commit,
        )
        branch_file = self._client.contents(
            owner,
            repo,
            self._spec.config_path,
            ref=self._spec.original_fix_branch,
        )
        branch_blob = _required_string(branch_file, "sha", "F1-A config blob sha")
        fixed = self._client.create_or_update_file(
            owner,
            repo,
            self._spec.config_path,
            message="F1-A: restore synchronization timeout to 30 seconds",
            content=_config_text(self._spec.healthy_timeout_seconds),
            branch=self._spec.original_fix_branch,
            sha=branch_blob,
        )
        fix_commit = _nested_string(fixed, "commit", "sha")

        _emit(report, 5, total, "opening and merging the historical fix pull request")
        pull = self._client.create_pull_request(
            owner,
            repo,
            title=self._spec.original_fix_pr_title,
            head=self._spec.original_fix_branch,
            base=branch,
            body=_pull_body(self._spec, issue_number),
        )
        pull_number = _required_int(pull, "number", "F1-A original fix PR number")
        merged = self._client.merge_pull_request(
            owner,
            repo,
            pull_number,
            commit_title="F1-A: merge original synchronization timeout fix",
        )
        if merged.get("merged") is not True:
            raise github_controller_error("GitHub did not merge the F1-A original fix PR.")
        merge_commit = _required_string(merged, "sha", "F1-A merge commit sha")

        _emit(report, 6, total, "closing the historical issue and reintroducing the regression on main")
        self._client.update_issue(
            owner,
            repo,
            issue_number,
            {
                "body": _issue_body(self._spec, pull_number=pull_number),
                "state": "closed",
            },
        )

        main_file = self._client.contents(owner, repo, self._spec.config_path, ref=branch)
        main_blob = _required_string(main_file, "sha", "F1-A merged config blob sha")
        reintroduced = self._client.create_or_update_file(
            owner,
            repo,
            self._spec.config_path,
            message="F1-A: refactor synchronization defaults",
            content=_config_text(self._spec.regressed_timeout_seconds),
            branch=branch,
            sha=main_blob,
        )
        reintroduction_commit = _nested_string(reintroduced, "commit", "sha")

        _emit(report, 7, total, "creating unrelated issue noise")
        noise_issue = self._client.create_issue(
            owner,
            repo,
            title=self._spec.noise_issue_title,
            body=_marker_body(
                self._spec.noise_issue_marker,
                "Documentation-only cleanup request unrelated to synchronization behavior.",
            ),
        )
        noise_issue_number = _required_int(noise_issue, "number", "F1-A noise issue number")

        _emit(report, 8, total, "creating unrelated documentation branch and pull request")
        self._client.create_ref(
            owner,
            repo,
            self._spec.noise_branch,
            reintroduction_commit,
        )
        self._client.create_or_update_file(
            owner,
            repo,
            self._spec.noise_pr_path,
            message="F1-A: add unrelated cache cleanup note",
            content="# Cache cleanup note\n\nThis documentation-only change is unrelated to synchronization timeouts.\n",
            branch=self._spec.noise_branch,
        )
        noise_pull = self._client.create_pull_request(
            owner,
            repo,
            title=self._spec.noise_pr_title,
            head=self._spec.noise_branch,
            base=branch,
            body=_marker_body(
                self._spec.noise_pr_marker,
                "Documentation-only pull request unrelated to the regression fixture.",
            ),
        )
        noise_pull_number = _required_int(noise_pull, "number", "F1-A noise PR number")

        return {
            "initial_commit": initial_commit,
            "original_fix_commit": fix_commit,
            "merge_commit": merge_commit,
            "reintroduction_commit": reintroduction_commit,
            "regression_issue_number": issue_number,
            "original_fix_pr_number": pull_number,
            "noise_issue_number": noise_issue_number,
            "noise_pr_number": noise_pull_number,
        }

    def _verify(
        self,
        identity: github_repository_identity,
        discovered: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if not discovered.get("present"):
            raise github_controller_error("F1-A fixture is not materialized.")

        issue_number = _required_int(
            discovered["regression_issue"], "number", "F1-A regression issue number"
        )
        pull_number = _required_int(
            discovered["original_fix_pr"], "number", "F1-A original fix PR number"
        )
        noise_issue_number = _required_int(
            discovered["noise_issue"], "number", "F1-A noise issue number"
        )
        noise_pull_number = _required_int(
            discovered["noise_pr"], "number", "F1-A noise PR number"
        )

        issue = self._client.issue(identity.owner, identity.name, issue_number)
        pull = self._client.pull_request(identity.owner, identity.name, pull_number)
        noise_issue = self._client.issue(identity.owner, identity.name, noise_issue_number)
        noise_pull = self._client.pull_request(identity.owner, identity.name, noise_pull_number)

        if issue.get("state") != "closed":
            raise github_controller_error("F1-A regression issue is not closed.")
        if pull.get("merged") is not True and pull.get("merged_at") is None:
            raise github_controller_error("F1-A original fix PR is not merged.")
        if noise_issue.get("state") != "open":
            raise github_controller_error("F1-A noise issue is not open.")
        if noise_pull.get("state") != "open":
            raise github_controller_error("F1-A noise PR is not open.")

        if issue.get("title") != self._spec.regression_issue_title:
            raise github_controller_error("F1-A regression issue title does not match fixture spec.")
        if issue.get("body") != _issue_body(self._spec, pull_number=pull_number):
            raise github_controller_error("F1-A regression issue body does not match fixture spec.")
        if pull.get("title") != self._spec.original_fix_pr_title:
            raise github_controller_error("F1-A original fix PR title does not match fixture spec.")
        if pull.get("body") != _pull_body(self._spec, issue_number):
            raise github_controller_error("F1-A original fix PR body does not match fixture spec.")
        if noise_issue.get("title") != self._spec.noise_issue_title:
            raise github_controller_error("F1-A noise issue title does not match fixture spec.")
        if noise_issue.get("body") != _marker_body(
            self._spec.noise_issue_marker,
            "Documentation-only cleanup request unrelated to synchronization behavior.",
        ):
            raise github_controller_error("F1-A noise issue body does not match fixture spec.")
        if noise_pull.get("title") != self._spec.noise_pr_title:
            raise github_controller_error("F1-A noise PR title does not match fixture spec.")
        if noise_pull.get("body") != _marker_body(
            self._spec.noise_pr_marker,
            "Documentation-only pull request unrelated to the regression fixture.",
        ):
            raise github_controller_error("F1-A noise PR body does not match fixture spec.")
        noise_head = noise_pull.get("head")
        noise_base = noise_pull.get("base")
        if not isinstance(noise_head, Mapping) or noise_head.get("ref") != self._spec.noise_branch:
            raise github_controller_error("F1-A noise PR head branch does not match fixture spec.")
        if not isinstance(noise_base, Mapping) or noise_base.get("ref") != identity.default_branch:
            raise github_controller_error("F1-A noise PR base branch does not match fixture spec.")

        current_text = self._client.read_text_file(
            identity.owner,
            identity.name,
            self._spec.config_path,
            ref=identity.default_branch,
        )
        if current_text != _config_text(self._spec.regressed_timeout_seconds):
            raise github_controller_error(
                "F1-A current default-branch synchronization value is not regressed."
            )
        fix_commit = _nested_string(pull, "head", "sha")
        fixed_text = self._client.read_text_file(
            identity.owner,
            identity.name,
            self._spec.config_path,
            ref=fix_commit,
        )
        if fixed_text != _config_text(self._spec.healthy_timeout_seconds):
            raise github_controller_error(
                "F1-A original-fix branch no longer contains the healthy value."
            )

        head = self._client.ref(
            identity.owner,
            identity.name,
            f"heads/{identity.default_branch}",
        )
        reintroduction_commit = _nested_string(head, "object", "sha")
        commit = self._client.commit(
            identity.owner,
            identity.name,
            reintroduction_commit,
        )
        parents = commit.get("parents")
        if not isinstance(parents, list) or not parents:
            raise github_controller_error("F1-A reintroduction commit has no parent history.")
        merge_commit = _required_string(pull, "merge_commit_sha", "F1-A merge commit sha")
        parent_shas = {
            str(item.get("sha"))
            for item in parents
            if isinstance(item, Mapping) and isinstance(item.get("sha"), str)
        }
        if merge_commit not in parent_shas:
            raise github_controller_error(
                "F1-A current default-branch head is not the expected reintroduction "
                "commit directly following the historical fix merge."
            )

        return {
            "fixture_id": self._spec.fixture_id,
            "repository": identity.full_name,
            "default_branch": identity.default_branch,
            "config_path": self._spec.config_path,
            "healthy_timeout_seconds": self._spec.healthy_timeout_seconds,
            "regressed_timeout_seconds": self._spec.regressed_timeout_seconds,
            "regression_issue_number": issue_number,
            "original_fix_pr_number": pull_number,
            "original_fix_commit": fix_commit,
            "merge_commit": merge_commit,
            "reintroduction_commit": reintroduction_commit,
            "noise_issue_number": noise_issue_number,
            "noise_pr_number": noise_pull_number,
        }



def _emit_existing_fixture_skips(
    report: Callable[[apparatus_action_progress], None] | None,
    total: int,
) -> None:
    phases = (
        (3, "skipped (already intact): regression state and canonical issue"),
        (4, "skipped (already intact): historical fix branch and healthy commit"),
        (5, "skipped (already intact): historical fix pull request and merge"),
        (6, "skipped (already intact): closed regression issue and reintroduction on main"),
        (7, "skipped (already intact): unrelated issue noise"),
        (8, "skipped (already intact): unrelated documentation branch and pull request"),
    )
    for step, message in phases:
        _emit(report, step, total, message)

def _emit(
    report: Callable[[apparatus_action_progress], None] | None,
    step: int,
    total: int,
    message: str,
) -> None:
    if report is not None:
        report(apparatus_action_progress(message=message, step=step, total=total))


def load_f1_a_spec(value: Mapping[str, Any]) -> github_f1_a_spec:
    if value.get("schema_version") != "0.1":
        raise ValueError("F1-A fixture spec schema_version must be '0.1'.")
    if value.get("fixture_id") != "github_workspace_f1_a":
        raise ValueError("F1-A fixture spec has an unexpected fixture_id.")

    def text(name: str) -> str:
        item = value.get(name)
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"F1-A fixture spec field '{name}' is invalid.")
        return item.strip()

    def positive_int(name: str) -> int:
        item = value.get(name)
        if not isinstance(item, int) or isinstance(item, bool) or item <= 0:
            raise ValueError(f"F1-A fixture spec field '{name}' is invalid.")
        return item

    def object_text(section: str, field: str) -> str:
        item = value.get(section)
        if not isinstance(item, Mapping):
            raise ValueError(f"F1-A fixture spec section '{section}' is invalid.")
        result = item.get(field)
        if not isinstance(result, str) or not result.strip():
            raise ValueError(
                f"F1-A fixture spec field '{section}.{field}' is invalid."
            )
        return result.strip()

    healthy = positive_int("healthy_timeout_seconds")
    regressed = positive_int("regressed_timeout_seconds")
    if healthy == regressed:
        raise ValueError("F1-A healthy and regressed timeout values must differ.")

    return github_f1_a_spec(
        fixture_id="github_workspace_f1_a",
        config_path=text("config_path"),
        healthy_timeout_seconds=healthy,
        regressed_timeout_seconds=regressed,
        original_fix_branch=text("original_fix_branch"),
        noise_branch=text("noise_branch"),
        regression_issue_title=object_text("regression_issue", "title"),
        regression_issue_marker=object_text("regression_issue", "marker"),
        original_fix_pr_title=object_text("original_fix_pr", "title"),
        original_fix_pr_marker=object_text("original_fix_pr", "marker"),
        noise_issue_title=object_text("noise_issue", "title"),
        noise_issue_marker=object_text("noise_issue", "marker"),
        noise_pr_title=object_text("noise_pr", "title"),
        noise_pr_marker=object_text("noise_pr", "marker"),
        noise_pr_path=object_text("noise_pr", "path"),
    )


def _config_text(timeout_seconds: int) -> str:
    return json.dumps(
        {"default_synchronization_timeout_seconds": timeout_seconds},
        indent=2,
        sort_keys=True,
    ) + "\n"


def _issue_body(spec: github_f1_a_spec, *, pull_number: int | None = None) -> str:
    relation = (
        f"\n\nHistorical fix: pull request #{pull_number}."
        if pull_number is not None
        else ""
    )
    return _marker_body(
        spec.regression_issue_marker,
        (
            "The default synchronization timeout regressed from "
            f"{spec.healthy_timeout_seconds} seconds to "
            f"{spec.regressed_timeout_seconds} seconds. "
            f"The authoritative configuration is `{spec.config_path}`."
            + relation
        ),
    )


def _pull_body(spec: github_f1_a_spec, issue_number: int) -> str:
    return _marker_body(
        spec.original_fix_pr_marker,
        (
            f"Restores `{spec.config_path}` from "
            f"{spec.regressed_timeout_seconds} seconds to "
            f"{spec.healthy_timeout_seconds} seconds.\n\n"
            f"Tracks issue #{issue_number}."
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
        raise github_controller_error(
            f"Multiple GitHub objects contain fixture marker '{marker}'."
        )
    return matches[0] if matches else None


def _required_int(value: Mapping[str, Any], key: str, label: str) -> int:
    result = value.get(key)
    if not isinstance(result, int) or isinstance(result, bool):
        raise github_controller_error(f"{label} is not a numeric GitHub identifier.")
    return result


def _required_string(value: Mapping[str, Any], key: str, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise github_controller_error(f"{label} is missing.")
    return result


def _nested_string(
    value: Mapping[str, Any],
    outer: str,
    inner: str,
) -> str:
    nested = value.get(outer)
    if not isinstance(nested, Mapping):
        raise github_controller_error(f"GitHub response has no '{outer}' object.")
    return _required_string(nested, inner, f"GitHub response {outer}.{inner}")
