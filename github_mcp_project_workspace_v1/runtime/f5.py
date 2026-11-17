from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from acmm.experiment_api import apparatus_action_progress, apparatus_action_result

from .controller import (
    github_controller_client,
    github_controller_error,
    github_fixture_base_file,
    github_repository_identity,
)


@dataclass(frozen=True)
class github_f5_issue_spec:
    title: str
    marker: str
    body: str


@dataclass(frozen=True)
class github_f5_a_spec:
    fixture_id: str
    retry_source_path: str
    retry_source_content: str
    retry_tests_path: str
    retry_tests_content: str
    retry_issue: github_f5_issue_spec


@dataclass(frozen=True)
class github_f5_b_spec:
    fixture_id: str
    release_authority_path: str
    release_authority_content: str
    maintenance_policy_path: str
    maintenance_policy_content: str
    compatibility_path: str
    compatibility_stale_content: str
    compatibility_expected_content: str
    channel_metadata_path: str
    channel_metadata_stale_content: str
    channel_metadata_expected_content: str
    product_source_path: str
    product_source_content: str


class _github_f5_materializer_base:
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

    def _seed_initial_files(
        self,
        identity: github_repository_identity,
        files: tuple[tuple[str, str, str], ...],
    ) -> None:
        """Add package-owned files to the current local publication phase.

        This helper is only for a newly created disposable repository whose
        first remote publication has not happened yet. It deliberately avoids
        remote existence checks so the lifecycle can compose fixture-base and
        scenario commits into one Git push.
        """
        for path, content, message in files:
            self._client.create_or_update_file(
                identity.owner,
                identity.name,
                path,
                message=message,
                content=content,
                branch=identity.default_branch,
            )

    def _ensure_file(
        self,
        identity: github_repository_identity,
        path: str,
        content: str,
        message: str,
    ) -> bool:
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
                return False
            sha = existing.get("sha")
            if not isinstance(sha, str):
                raise github_controller_error(
                    f"Existing fixture file '{path}' has no blob SHA."
                )
            self._client.create_or_update_file(
                identity.owner,
                identity.name,
                path,
                message=message,
                content=content,
                branch=identity.default_branch,
                sha=sha,
            )
            return True
        self._client.create_or_update_file(
            identity.owner,
            identity.name,
            path,
            message=message,
            content=content,
            branch=identity.default_branch,
        )
        return True


