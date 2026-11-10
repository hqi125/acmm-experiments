from __future__ import annotations

from dataclasses import dataclass
import base64
import json
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from acmm.experiment_api import (
    runtime_diagnostic_check,
    runtime_diagnostic_report,
)


Transport = Callable[
    [str, str, Mapping[str, str], bytes | None],
    tuple[int, Mapping[str, str], bytes],
]


class github_controller_error(RuntimeError):
    pass


class github_api_error(github_controller_error):
    def __init__(
        self,
        *,
        method: str,
        path: str,
        status: int,
        detail: str,
    ) -> None:
        self.method = method
        self.path = path
        self.status = status
        self.detail = detail
        super().__init__(
            f"GitHub API {method} {path} returned HTTP {status}: {detail}"
        )


@dataclass(frozen=True)
class github_repository_identity:
    repository_id: int
    owner: str
    name: str
    full_name: str
    private: bool
    default_branch: str
    issues_enabled: bool
    push_allowed: bool


@dataclass(frozen=True)
class github_fixture_base_file:
    path: str
    content: str


@dataclass(frozen=True)
class github_fixture_namespace:
    execution_id: str
    scenario_id: str
    branch_prefix: str = "acmm/"

    def branch(self, role: str) -> str:
        safe_role = _slug(role)
        return (
            f"{self.branch_prefix}{_slug(self.execution_id)}/"
            f"{_slug(self.scenario_id)}/{safe_role}"
        )

    def marker(self, fixture_marker: str) -> str:
        return (
            f"[{fixture_marker}:execution={self.execution_id};"
            f"scenario={self.scenario_id}]"
        )


