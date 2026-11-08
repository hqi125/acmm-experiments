from __future__ import annotations

from acmm.experiment_api import apparatus_action_result

from .controller import (
    github_api_error,
    github_controller_client,
    github_controller_error,
    github_fixture_base_file,
    github_repository_identity,
)


class github_fixture_base_initializer:
    def __init__(
        self,
        client: github_controller_client,
        *,
        repository_name: str,
        expected_repository_full_name: str,
        expected_repository_id: int,
        expected_default_branch: str,
        require_private: bool,
        fixture_base_version: str,
        fixture_base_files: tuple[github_fixture_base_file, ...],
    ) -> None:
        if not fixture_base_files:
            raise ValueError("Trusted fixture base must contain at least one file.")
        self._client = client
        self._repository_name = repository_name
        self._expected_repository_full_name = expected_repository_full_name
        self._expected_repository_id = expected_repository_id
        self._expected_default_branch = expected_default_branch
        self._require_private = require_private
        self._fixture_base_version = fixture_base_version
        self._fixture_base_files = tuple(fixture_base_files)

    def run(self) -> apparatus_action_result:
        identity = self._resolve_safe_identity()
        initialized = self._repository_has_branch(identity)
        if initialized:
            self._verify_fixture_base(identity)
            head_sha = self._head_sha(identity)
            return apparatus_action_result(
                changed=False,
                detail=(
                    f"trusted fixture base v{self._fixture_base_version} is already "
                    "initialized and matches package-owned seed content"
                ),
                observations=self._observations(identity, head_sha),
            )

        self._require_clean_empty_repository(identity)
        for index, item in enumerate(self._fixture_base_files):
            self._client.create_or_update_file(
                identity.owner,
                identity.name,
                item.path,
                message=(
                    f"ACMM: initialize fixture base v{self._fixture_base_version} "
                    f"({item.path})"
                ),
                content=item.content,
                branch=(None if index == 0 else self._expected_default_branch),
            )

        self._verify_fixture_base(identity)
        head_sha = self._head_sha(identity)
        return apparatus_action_result(
            changed=True,
            detail=(
                f"initialized trusted fixture base v{self._fixture_base_version} "
                f"on '{self._expected_default_branch}'"
            ),
            observations=self._observations(identity, head_sha),
        )

    def _resolve_safe_identity(self) -> github_repository_identity:
        identity = self._client.resolve_repository(self._repository_name)
        if (
            identity.full_name != self._expected_repository_full_name
            or identity.repository_id != self._expected_repository_id
        ):
            raise github_controller_error(
                f"Resolved repository {identity.full_name} "
                f"(repository id={identity.repository_id}); expected "
                f"{self._expected_repository_full_name} "
                f"(repository id={self._expected_repository_id})."
            )
        if self._require_private and not identity.private:
            raise github_controller_error("Pinned fixture repository is not private.")
        if not identity.issues_enabled:
            raise github_controller_error("Pinned fixture repository has Issues disabled.")
        if not identity.push_allowed:
            raise github_controller_error(
                "Controller credential does not have push access to the fixture repository."
            )
        if identity.default_branch != self._expected_default_branch:
            raise github_controller_error(
                f"Pinned fixture repository default branch is '{identity.default_branch}'; "
                f"expected '{self._expected_default_branch}'."
            )
        return identity

    def _repository_has_branch(self, identity: github_repository_identity) -> bool:
        try:
            self._client.ref(
                identity.owner,
                identity.name,
                f"heads/{self._expected_default_branch}",
            )
            return True
        except github_api_error as exc:
            if exc.status == 409 and "empty" in exc.detail.lower():
                return False
            raise

    def _require_clean_empty_repository(
        self,
        identity: github_repository_identity,
    ) -> None:
        issues = self._client.list_issues(
            identity.owner,
            identity.name,
            state="all",
            per_page=100,
        )
        pulls = self._client.list_pull_requests(
            identity.owner,
            identity.name,
            state="all",
            per_page=100,
        )
        if issues or pulls:
            raise github_controller_error(
                "Empty Git repository contains pre-existing issue or pull-request state; "
                "refusing trusted fixture-base initialization."
            )

    def _verify_fixture_base(self, identity: github_repository_identity) -> None:
        for item in self._fixture_base_files:
            actual = self._client.read_text_file(
                identity.owner,
                identity.name,
                item.path,
                ref=self._expected_default_branch,
            )
            if actual != item.content:
                raise github_controller_error(
                    f"Trusted fixture base file '{item.path}' does not match "
                    "package-owned seed content."
                )

    def _head_sha(self, identity: github_repository_identity) -> str:
        value = self._client.ref(
            identity.owner,
            identity.name,
            f"heads/{self._expected_default_branch}",
        )
        obj = value.get("object")
        sha = obj.get("sha") if isinstance(obj, dict) else None
        if not isinstance(sha, str) or not sha:
            raise github_controller_error(
                "Default-branch reference response does not contain a commit SHA."
            )
        return sha

    def _observations(
        self,
        identity: github_repository_identity,
        head_sha: str,
    ) -> dict[str, object]:
        return {
            "repository": identity.full_name,
            "repository_id": identity.repository_id,
            "default_branch": self._expected_default_branch,
            "fixture_base_version": self._fixture_base_version,
            "head_sha": head_sha,
        }
