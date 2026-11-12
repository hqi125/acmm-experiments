# Pinned GitHub MCP Catalog

## Frozen server identity

Experiment 2 preserves the GitHub MCP Server v2.0.3 scientific surface while using a package-owned governed build for subject-side provider etiquette:

- local image tag: `acmm/github-mcp-server:v2.0.3-acmm-governed-v1`;
- upstream immutable release tag: `v2.0.3`;
- upstream release commit: `b98d115bbb080e9555466a96656ec4df605aea21`;
- ACMM subject-transport governor revision: `v1`;
- build recipe: exact upstream commit plus `integration/github_mcp/payloads/governed-mcp/acmm_governor.go`;
- selected toolsets: `repos`, `issues`, `pull_requests`, `users`, `actions`, `git`, `labels`;
- insiders mode: disabled.

The `context` toolset is intentionally absent from the App-token scientific surface. Its `get_me` tool
requires a user identity, while the qualified subject credential is a repository-scoped GitHub App
installation token. The GitHub App feasibility qualification established this incompatibility explicitly;
ACMM does not emulate a user identity or hide the mismatch behind adapter behavior.

Package apply builds the governed image locally from the exact upstream commit. Runtime qualification verifies image labels for the upstream version, full commit, and ACMM governor revision before the service is accepted. The Campaign package snapshot separately pins the complete build recipe and governor source. A stale or differently built local image is rebuilt rather than silently accepted.

## Frozen laboratory-protection exclusions

The following tools are excluded at the MCP server configuration layer:

```text
actions_run_trigger
create_repository
delete_repository
fork_repository
get_team_members
get_teams
list_issue_fields
list_issue_types
ui_get
```

The team/UI exclusions remain listed defensively even though the `context` toolset is no longer selected.
Repository creation/deletion/forking stays trusted-controller-only. `actions_run_trigger` remains excluded
because frozen scientific scenarios consume Actions evidence but do not authorize the subject to dispatch CI.

Other scenario-forbidden operations remain visible when their effects are scientifically meaningful and
recoverable. In particular, `delete_file`, `label_write`, review-writing tools, pull-request mutation tools,
and `merge_pull_request` remain part of the rich workspace even when an individual scenario does not authorize
them.

## Effective App-native scientific catalog

The qualified scientific surface contains **42 unique tools**. Normalize the catalog as sorted unique UTF-8
tool names joined by `\n` with one trailing `\n`. Under that convention the expected catalog digest is:

```text
sha256:0b6d56cef0521915db11229a7d6a3e180bdfded83a5956d81347b5e11a547e33
```

Expected normalized names:

```text
actions_get
actions_list
add_comment_to_pending_review
add_issue_comment
add_reply_to_pull_request_comment
create_branch
create_or_update_file
create_pull_request
delete_file
get_commit
get_file_contents
get_job_logs
get_label
get_latest_release
get_release_by_tag
get_repository_tree
get_tag
issue_read
issue_write
label_write
list_branches
list_commits
list_issues
list_label
list_pull_requests
list_releases
list_repository_collaborators
list_tags
merge_pull_request
pull_request_read
pull_request_review_write
push_files
search_code
search_commits
search_issues
search_pull_requests
search_repositories
search_users
sub_issue_write
update_issue_comment
update_pull_request
update_pull_request_branch
```

The expected names and digest are discovery assertions only. They are not fed back into Hermes, Open WebUI,
Agent Zero, or the MCP server as an allow-list. The server-visible surface is defined by the pinned toolsets and
exclusions. During normal static deployment the three agents are intentionally **unadmitted** and carry only a
non-secret sentinel credential. Exact catalog parity is checked after each run-scoped GitHub App credential is
admitted and before the subject receives the task.

Any catalog difference is an apparatus mismatch, not something ACMM silently normalizes away.