class github_controller_client:
    def __init__(
        self,
        token: str,
        *,
        api_base: str = "https://api.github.com",
        transport: Transport | None = None,
    ) -> None:
        if not token.strip():
            raise ValueError("GitHub controller token must not be empty.")
        self._token = token.strip()
        self._api_base = api_base.rstrip("/")
        self._transport = transport or _urllib_transport

    def current_user(self) -> Mapping[str, Any]:
        return self._object("GET", "/user")

    def list_repositories(self) -> tuple[Mapping[str, Any], ...]:
        repositories: list[Mapping[str, Any]] = []
        page = 1
        while page <= 20:
            query = urlencode(
                {
                    "affiliation": "owner,collaborator,organization_member",
                    "per_page": 100,
                    "page": page,
                }
            )
            values = self._array("GET", f"/user/repos?{query}")
            repositories.extend(
                item for item in values if isinstance(item, Mapping)
            )
            if len(values) < 100:
                break
            page += 1
        return tuple(repositories)

    def resolve_repository(self, repository_name: str) -> github_repository_identity:
        matches: list[Mapping[str, Any]] = []
        page = 1
        while page <= 10:
            query = urlencode(
                {
                    "affiliation": "owner,collaborator,organization_member",
                    "per_page": 100,
                    "page": page,
                }
            )
            values = self._array("GET", f"/user/repos?{query}")
            matches.extend(
                item
                for item in values
                if isinstance(item, Mapping) and item.get("name") == repository_name
            )
            if len(values) < 100:
                break
            page += 1

        if not matches:
            raise github_controller_error(
                f"Controller credential cannot resolve repository '{repository_name}'."
            )
        if len(matches) != 1:
            full_names = sorted(str(item.get("full_name", "?")) for item in matches)
            raise github_controller_error(
                f"Repository name '{repository_name}' is ambiguous for the controller "
                f"credential: {', '.join(full_names)}"
            )

        return _repository_identity(matches[0])

    def repository(self, owner: str, name: str) -> Mapping[str, Any]:
        return self._object("GET", f"/repos/{quote(owner)}/{quote(name)}")

    def repository_optional(
        self,
        owner: str,
        name: str,
    ) -> Mapping[str, Any] | None:
        try:
            return self.repository(owner, name)
        except github_api_error as exc:
            if exc.status == 404:
                return None
            raise

    def repository_identity(
        self,
        owner: str,
        name: str,
    ) -> github_repository_identity:
        return _repository_identity(self.repository(owner, name))

    def create_repository(
        self,
        *,
        name: str,
        description: str,
        private: bool = True,
        has_issues: bool = True,
        auto_init: bool = False,
    ) -> Mapping[str, Any]:
        if private is not True:
            raise ValueError(
                "ACMM trusted repository creation is private-only; public repositories "
                "are forbidden."
            )
        value = self._object(
            "POST",
            "/user/repos",
            {
                "name": name,
                "description": description,
                "private": True,
                "has_issues": has_issues,
                "auto_init": auto_init,
            },
            expected=(201,),
        )
        if value.get("private") is not True:
            raise github_controller_error(
                "GitHub create-repository response is not private; refusing to use "
                "the repository as ACMM apparatus."
            )
        return value

    def delete_repository(self, owner: str, name: str) -> None:
        self._json(
            "DELETE",
            f"/repos/{quote(owner)}/{quote(name)}",
            expected=(204,),
        )

    def ref(self, owner: str, name: str, ref: str) -> Mapping[str, Any]:
        encoded = quote(ref, safe="/")
        return self._object(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/git/ref/{encoded}",
        )

    def contents(
        self,
        owner: str,
        name: str,
        path: str = "",
        *,
        ref: str | None = None,
    ) -> Any:
        encoded = quote(path, safe="/")
        suffix = f"/contents/{encoded}" if encoded else "/contents"
        if ref is not None:
            suffix += "?" + urlencode({"ref": ref})
        return self._json("GET", f"/repos/{quote(owner)}/{quote(name)}{suffix}")

    def contents_optional(
        self,
        owner: str,
        name: str,
        path: str,
        *,
        ref: str | None = None,
    ) -> Any | None:
        try:
            return self.contents(owner, name, path, ref=ref)
        except github_api_error as exc:
            if exc.status == 404:
                return None
            raise

    def read_text_file(
        self,
        owner: str,
        name: str,
        path: str,
        *,
        ref: str,
    ) -> str:
        value = self.contents(owner, name, path, ref=ref)
        if not isinstance(value, Mapping):
            raise github_controller_error(
                f"Repository content '{path}' is not a file object."
            )
        encoding = value.get("encoding")
        content = value.get("content")
        if encoding != "base64" or not isinstance(content, str):
            raise github_controller_error(
                f"Repository content '{path}' is not base64 file content."
            )
        try:
            raw = base64.b64decode(content.encode("ascii"), validate=False)
            return raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise github_controller_error(
                f"Repository content '{path}' is not valid UTF-8 text."
            ) from exc

    def create_or_update_file(
        self,
        owner: str,
        name: str,
        path: str,
        *,
        message: str,
        content: str,
        branch: str | None = None,
        sha: str | None = None,
    ) -> Mapping[str, Any]:
        encoded_path = quote(path, safe="/")
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        if branch is not None:
            payload["branch"] = branch
        if sha is not None:
            payload["sha"] = sha
        return self._object(
            "PUT",
            f"/repos/{quote(owner)}/{quote(name)}/contents/{encoded_path}",
            payload,
            expected=(200, 201),
        )

    def list_issues(
        self,
        owner: str,
        name: str,
        *,
        state: str = "all",
        per_page: int = 100,
    ) -> tuple[Mapping[str, Any], ...]:
        query = urlencode({"state": state, "per_page": per_page})
        return self._array(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/issues?{query}",
        )

    def list_pull_requests(
        self,
        owner: str,
        name: str,
        *,
        state: str = "all",
        per_page: int = 100,
    ) -> tuple[Mapping[str, Any], ...]:
        query = urlencode({"state": state, "per_page": per_page})
        return self._array(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/pulls?{query}",
        )

    def issue(
        self,
        owner: str,
        name: str,
        number: int,
    ) -> Mapping[str, Any]:
        return self._object(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/issues/{number}",
        )

    def pull_request(
        self,
        owner: str,
        name: str,
        number: int,
    ) -> Mapping[str, Any]:
        return self._object(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/pulls/{number}",
        )

    def commit(
        self,
        owner: str,
        name: str,
        ref: str,
    ) -> Mapping[str, Any]:
        return self._object(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/commits/{quote(ref, safe='')}",
        )

    def list_commits(
        self,
        owner: str,
        name: str,
        *,
        sha: str | None = None,
        path: str | None = None,
        per_page: int = 100,
    ) -> tuple[Mapping[str, Any], ...]:
        query_values: dict[str, Any] = {"per_page": per_page}
        if sha is not None:
            query_values["sha"] = sha
        if path is not None:
            query_values["path"] = path
        query = urlencode(query_values)
        return self._array(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/commits?{query}",
        )

    def compare_commits(
        self,
        owner: str,
        name: str,
        base: str,
        head: str,
    ) -> Mapping[str, Any]:
        comparison = quote(f"{base}...{head}", safe=".")
        return self._object(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/compare/{comparison}",
        )

    def list_workflows(
        self,
        owner: str,
        name: str,
    ) -> Mapping[str, Any]:
        return self._object(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/actions/workflows?per_page=100",
        )

    def list_workflow_runs(
        self,
        owner: str,
        name: str,
    ) -> Mapping[str, Any]:
        return self._object(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/actions/runs?per_page=1",
        )

    def list_workflow_runs_for_workflow(
        self,
        owner: str,
        name: str,
        workflow_id: int | str,
        *,
        branch: str | None = None,
        event: str | None = None,
        per_page: int = 100,
    ) -> Mapping[str, Any]:
        query_values: dict[str, Any] = {"per_page": per_page}
        if branch is not None:
            query_values["branch"] = branch
        if event is not None:
            query_values["event"] = event
        query = urlencode(query_values)
        return self._object(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/actions/workflows/"
            f"{quote(str(workflow_id), safe='')}/runs?{query}",
        )

    def dispatch_workflow(
        self,
        owner: str,
        name: str,
        workflow_id: int | str,
        *,
        ref: str,
        inputs: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {"ref": ref}
        if inputs:
            payload["inputs"] = dict(inputs)
        value = self._json(
            "POST",
            f"/repos/{quote(owner)}/{quote(name)}/actions/workflows/"
            f"{quote(str(workflow_id), safe='')}/dispatches",
            payload,
            expected=(200, 204),
        )
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise github_controller_error(
                "GitHub workflow-dispatch response is not an object."
            )
        return value

    def workflow_run(
        self,
        owner: str,
        name: str,
        run_id: int,
    ) -> Mapping[str, Any]:
        return self._object(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/actions/runs/{run_id}",
        )

    def list_branches(
        self,
        owner: str,
        name: str,
        *,
        per_page: int = 100,
    ) -> tuple[Mapping[str, Any], ...]:
        query = urlencode({"per_page": per_page})
        return self._array(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/branches?{query}",
        )

    def list_labels(
        self,
        owner: str,
        name: str,
        *,
        per_page: int = 100,
    ) -> tuple[Mapping[str, Any], ...]:
        query = urlencode({"per_page": per_page})
        return self._array(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/labels?{query}",
        )

    def list_milestones(
        self,
        owner: str,
        name: str,
        *,
        state: str = "all",
        per_page: int = 100,
    ) -> tuple[Mapping[str, Any], ...]:
        query = urlencode({"state": state, "per_page": per_page})
        return self._array(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/milestones?{query}",
        )

    def milestone(
        self,
        owner: str,
        name: str,
        number: int,
    ) -> Mapping[str, Any]:
        return self._object(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/milestones/{number}",
        )

    def create_milestone(
        self,
        owner: str,
        name: str,
        *,
        title: str,
        description: str | None = None,
        state: str = "open",
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {"title": title, "state": state}
        if description is not None:
            payload["description"] = description
        return self._object(
            "POST",
            f"/repos/{quote(owner)}/{quote(name)}/milestones",
            payload,
            expected=(201,),
        )

    def issue_comments(
        self,
        owner: str,
        name: str,
        number: int,
        *,
        per_page: int = 100,
    ) -> tuple[Mapping[str, Any], ...]:
        query = urlencode({"per_page": per_page})
        return self._array(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/issues/{number}/comments?{query}",
        )

    def create_issue_comment(
        self,
        owner: str,
        name: str,
        number: int,
        body: str,
    ) -> Mapping[str, Any]:
        return self._object(
            "POST",
            f"/repos/{quote(owner)}/{quote(name)}/issues/{number}/comments",
            {"body": body},
            expected=(201,),
        )

    def pull_request_reviews(
        self,
        owner: str,
        name: str,
        number: int,
        *,
        per_page: int = 100,
    ) -> tuple[Mapping[str, Any], ...]:
        query = urlencode({"per_page": per_page})
        return self._array(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/pulls/{number}/reviews?{query}",
        )

    def pull_request_review_comments(
        self,
        owner: str,
        name: str,
        number: int,
        *,
        per_page: int = 100,
    ) -> tuple[Mapping[str, Any], ...]:
        query = urlencode({"per_page": per_page})
        return self._array(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/pulls/{number}/comments?{query}",
        )

    def update_issue_comment(
        self,
        owner: str,
        name: str,
        comment_id: int,
        body: str,
    ) -> Mapping[str, Any]:
        return self._object(
            "PATCH",
            f"/repos/{quote(owner)}/{quote(name)}/issues/comments/{comment_id}",
            {"body": body},
        )

    def delete_issue_comment(
        self,
        owner: str,
        name: str,
        comment_id: int,
    ) -> None:
        self._json(
            "DELETE",
            f"/repos/{quote(owner)}/{quote(name)}/issues/comments/{comment_id}",
            expected=(204,),
        )

    def update_pull_request_review_comment(
        self,
        owner: str,
        name: str,
        comment_id: int,
        body: str,
    ) -> Mapping[str, Any]:
        return self._object(
            "PATCH",
            f"/repos/{quote(owner)}/{quote(name)}/pulls/comments/{comment_id}",
            {"body": body},
        )

    def delete_pull_request_review_comment(
        self,
        owner: str,
        name: str,
        comment_id: int,
    ) -> None:
        self._json(
            "DELETE",
            f"/repos/{quote(owner)}/{quote(name)}/pulls/comments/{comment_id}",
            expected=(204,),
        )

    def delete_pending_pull_request_review(
        self,
        owner: str,
        name: str,
        number: int,
        review_id: int,
    ) -> None:
        self._json(
            "DELETE",
            f"/repos/{quote(owner)}/{quote(name)}/pulls/{number}/reviews/{review_id}",
            expected=(200,),
        )

    def create_label(
        self,
        owner: str,
        name: str,
        *,
        label: str,
        color: str,
        description: str | None = None,
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {"name": label, "color": color}
        if description is not None:
            payload["description"] = description
        return self._object(
            "POST",
            f"/repos/{quote(owner)}/{quote(name)}/labels",
            payload,
            expected=(201,),
        )

    def update_label(
        self,
        owner: str,
        name: str,
        current_name: str,
        *,
        new_name: str,
        color: str,
        description: str | None = None,
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {
            "new_name": new_name,
            "color": color,
            "description": description,
        }
        return self._object(
            "PATCH",
            f"/repos/{quote(owner)}/{quote(name)}/labels/{quote(current_name, safe='')}",
            payload,
        )

    def delete_label(
        self,
        owner: str,
        name: str,
        label: str,
    ) -> None:
        self._json(
            "DELETE",
            f"/repos/{quote(owner)}/{quote(name)}/labels/{quote(label, safe='')}",
            expected=(204,),
        )

    def create_ref(
        self,
        owner: str,
        name: str,
        branch: str,
        sha: str,
    ) -> Mapping[str, Any]:
        return self._object(
            "POST",
            f"/repos/{quote(owner)}/{quote(name)}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": sha},
            expected=(201,),
        )

    def update_ref(
        self,
        owner: str,
        name: str,
        branch: str,
        sha: str,
        *,
        force: bool = True,
    ) -> Mapping[str, Any]:
        encoded = quote(f"heads/{branch}", safe="/")
        return self._object(
            "PATCH",
            f"/repos/{quote(owner)}/{quote(name)}/git/refs/{encoded}",
            {"sha": sha, "force": force},
        )

    def delete_ref(self, owner: str, name: str, branch: str) -> None:
        encoded = quote(f"heads/{branch}", safe="/")
        self._json(
            "DELETE",
            f"/repos/{quote(owner)}/{quote(name)}/git/refs/{encoded}",
            expected=(204,),
        )

    def create_issue(
        self,
        owner: str,
        name: str,
        *,
        title: str,
        body: str,
        labels: tuple[str, ...] = (),
        milestone: int | None = None,
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {
            "title": title,
            "body": body,
            "labels": list(labels),
        }
        if milestone is not None:
            payload["milestone"] = milestone
        return self._object(
            "POST",
            f"/repos/{quote(owner)}/{quote(name)}/issues",
            payload,
            expected=(201,),
        )

    def update_issue(
        self,
        owner: str,
        name: str,
        number: int,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return self._object(
            "PATCH",
            f"/repos/{quote(owner)}/{quote(name)}/issues/{number}",
            dict(payload),
        )

    def create_pull_request(
        self,
        owner: str,
        name: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str,
        draft: bool = False,
    ) -> Mapping[str, Any]:
        return self._object(
            "POST",
            f"/repos/{quote(owner)}/{quote(name)}/pulls",
            {
                "title": title,
                "head": head,
                "base": base,
                "body": body,
                "draft": draft,
            },
            expected=(201,),
        )

    def update_pull_request(
        self,
        owner: str,
        name: str,
        number: int,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return self._object(
            "PATCH",
            f"/repos/{quote(owner)}/{quote(name)}/pulls/{number}",
            dict(payload),
        )

    def merge_pull_request(
        self,
        owner: str,
        name: str,
        number: int,
        *,
        commit_title: str | None = None,
        commit_message: str | None = None,
        merge_method: str = "merge",
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {"merge_method": merge_method}
        if commit_title is not None:
            payload["commit_title"] = commit_title
        if commit_message is not None:
            payload["commit_message"] = commit_message
        return self._object(
            "PUT",
            f"/repos/{quote(owner)}/{quote(name)}/pulls/{number}/merge",
            payload,
        )

    def _object(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        expected: tuple[int, ...] = (200,),
    ) -> Mapping[str, Any]:
        value = self._json(method, path, payload, expected=expected)
        if not isinstance(value, Mapping):
            raise github_controller_error(
                f"GitHub API response for {method} {path} is not an object."
            )
        return value

    def _array(
        self,
        method: str,
        path: str,
        *,
        expected: tuple[int, ...] = (200,),
    ) -> tuple[Mapping[str, Any], ...]:
        value = self._json(method, path, expected=expected)
        if not isinstance(value, list) or not all(
            isinstance(item, Mapping) for item in value
        ):
            raise github_controller_error(
                f"GitHub API response for {method} {path} is not an object array."
            )
        return tuple(value)

    def _json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        data = None
        if payload is not None:
            data = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "acmm-github-fixture-controller",
        }
        status, _response_headers, body = self._transport(
            method,
            self._api_base + path,
            headers,
            data,
        )
        if status not in expected:
            detail = _safe_error_detail(body)
            raise github_api_error(
                method=method,
                path=path,
                status=status,
                detail=detail,
            )
        if status == 204 or not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise github_controller_error(
                f"GitHub API {method} {path} returned invalid JSON."
            ) from exc


class github_controller_diagnostic:
    def __init__(
        self,
        client: github_controller_client,
        *,
        repository_name: str,
        expected_repository_full_name: str,
        expected_repository_id: int,
        expected_default_branch: str,
        require_private: bool,
        credentials_distinct: bool,
        fixture_base_version: str,
        fixture_base_files: tuple[github_fixture_base_file, ...],
    ) -> None:
        self._client = client
        self._repository_name = repository_name
        self._expected_repository_full_name = expected_repository_full_name
        self._expected_repository_id = expected_repository_id
        self._expected_default_branch = expected_default_branch
        self._require_private = require_private
        self._credentials_distinct = credentials_distinct
        self._fixture_base_version = fixture_base_version
        self._fixture_base_files = tuple(fixture_base_files)

    def doctor(self) -> runtime_diagnostic_report:
        checks: list[runtime_diagnostic_check] = [
            runtime_diagnostic_check(
                name="credential_separation",
                ok=self._credentials_distinct,
                detail=(
                    "controller and subject credentials are distinct"
                    if self._credentials_distinct
                    else "controller and subject credentials resolve to the same value"
                ),
            )
        ]

        try:
            user = self._client.current_user()
            login = str(user.get("login", "")).strip()
            if not login:
                raise github_controller_error(
                    "Authenticated GitHub user response does not contain login."
                )
            checks.append(
                runtime_diagnostic_check(
                    name="controller_identity",
                    ok=True,
                    detail=f"authenticated as {login}",
                )
            )
        except Exception as exc:
            checks.append(_failed("controller_identity", exc))
            return runtime_diagnostic_report(tuple(checks))

        try:
            identity = self._client.resolve_repository(self._repository_name)
            identity_ok = (
                identity.full_name == self._expected_repository_full_name
                and identity.repository_id == self._expected_repository_id
            )
            if identity_ok:
                identity_detail = (
                    f"resolved pinned repository {identity.full_name} "
                    f"(repository id={identity.repository_id})"
                )
            else:
                identity_detail = (
                    f"resolved {identity.full_name} "
                    f"(repository id={identity.repository_id}); expected "
                    f"{self._expected_repository_full_name} "
                    f"(repository id={self._expected_repository_id})"
                )
            checks.append(
                runtime_diagnostic_check(
                    name="repository_identity",
                    ok=identity_ok,
                    detail=identity_detail,
                )
            )
            if not identity_ok:
                return runtime_diagnostic_report(tuple(checks))
        except Exception as exc:
            checks.append(_failed("repository_identity", exc))
            return runtime_diagnostic_report(tuple(checks))

        private_ok = identity.private if self._require_private else True
        checks.append(
            runtime_diagnostic_check(
                name="repository_private",
                ok=private_ok,
                detail=(
                    "repository is private"
                    if identity.private
                    else "repository is not private"
                ),
            )
        )
        checks.append(
            runtime_diagnostic_check(
                name="issues_enabled",
                ok=identity.issues_enabled,
                detail=(
                    "repository Issues are enabled"
                    if identity.issues_enabled
                    else "repository Issues are disabled"
                ),
            )
        )
        checks.append(
            runtime_diagnostic_check(
                name="controller_push_access",
                ok=identity.push_allowed,
                detail=(
                    "repository reports push capability for controller credential"
                    if identity.push_allowed
                    else "repository does not report push capability for controller credential"
                ),
            )
        )
        default_branch_ok = identity.default_branch == self._expected_default_branch
        checks.append(
            runtime_diagnostic_check(
                name="repository_default_branch",
                ok=default_branch_ok,
                detail=(
                    f"default branch is '{identity.default_branch}'"
                    if default_branch_ok
                    else (
                        f"default branch is '{identity.default_branch}'; expected "
                        f"'{self._expected_default_branch}'"
                    )
                ),
            )
        )

        checks.extend(
            self._read_surface_checks(identity)
        )
        return runtime_diagnostic_report(tuple(checks))

    def _read_surface_checks(
        self,
        identity: github_repository_identity,
    ) -> tuple[runtime_diagnostic_check, ...]:
        owner = identity.owner
        name = identity.name
        checks: list[runtime_diagnostic_check] = []

        try:
            self._client.ref(
                owner,
                name,
                f"heads/{identity.default_branch}",
            )
            checks.append(
                runtime_diagnostic_check(
                    name="repository_initialized",
                    ok=True,
                    detail=(
                        "repository has a readable default branch"
                    ),
                )
            )
            checks.append(
                runtime_diagnostic_check(
                    name="default_branch_read",
                    ok=True,
                    detail=f"default branch '{identity.default_branch}' is readable",
                )
            )
            try:
                self._client.contents(
                    owner,
                    name,
                    ref=identity.default_branch,
                )
                checks.append(
                    runtime_diagnostic_check(
                        name="repository_contents_read",
                        ok=True,
                        detail="default-branch repository contents are readable",
                    )
                )
                try:
                    self._verify_fixture_base(identity)
                    checks.append(
                        runtime_diagnostic_check(
                            name="fixture_base_integrity",
                            ok=True,
                            detail=(
                                f"trusted fixture base v{self._fixture_base_version} "
                                "matches package-owned seed content"
                            ),
                        )
                    )
                except Exception as exc:
                    checks.append(_failed("fixture_base_integrity", exc))
            except Exception as exc:
                checks.append(_failed("repository_contents_read", exc))
        except github_api_error as exc:
            if exc.status == 409 and "empty" in exc.detail.lower():
                checks.append(
                    runtime_diagnostic_check(
                        name="repository_initialized",
                        ok=False,
                        detail=(
                            "repository is empty; initialize the trusted fixture base "
                            "before scientific execution"
                        ),
                    )
                )
            else:
                checks.append(_failed("default_branch_read", exc))
        except Exception as exc:
            checks.append(_failed("default_branch_read", exc))

        operations = (
            (
                "issues_read",
                lambda: self._client.list_issues(owner, name, per_page=1),
                "Issues API is readable",
            ),
            (
                "pull_requests_read",
                lambda: self._client.list_pull_requests(owner, name, per_page=1),
                "Pull Requests API is readable",
            ),
            (
                "actions_workflows_read",
                lambda: self._client.list_workflows(owner, name),
                "Actions workflows are readable",
            ),
            (
                "actions_runs_read",
                lambda: self._client.list_workflow_runs(owner, name),
                "Actions workflow runs are readable",
            ),
        )
        for check_name, action, success_detail in operations:
            try:
                action()
                checks.append(
                    runtime_diagnostic_check(
                        name=check_name,
                        ok=True,
                        detail=success_detail,
                    )
                )
            except Exception as exc:
                checks.append(_failed(check_name, exc))
        return tuple(checks)

    def _verify_fixture_base(
        self,
        identity: github_repository_identity,
    ) -> None:
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


def _repository_identity(data: Mapping[str, Any]) -> github_repository_identity:
    owner_data = data.get("owner")
    permissions = data.get("permissions")
    owner = owner_data.get("login") if isinstance(owner_data, Mapping) else None
    push_allowed = permissions.get("push") if isinstance(permissions, Mapping) else False
    values = {
        "repository_id": data.get("id"),
        "owner": owner,
        "name": data.get("name"),
        "full_name": data.get("full_name"),
        "private": data.get("private"),
        "default_branch": data.get("default_branch"),
        "issues_enabled": data.get("has_issues"),
    }
    if not isinstance(values["repository_id"], int):
        raise github_controller_error("Repository response has no numeric id.")
    for key in ("owner", "name", "full_name", "default_branch"):
        if not isinstance(values[key], str) or not values[key]:
            raise github_controller_error(f"Repository response has no valid {key}.")
    for key in ("private", "issues_enabled"):
        if not isinstance(values[key], bool):
            raise github_controller_error(f"Repository response has no valid {key} flag.")
    return github_repository_identity(
        repository_id=values["repository_id"],
        owner=values["owner"],
        name=values["name"],
        full_name=values["full_name"],
        private=values["private"],
        default_branch=values["default_branch"],
        issues_enabled=values["issues_enabled"],
        push_allowed=bool(push_allowed),
    )


def _failed(name: str, exc: Exception) -> runtime_diagnostic_check:
    return runtime_diagnostic_check(
        name=name,
        ok=False,
        detail=str(exc) or exc.__class__.__name__,
    )


def _safe_error_detail(body: bytes) -> str:
    if not body:
        return "no response body"
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "non-JSON error response"
    if isinstance(value, Mapping):
        message = value.get("message")
        if isinstance(message, str) and message:
            return message
    return "GitHub API request failed"


def _slug(value: str) -> str:
    rendered = "".join(
        character.lower() if character.isalnum() else "-"
        for character in value.strip()
    )
    while "--" in rendered:
        rendered = rendered.replace("--", "-")
    rendered = rendered.strip("-")
    if not rendered:
        raise ValueError("Fixture namespace component must not be empty.")
    return rendered


def _urllib_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    payload: bytes | None,
) -> tuple[int, Mapping[str, str], bytes]:
    request = Request(
        url,
        data=payload,
        headers=dict(headers),
        method=method,
    )
    try:
        with urlopen(request, timeout=30.0) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()
    except URLError as exc:
        raise github_controller_error(
            f"Could not reach GitHub API: {exc.reason}"
        ) from exc