class github_f5_a_materializer(_github_f5_materializer_base):
    description = "Materialize or verify the engineering-reference F5-A world."

    def __init__(self, client: github_controller_client, *, spec: github_f5_a_spec, **kwargs) -> None:
        super().__init__(client, **kwargs)
        self._spec = spec

    def run(self) -> apparatus_action_result:
        _identity, observations, changed = self._ensure()
        return apparatus_action_result(
            changed=changed,
            detail=(
                "materialized trusted F5-A controlled-implementation fixture"
                if changed
                else "F5-A trusted fixture already exists and matches package-owned state"
            ),
            observations=observations,
        )

    def seed_initial_publication(self, identity: github_repository_identity) -> None:
        self._seed_initial_files(
            identity,
            (
                (
                    self._spec.retry_source_path,
                    self._spec.retry_source_content,
                    "F5-A: seed retry policy implementation",
                ),
                (
                    self._spec.retry_tests_path,
                    self._spec.retry_tests_content,
                    "F5-A: seed retry policy acceptance specification",
                ),
            ),
        )

    def run_with_progress(
        self,
        report: Callable[[apparatus_action_progress], None],
    ) -> apparatus_action_result:
        report(
            apparatus_action_progress(
                step=1,
                total=1,
                detail="materializing/verifying F5-A implementation fixture",
            )
        )
        return self.run()

    def inspect(self):
        identity, observations, _changed = self._ensure(allow_create=False)
        return identity, observations

    def _ensure(self, *, allow_create: bool = True):
        identity = self._resolve_identity("F5-A")
        issue = self._discover_retry_issue(identity, retry=not allow_create)
        changed = False
        if issue is None:
            if not allow_create:
                raise github_controller_error("F5-A fixture is not fully materialized.")
            with self._client.git_publish_batch(identity.owner, identity.name):
                changed |= self._ensure_file(
                    identity,
                    self._spec.retry_source_path,
                    self._spec.retry_source_content,
                    "F5-A: seed retry policy implementation",
                )
                changed |= self._ensure_file(
                    identity,
                    self._spec.retry_tests_path,
                    self._spec.retry_tests_content,
                    "F5-A: seed retry policy acceptance specification",
                )
            issue = self._client.create_issue(
                identity.owner,
                identity.name,
                title=self._spec.retry_issue.title,
                body=_marker_body(self._spec.retry_issue.marker, self._spec.retry_issue.body),
            )
            changed = True
        issue_number = _required_int(issue, "number", "F5-A retry issue number")
        current = self._client.issue(identity.owner, identity.name, issue_number)
        if current.get("state") != "open":
            raise github_controller_error("F5-A retry issue is not open.")
        source = self._client.read_text_file(
            identity.owner,
            identity.name,
            self._spec.retry_source_path,
            ref=identity.default_branch,
        )
        tests = self._client.read_text_file(
            identity.owner,
            identity.name,
            self._spec.retry_tests_path,
            ref=identity.default_branch,
        )
        if source != self._spec.retry_source_content or tests != self._spec.retry_tests_content:
            raise github_controller_error("F5-A package-owned source/test content does not match fixture definition.")
        return identity, {
            "fixture_id": self._spec.fixture_id,
            "retry_issue_number": issue_number,
            "retry_source_path": self._spec.retry_source_path,
            "retry_tests_path": self._spec.retry_tests_path,
        }, changed

    def _discover_retry_issue(
        self,
        identity: github_repository_identity,
        *,
        retry: bool,
    ) -> Mapping[str, Any] | None:
        issue = self._find_retry_issue_once(identity)
        if issue is not None or not retry:
            return issue
        for delay in self._discovery_retry_delays[1:]:
            self._client.wait_for_poll(
                max(2.0, float(delay)),
                "issue.list",
            )
            issue = self._find_retry_issue_once(identity)
            if issue is not None:
                return issue
        return None

    def _find_retry_issue_once(
        self,
        identity: github_repository_identity,
    ) -> Mapping[str, Any] | None:
        issues = tuple(
            item
            for item in self._client.list_issues(identity.owner, identity.name)
            if "pull_request" not in item
        )
        return _find_marker(issues, self._spec.retry_issue.marker)


class github_f5_b_materializer(_github_f5_materializer_base):
    description = "Materialize or verify the engineering-reference F5-B world."

    def __init__(self, client: github_controller_client, *, spec: github_f5_b_spec, **kwargs) -> None:
        super().__init__(client, **kwargs)
        self._spec = spec

    def run(self) -> apparatus_action_result:
        _identity, observations, changed = self._ensure()
        return apparatus_action_result(
            changed=changed,
            detail=(
                "materialized trusted F5-B release-maintenance fixture"
                if changed
                else "F5-B trusted fixture already exists and matches package-owned state"
            ),
            observations=observations,
        )

    def seed_initial_publication(self, identity: github_repository_identity) -> None:
        self._seed_initial_files(
            identity,
            (
                (
                    self._spec.release_authority_path,
                    self._spec.release_authority_content,
                    "F5-B: seed release authority",
                ),
                (
                    self._spec.maintenance_policy_path,
                    self._spec.maintenance_policy_content,
                    "F5-B: seed release maintenance policy",
                ),
                (
                    self._spec.compatibility_path,
                    self._spec.compatibility_stale_content,
                    "F5-B: seed stale compatibility mirror",
                ),
                (
                    self._spec.channel_metadata_path,
                    self._spec.channel_metadata_stale_content,
                    "F5-B: seed stale channel metadata",
                ),
                (
                    self._spec.product_source_path,
                    self._spec.product_source_content,
                    "F5-B: seed protected product source",
                ),
            ),
        )

    def run_with_progress(
        self,
        report: Callable[[apparatus_action_progress], None],
    ) -> apparatus_action_result:
        report(
            apparatus_action_progress(
                step=1,
                total=1,
                detail="materializing/verifying F5-B maintenance fixture",
            )
        )
        return self.run()

    def inspect(self):
        identity, observations, _changed = self._ensure(allow_create=False)
        return identity, observations

    def _ensure(self, *, allow_create: bool = True):
        identity = self._resolve_identity("F5-B")
        files = (
            (
                self._spec.release_authority_path,
                self._spec.release_authority_content,
                "F5-B: seed release authority",
            ),
            (
                self._spec.maintenance_policy_path,
                self._spec.maintenance_policy_content,
                "F5-B: seed release maintenance policy",
            ),
            (
                self._spec.compatibility_path,
                self._spec.compatibility_stale_content,
                "F5-B: seed stale compatibility mirror",
            ),
            (
                self._spec.channel_metadata_path,
                self._spec.channel_metadata_stale_content,
                "F5-B: seed stale channel metadata",
            ),
            (
                self._spec.product_source_path,
                self._spec.product_source_content,
                "F5-B: seed protected product source",
            ),
        )
        changed = False
        missing = [
            path
            for path, _content, _message in files
            if self._client.contents_optional(
                identity.owner,
                identity.name,
                path,
                ref=identity.default_branch,
            )
            is None
        ]
        if missing and not allow_create:
            raise github_controller_error("F5-B fixture is not fully materialized.")
        if allow_create:
            with self._client.git_publish_batch(identity.owner, identity.name):
                for path, content, message in files:
                    changed |= self._ensure_file(identity, path, content, message)
        for path, expected, _message in files:
            actual = self._client.read_text_file(
                identity.owner,
                identity.name,
                path,
                ref=identity.default_branch,
            )
            if actual != expected:
                raise github_controller_error(
                    f"F5-B fixture file '{path}' does not match package-owned content."
                )
        return identity, {
            "fixture_id": self._spec.fixture_id,
            "release_authority_path": self._spec.release_authority_path,
            "maintenance_policy_path": self._spec.maintenance_policy_path,
            "compatibility_path": self._spec.compatibility_path,
            "channel_metadata_path": self._spec.channel_metadata_path,
            "product_source_path": self._spec.product_source_path,
        }, changed


