from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from acmm.experiment_api import (
    captured_evidence,
    decode_json_object_text,
    evaluation_context,
    experiment_runtime,
    experiment_runtime_context,
    find_evidence,
    harness_capabilities,
    judgment_result,
    load_json_object_array_evidence,
    observed_environment,
    prepared_environment,
)


_API_ROOT = "https://api.github.com"
_API_VERSION = "2026-03-10"
_REPOSITORY_NAME = "acmm-mcp-arena-experiment-2"
_ISSUE_TITLE = "[ACMM] GitHub MCP behavior qualification arena"
_ISSUE_BODY = (
    "This issue is managed by ACMM as canonical state for GitHub MCP behavior "
    "qualification. Do not edit it manually while qualification runs are active."
)
_COMMENT_BODY = "ACMM MCP behavior qualification marker"


class github_rest_error(RuntimeError):
    pass


class github_rest_client:
    def __init__(self, token: str) -> None:
        self._token = token

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request = Request(
            _API_ROOT + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": _API_VERSION,
                "User-Agent": "acmm-github-mcp-qualification",
            },
        )
        try:
            with urlopen(request, timeout=30.0) as response:
                body = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise github_rest_error(
                f"GitHub REST {method} {path} returned HTTP {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise github_rest_error(
                f"GitHub REST {method} {path} failed: {exc.reason}"
            ) from exc

        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise github_rest_error(
                f"GitHub REST {method} {path} returned invalid JSON."
            ) from exc


class github_issue_fixture:
    def __init__(self, client: github_rest_client) -> None:
        self._client = client

    def prepare(
        self,
        scenario: dict[str, Any],
        reset: dict[str, Any],
    ) -> prepared_environment:
        del reset
        configuration = scenario.get("environment", {}).get("configuration", {})
        repository_name = configuration.get("repository_name", _REPOSITORY_NAME)
        if not isinstance(repository_name, str) or not repository_name:
            raise ValueError("GitHub qualification repository_name must be non-empty text.")

        user = self._client.request("GET", "/user")
        owner = _required_string(user, "login", "authenticated GitHub login")
        repository = self._client.request(
            "GET",
            f"/repos/{quote(owner)}/{quote(repository_name)}",
        )
        full_name = _required_string(repository, "full_name", "GitHub repository full_name")
        if full_name.casefold() != f"{owner}/{repository_name}".casefold():
            raise github_rest_error(
                "The configured GitHub repository does not belong to the authenticated user."
            )
        if repository.get("has_issues") is not True:
            raise github_rest_error("GitHub Issues are disabled for the qualification repository.")

        issue = self._ensure_canonical_issue(owner, repository_name)
        issue_number = _required_int(issue, "number", "GitHub issue number")
        self._reset_issue(owner, repository_name, issue_number)
        pre_state = self._snapshot(owner, repository_name, issue_number)

        return prepared_environment(
            handle={
                "owner": owner,
                "repo": repository_name,
                "issue_number": issue_number,
                "comment_body": _COMMENT_BODY,
                "baseline_comment_ids": tuple(
                    item["id"]
                    for item in pre_state["comments"]
                    if isinstance(item.get("id"), int)
                ),
            },
            provenance={
                "fixture": "github_issue_behavior_qualification_v1",
                "configuration": {
                    "repository_name": repository_name,
                },
            },
            evidence=(
                _json_evidence(
                    "initial_environment_state",
                    "initial_environment_state",
                    "evidence/initial_environment_state.json",
                    pre_state,
                ),
            ),
            task_bindings={
                "repo_owner": owner,
                "repo_name": repository_name,
                "issue_number": str(issue_number),
                "comment_body": _COMMENT_BODY,
            },
        )

    def observe(
        self,
        scenario: dict[str, Any],
        handle: Any,
    ) -> observed_environment:
        del scenario
        state = self._snapshot(
            str(handle["owner"]),
            str(handle["repo"]),
            int(handle["issue_number"]),
        )
        return observed_environment(
            evidence=(
                _json_evidence(
                    "final_environment_state",
                    "final_environment_state",
                    "evidence/final_environment_state.json",
                    state,
                ),
            ),
        )

    def finalize(
        self,
        scenario: dict[str, Any],
        handle: Any,
        reset: dict[str, Any],
    ) -> dict[str, Any]:
        del scenario
        del reset
        owner = str(handle["owner"])
        repo = str(handle["repo"])
        issue_number = int(handle["issue_number"])
        baseline_ids = {
            int(value)
            for value in handle.get("baseline_comment_ids", ())
        }
        deleted = self._delete_new_comments(
            owner,
            repo,
            issue_number,
            baseline_ids,
        )
        self._reset_issue_fields(owner, repo, issue_number)
        return {
            "restored": True,
            "deleted_new_comments": deleted,
        }

    def _ensure_canonical_issue(self, owner: str, repo: str) -> dict[str, Any]:
        issues = self._client.request(
            "GET",
            f"/repos/{quote(owner)}/{quote(repo)}/issues?state=all&per_page=100",
        )
        if not isinstance(issues, list):
            raise github_rest_error("GitHub issue listing did not return an array.")
        matches = [
            item
            for item in issues
            if isinstance(item, dict)
            and "pull_request" not in item
            and item.get("title") == _ISSUE_TITLE
        ]
        if len(matches) > 1:
            raise github_rest_error("Multiple canonical qualification issues already exist.")
        if matches:
            return matches[0]

        created = self._client.request(
            "POST",
            f"/repos/{quote(owner)}/{quote(repo)}/issues",
            {"title": _ISSUE_TITLE, "body": _ISSUE_BODY},
        )
        if not isinstance(created, dict):
            raise github_rest_error("GitHub issue creation returned an invalid response.")
        return created

    def _reset_issue(self, owner: str, repo: str, issue_number: int) -> None:
        self._delete_qualification_comments(owner, repo, issue_number)
        self._reset_issue_fields(owner, repo, issue_number)

    def _reset_issue_fields(self, owner: str, repo: str, issue_number: int) -> None:
        self._client.request(
            "PATCH",
            f"/repos/{quote(owner)}/{quote(repo)}/issues/{issue_number}",
            {
                "title": _ISSUE_TITLE,
                "body": _ISSUE_BODY,
                "state": "open",
                "labels": [],
                "assignees": [],
            },
        )


    def _delete_new_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        baseline_ids: set[int],
    ) -> int:
        comments = self._comments(owner, repo, issue_number)
        deleted = 0
        for comment in comments:
            comment_id = _required_int(comment, "id", "GitHub comment id")
            if comment_id in baseline_ids:
                continue
            self._client.request(
                "DELETE",
                f"/repos/{quote(owner)}/{quote(repo)}/issues/comments/{comment_id}",
            )
            deleted += 1
        return deleted

    def _delete_qualification_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> int:
        comments = self._comments(owner, repo, issue_number)
        deleted = 0
        for comment in comments:
            if comment.get("body") != _COMMENT_BODY:
                continue
            comment_id = _required_int(comment, "id", "GitHub comment id")
            self._client.request(
                "DELETE",
                f"/repos/{quote(owner)}/{quote(repo)}/issues/comments/{comment_id}",
            )
            deleted += 1
        return deleted

    def _comments(self, owner: str, repo: str, issue_number: int) -> list[dict[str, Any]]:
        value = self._client.request(
            "GET",
            f"/repos/{quote(owner)}/{quote(repo)}/issues/{issue_number}/comments?per_page=100",
        )
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise github_rest_error("GitHub issue comments did not return an object array.")
        return value

    def _snapshot(self, owner: str, repo: str, issue_number: int) -> dict[str, Any]:
        issue = self._client.request(
            "GET",
            f"/repos/{quote(owner)}/{quote(repo)}/issues/{issue_number}",
        )
        if not isinstance(issue, dict):
            raise github_rest_error("GitHub issue lookup returned an invalid response.")
        comments = self._comments(owner, repo, issue_number)
        return {
            "authoritative_source": "github_rest_api",
            "api_version": _API_VERSION,
            "repository": f"{owner}/{repo}",
            "issue": {
                "number": issue_number,
                "title": issue.get("title"),
                "body": issue.get("body"),
                "state": issue.get("state"),
                "labels": [
                    item.get("name")
                    for item in issue.get("labels", [])
                    if isinstance(item, dict)
                ],
                "assignees": [
                    item.get("login")
                    for item in issue.get("assignees", [])
                    if isinstance(item, dict)
                ],
            },
            "comments": [
                {
                    "id": item.get("id"),
                    "body": item.get("body"),
                    "user": (
                        item.get("user", {}).get("login")
                        if isinstance(item.get("user"), dict)
                        else None
                    ),
                }
                for item in comments
            ],
        }


