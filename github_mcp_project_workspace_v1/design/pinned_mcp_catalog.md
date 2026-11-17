# Pinned GitHub MCP Catalog

## Frozen server identity

Experiment 2 preserves the qualified 42-tool scientific surface while rebasing the server implementation to GitHub MCP Server v2.1.0 plus the maintained ACMM governor fork:

- local image tag: `acmm/github-mcp-server:v2.1.0-acmm-governed-v2`;
- ACMM source repository: `https://github.com/hqi125/acmm-github-mcp-server.git`;
- ACMM source commit: the exact full SHA-1 pinned by `local_service.source_commit` in `experiment-package.yaml`;
- upstream immutable release tag: `v2.1.0`;
- upstream release commit: `4bcdcdf8d7beee98c9448e73e257308280924cc4`;
- ACMM subject-transport governor revision: `v2`;
- build recipe: fetch the exact maintained-fork source commit, verify `HEAD`, and build that source tree's committed Dockerfile with explicit upstream/source/governor provenance arguments;
- selected toolsets: `repos`, `issues`, `pull_requests`, `users`, `actions`, `git`, `labels`;
- feature flags: explicitly empty;
- insiders mode: explicitly disabled.

The `context` toolset is intentionally absent from the App-token scientific surface. Its `get_me` tool
requires a user identity, while the qualified subject credential is a repository-scoped GitHub App
installation token. The GitHub App feasibility qualification established this incompatibility explicitly;
ACMM does not emulate a user identity or hide the mismatch behind adapter behavior.

The v2.1.0 source adds capabilities outside the frozen surface, including a separate `stargazers` toolset and feature-gated repository/issue/pull-request additions. They do not enter Experiment 2 because the selected toolset set is unchanged, `GITHUB_FEATURES` is empty, and insiders mode is disabled. The expected normalized 42-tool names and digest therefore remain the scientific acquisition assertion rather than being silently expanded during the rebase.

Package apply fetches the exact ACMM source commit from the maintained fork and verifies the checkout before building. Runtime qualification verifies image labels for the upstream version, upstream full commit, ACMM source full commit, and governor revision before the service is accepted. The Campaign package snapshot pins the complete integration configuration. A stale or differently built local image is rebuilt rather than silently accepted.

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
exclusions. During normal static deployment all three agents are intentionally **unadmitted**. Hermes and Open WebUI
carry only a non-secret sentinel credential; Agent Zero starts with no GitHub MCP server configured so startup cannot
launch discovery against an unusable static server. During an active Agent Zero subject slice, per-run unadmission is
established by provider revocation of the preceding repository-scoped App token rather than by rewriting MCP settings
after every run; this prevents stale asynchronous catalog refreshes from racing the next admission. The revoked token
has no usable provider authority, the next run replaces it exactly once, and subject release removes the GitHub MCP
server before shutdown.
Exact catalog parity is checked after every run-scoped GitHub App credential is admitted and before the subject
receives the task.

Any catalog difference is an apparatus mismatch, not something ACMM silently normalizes away.