def load_f5_a_spec(value: Mapping[str, Any]) -> github_f5_a_spec:
    issue = value.get("retry_issue")
    if not isinstance(issue, Mapping):
        raise ValueError("F5-A retry_issue is invalid.")
    return github_f5_a_spec(
        fixture_id=_required_string(value, "fixture_id"),
        retry_source_path=_required_string(value, "retry_source_path"),
        retry_source_content=_required_string(value, "retry_source_content", allow_empty=True),
        retry_tests_path=_required_string(value, "retry_tests_path"),
        retry_tests_content=_required_string(value, "retry_tests_content", allow_empty=True),
        retry_issue=github_f5_issue_spec(
            title=_required_string(issue, "title"),
            marker=_required_string(issue, "marker"),
            body=_required_string(issue, "body"),
        ),
    )


def load_f5_b_spec(value: Mapping[str, Any]) -> github_f5_b_spec:
    return github_f5_b_spec(
        fixture_id=_required_string(value, "fixture_id"),
        release_authority_path=_required_string(value, "release_authority_path"),
        release_authority_content=_required_string(value, "release_authority_content", allow_empty=True),
        maintenance_policy_path=_required_string(value, "maintenance_policy_path"),
        maintenance_policy_content=_required_string(value, "maintenance_policy_content", allow_empty=True),
        compatibility_path=_required_string(value, "compatibility_path"),
        compatibility_stale_content=_required_string(value, "compatibility_stale_content", allow_empty=True),
        compatibility_expected_content=_required_string(value, "compatibility_expected_content", allow_empty=True),
        channel_metadata_path=_required_string(value, "channel_metadata_path"),
        channel_metadata_stale_content=_required_string(value, "channel_metadata_stale_content", allow_empty=True),
        channel_metadata_expected_content=_required_string(value, "channel_metadata_expected_content", allow_empty=True),
        product_source_path=_required_string(value, "product_source_path"),
        product_source_content=_required_string(value, "product_source_content", allow_empty=True),
    )


def _marker_body(marker: str, body: str) -> str:
    return f"<!-- {marker} -->\n\n{body}\n"


def _find_marker(
    values: tuple[Mapping[str, Any], ...],
    marker: str,
) -> Mapping[str, Any] | None:
    token = marker.casefold()
    matches = [
        item
        for item in values
        if token in str(item.get("body", "")).casefold()
    ]
    if len(matches) > 1:
        raise github_controller_error(f"Fixture marker '{marker}' is duplicated.")
    return matches[0] if matches else None


def _required_int(value: Mapping[str, Any], key: str, label: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise github_controller_error(f"{label} is missing or invalid.")
    return item


def _required_string(
    value: Mapping[str, Any],
    key: str,
    *,
    allow_empty: bool = False,
) -> str:
    item = value.get(key)
    if not isinstance(item, str) or (not allow_empty and not item.strip()):
        raise ValueError(f"F5 fixture field '{key}' is invalid.")
    return item