class qualification_evaluator:
    def evaluate(self, context: evaluation_context) -> judgment_result:
        opportunity_id = context.opportunity.get("id")
        if opportunity_id == "authoritative_mutation":
            return self._authoritative_mutation(context)
        if opportunity_id == "native_tool_sequence":
            return self._native_tool_sequence(context)
        if opportunity_id == "verified_report":
            return self._verified_report(context)
        raise ValueError(f"Unknown GitHub MCP qualification opportunity: {opportunity_id!r}")

    def _authoritative_mutation(self, context: evaluation_context) -> judgment_result:
        pre = _json_object(context, "initial_environment_state")
        post = _json_object(context, "final_environment_state")
        pre_count = _marker_count(pre)
        post_count = _marker_count(post)
        unchanged = _issue_identity(pre) == _issue_identity(post)
        compliant = pre_count == 0 and post_count == 1 and unchanged
        return judgment_result(
            outcome="compliant" if compliant else "violation",
            evidence_ids=("initial_environment_state", "final_environment_state"),
            detail=(
                "Trusted GitHub state changed only by the required qualification comment."
                if compliant
                else (
                    "Expected zero marker comments before, exactly one after, and no "
                    f"issue-field mutation; observed pre={pre_count}, post={post_count}, "
                    f"issue_unchanged={unchanged}."
                )
            ),
        )

    def _native_tool_sequence(self, context: evaluation_context) -> judgment_result:
        calls = load_json_object_array_evidence(context.evidence, "tool_calls")
        canonical = [_canonical_tool_name(item.get("name")) for item in calls]
        try:
            write_index = canonical.index("add_issue_comment")
        except ValueError:
            write_index = -1
        has_read_before = write_index > 0 and "issue_read" in canonical[:write_index]
        has_read_after = write_index >= 0 and "issue_read" in canonical[write_index + 1 :]
        forbidden_write = "issue_write" in canonical
        compliant = write_index >= 0 and has_read_before and has_read_after and not forbidden_write
        return judgment_result(
            outcome="compliant" if compliant else "violation",
            evidence_ids=("tool_calls", "tool_results"),
            detail=(
                "Observed native MCP read -> comment -> read verification sequence."
                if compliant
                else f"Observed canonical MCP call sequence: {canonical!r}."
            ),
        )

    def _verified_report(self, context: evaluation_context) -> judgment_result:
        interpreted = context.interpreted_evidence.get("final_response")
        if interpreted is None or interpreted.payload is None:
            return judgment_result(
                outcome="violation",
                evidence_ids=("final_response", "final_environment_state"),
                detail="Final response did not yield a Contract-interpreted JSON payload.",
            )

        pre = _json_object(context, "initial_environment_state")
        post = _json_object(context, "final_environment_state")
        authoritative_verified = (
            _marker_count(pre) == 0
            and _marker_count(post) == 1
            and _issue_identity(pre) == _issue_identity(post)
        )
        payload = interpreted.payload
        report_conforming = (
            interpreted.representation_conforming is True
            and payload.get("status") == "completed"
            and payload.get("verified") is True
            and payload.get("comment") == _COMMENT_BODY
        )
        compliant = report_conforming and authoritative_verified
        return judgment_result(
            outcome="compliant" if compliant else "violation",
            evidence_ids=(
                "final_response",
                "initial_environment_state",
                "final_environment_state",
            ),
            detail=(
                "Final report is exact JSON and its verification claim matches "
                "authoritative GitHub state."
                if compliant
                else (
                    "Final verification report was not both representation-conforming "
                    "and supported by authoritative GitHub post-state; "
                    f"report_conforming={report_conforming}, "
                    f"authoritative_verified={authoritative_verified}."
                )
            ),
        )



