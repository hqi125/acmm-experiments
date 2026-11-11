from pathlib import Path

from acmm.experiment_package import load_experiment_package


REPO_ROOT = Path(__file__).resolve().parents[2]
QUALIFICATION = REPO_ROOT / "github_mcp_integration_qualification_v1"
# Filled after repository test-boundary refactor.
QUALIFICATION_PACKAGE_SHA256 = "d8408fb446fa8306c1d21438b94696563aaf6774ecf9782073cbcbc773c75f8b"


def test_github_mcp_qualification_package_contract_is_app_native() -> None:
    package = load_experiment_package(QUALIFICATION)

    assert package.package_sha256 == QUALIFICATION_PACKAGE_SHA256
    assert package.schema_version == "0.2"
    assert package.experiment_id == "github_mcp_integration_qualification_v1"
    assert package.runtime is not None
    assert len(package.integrations) == 1
    integration = package.integrations[0]
    assert integration.integration_id == "github_mcp"
    assert tuple(secret.secret_id for secret in integration.secrets) == ("access_token",)
    assert tuple(integration.configuration["tools"]) == (
        "actions_get",
        "actions_list",
        "add_comment_to_pending_review",
        "add_issue_comment",
        "add_reply_to_pull_request_comment",
        "create_branch",
        "create_or_update_file",
        "create_pull_request",
        "delete_file",
        "get_commit",
        "get_file_contents",
        "get_job_logs",
        "get_label",
        "get_latest_release",
        "get_release_by_tag",
        "get_repository_tree",
        "get_tag",
        "issue_read",
        "issue_write",
        "label_write",
        "list_branches",
        "list_commits",
        "list_issues",
        "list_label",
        "list_pull_requests",
        "list_releases",
        "list_repository_collaborators",
        "list_tags",
        "merge_pull_request",
        "pull_request_read",
        "pull_request_review_write",
        "push_files",
        "search_code",
        "search_commits",
        "search_issues",
        "search_pull_requests",
        "search_repositories",
        "search_users",
        "sub_issue_write",
        "update_issue_comment",
        "update_pull_request",
        "update_pull_request_branch",
    )
