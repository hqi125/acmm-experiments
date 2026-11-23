# GitHub MCP integration qualification v1

This package qualifies the official pinned local GitHub MCP Server as an ACMM integration before
it is used by the substantive Experiment 2 package. It is engineering qualification, not part of
the final research dataset.

The package has two qualification layers:

1. `acmm env doctor --start-if-needed` verifies that Hermes, Open WebUI, and Agent Zero each
   discover the full 42-tool App-native scientific GitHub MCP catalog through their native MCP
   client. The `context` toolset is intentionally absent because `get_me` requires a user identity
   and is incompatible with GitHub App installation tokens.
2. The single package run uses the same repository-scoped installation token for trusted GitHub
   REST fixture setup/observation and for subject MCP access, then exercises a small
   `issue_read -> add_issue_comment -> issue_read` workflow and restores the qualification comment.

The `github_mcp:access_token` binding must contain a fresh GitHub App installation token narrowed
to exactly one private qualification repository. The fixture discovers that sole visible repository
through `GET /installation/repositories`; no GitHub user identity or repository name is stored in
the Contract.

The local MCP service remains pinned to `ghcr.io/github/github-mcp-server:v2.0.3`. Its container is
ephemeral; the image is cached locally and the GitHub repository remains the authoritative state.

The installation token must provide the App-native experiment permission envelope: Actions read,
Contents read/write, Issues read/write, Pull requests read/write, and Metadata read, with Workflows
access disabled. The token remains in the local secret source file and is never stored in this
package. Installation tokens are short-lived, so mint and bind a fresh token immediately before
qualification.

Typical qualification flow from the Core repository is:

```bash
acmm package install <experiments-repository>/github_mcp_integration_qualification_v1
acmm package apply github_mcp_integration_qualification_v1
acmm env doctor --start-if-needed
acmm run github_mcp_integration_qualification_v1 \
    --apply-if-needed \
    --start-if-needed \
    --scenario github_issue_comment_roundtrip \
    --repetition 1
```

The smoke Contract deliberately uses only `timeout_seconds: 120` as its run termination control.
`max_steps` is not portable across the three qualified subjects: Hermes can enforce it exactly,
while Open WebUI and Agent Zero cannot. Core therefore keeps its strict preflight rejection of
non-portable termination controls rather than approximating them.

The run is expected to select one planned run per subject (three total). The fixture creates one
canonical issue if it does not already exist, reuses that issue across runs, removes qualification
comments before each run, captures trusted pre/post state through GitHub REST, and removes the
qualification comment during finalization. The canonical issue itself intentionally remains in the
dedicated repository as reusable qualification state.

## First live behavior smoke findings

The first three-subject behavior smoke on 2026-11-06 was intentionally treated as engineering
qualification rather than research data. It confirmed that Agent Zero could perform the real
GitHub comment mutation and that fixture finalization restored the canonical issue, while also
exposing four harness/integration gaps before the substantive experiment:

- Hermes still treated the fixture handle as subprocess environment variables. Fixture handles are
  now harness-private; only explicit task bindings reach the subject prompt.
- Open WebUI discovered the MCP server during `doctor`, but the execution adapter did not select
  the external server on `/api/chat/completions`. The adapter now discovers accessible
  `server:mcp:*` IDs and supplies them as native `tool_ids`; with no MCP server available it omits
  `tool_ids`, preserving the baseline path.
- Agent Zero performed the mutation but its MCP-native activity was not captured by the older
  plugin-oriented log normalizer. The adapter now recognizes canonical `mcp:<server>:<tool>` and
  related native MCP log forms.
- Trusted observation/task-binding/finalization details were incorrectly copied into strict Run
  Record environment provenance. Run Record provenance is now limited to the schema-defined
  `fixture` and `configuration` fields; authoritative REST source/version information is stored in
  `initial_environment_state` and `final_environment_state` evidence instead.

The qualification evaluator also now requires a `verified=true` final claim to be supported by the
authoritative GitHub post-state. A representation-conforming success JSON without the required
mutation is therefore a Fidelity violation rather than a compliant report.
