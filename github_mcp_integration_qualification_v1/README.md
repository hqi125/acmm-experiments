# GitHub MCP integration qualification v1

This package qualifies the official pinned local GitHub MCP Server as an ACMM integration before
it is used by the substantive Experiment 2 package. It is engineering qualification, not part of
the final research dataset.

The package has two qualification layers:

1. `acmm env doctor --start-if-needed` verifies that Hermes, Open WebUI, and Agent Zero each
   discover exactly `issue_read`, `issue_write`, and `add_issue_comment` through their native MCP
   client.
2. The single package run uses a trusted GitHub REST fixture to establish canonical issue state,
   lets the subject perform `issue_read -> add_issue_comment -> issue_read`, captures authoritative
   post-state, and restores the issue by deleting the qualification comment.

The target repository is `acmm-mcp-arena-experiment-2` under the GitHub account authenticated by
the package's `github_mcp:access_token` secret binding. The account login is resolved at run time;
it is not stored in the Contract.

The local MCP service remains pinned to `ghcr.io/github/github-mcp-server:v2.0.3`. Its container is
ephemeral; the image is cached locally and the GitHub repository remains the authoritative state.

A fine-grained GitHub token should be restricted to the dedicated qualification repository and
must provide GitHub Issues read/write access. The token remains in the local secret source file and
is never stored in this package.

Typical qualification flow from the Core repository is:

```bash
acmm package install ~/acmm_experiments/github_mcp_integration_qualification_v1
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