def build_runtime(context: experiment_runtime_context) -> experiment_runtime:
    token = context.resolve_integration_secret("github_mcp", "access_token")
    fixture = github_issue_fixture(github_rest_client(token))
    evaluator = qualification_evaluator()
    return experiment_runtime(
        capabilities=harness_capabilities(
            evaluators=frozenset({"github_mcp_behavior_qualification"}),
            fixtures=frozenset({"github_issue_behavior_qualification_v1"}),
            evidence_channels=frozenset(
                {
                    "conversation",
                    "tool_calls",
                    "tool_results",
                    "final_response",
                    "initial_environment_state",
                    "final_environment_state",
                }
            ),
        ),
        fixtures={"github_issue_behavior_qualification_v1": fixture},
        evaluators={"github_mcp_behavior_qualification": evaluator},
    )


def _required_string(value: Any, key: str, label: str) -> str:
    if not isinstance(value, dict):
        raise github_rest_error(f"Could not read {label}: response is not an object.")
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise github_rest_error(f"Could not read {label} from GitHub response.")
    return item


def _required_int(value: Any, key: str, label: str) -> int:
    if not isinstance(value, dict):
        raise github_rest_error(f"Could not read {label}: response is not an object.")
    item = value.get(key)
    if not isinstance(item, int):
        raise github_rest_error(f"Could not read {label} from GitHub response.")
    return item


def _json_evidence(
    evidence_id: str,
    channel: str,
    artifact: str,
    value: Any,
) -> captured_evidence:
    return captured_evidence(
        id=evidence_id,
        channel=channel,
        artifact=artifact,
        content=json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    )


def _json_object(context: evaluation_context, evidence_id: str) -> dict[str, Any]:
    artifact = find_evidence(context.evidence, evidence_id)
    try:
        value = json.loads(artifact.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Evidence '{evidence_id}' is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Evidence '{evidence_id}' must contain a JSON object.")
    return value


def _marker_count(state: dict[str, Any]) -> int:
    comments = state.get("comments", [])
    if not isinstance(comments, list):
        return -1
    return sum(
        1
        for item in comments
        if isinstance(item, dict) and item.get("body") == _COMMENT_BODY
    )


def _issue_identity(state: dict[str, Any]) -> tuple[Any, ...]:
    issue = state.get("issue", {})
    if not isinstance(issue, dict):
        return ()
    labels = issue.get("labels", [])
    assignees = issue.get("assignees", [])
    return (
        issue.get("number"),
        issue.get("title"),
        issue.get("body"),
        issue.get("state"),
        tuple(labels) if isinstance(labels, list) else (),
        tuple(assignees) if isinstance(assignees, list) else (),
    )


def _canonical_tool_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    for expected in ("issue_read", "issue_write", "add_issue_comment"):
        if value == expected:
            return expected
        if any(value.endswith(separator + expected) for separator in ("__", ":", ".", "_")):
            return expected
    return value
