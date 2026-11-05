# GitHub MCP Integration Qualification v1

This package is an **engineering qualification package**, not a behavioral ACMM experiment. Its
purpose is to prove that the same official remote GitHub MCP Server can be reconciled through the
native external-tool mechanisms of Hermes Agent, Open WebUI, and Agent Zero without introducing
GitHub- or MCP-specific branches into ACMM Core.

## Qualified external capability

The package targets the official remote GitHub MCP Server at
`https://api.githubcopilot.com/mcp/` and constrains the server-side tool surface to:

- `issue_read`
- `issue_write`
- `add_issue_comment`

The same allow-list is expressed again in native agent policy where the host supports a useful
second enforcement layer. This package intentionally does not emulate GitHub through package-owned
Python tools. The qualification manager also adds a native discovery check to `doctor`: Hermes uses
its MCP connection test command, Open WebUI uses its pinned tool-server verification endpoint, and
Agent Zero uses its pinned MCP server-detail endpoint.

## Credential

Set a GitHub personal access token in the host process environment before applying or diagnosing the
package:

```text
export ACMM_GITHUB_MCP_TOKEN='...'
```

The manifest stores only the **name** of this environment variable. The package-local integration
reads the value during subject reconciliation and redacts it from manager-returned status and doctor
data. Do not commit a token to this repository.

Use a dedicated qualification account/repository and the minimum GitHub permissions needed for the
selected issue operations. The final behavioral experiment will define its repository scope and
reset policy separately.

## Intended workflow

```text
acmm package validate ../acmm-experiments/github_mcp_integration_qualification_v1
acmm package install ../acmm-experiments/github_mcp_integration_qualification_v1
acmm package apply github_mcp_integration_qualification_v1
acmm env doctor --start-if-needed
acmm env down
```

Do **not** treat the placeholder Contract scenario as scientific data. It exists only because an
Experiment Package still carries a structurally complete Contract. A later qualification checkpoint
will add an explicit real GitHub issue target for end-to-end calls once connection discovery is clean
on all three pinned agents. `READY` therefore means the native client discovered exactly the three
expected MCP tools; it does not yet mean a behavioral GitHub issue mutation has been qualified.

## Ownership boundary

- Core owns generic integration loading, lifecycle composition, provenance, and subject management.
- This package owns GitHub MCP connection mechanics and host-specific reconciliation.
- The future behavioral package will own scientific task meaning, controlled GitHub state, and
  adjudication.

If this integration becomes useful to multiple experiments, it is a candidate for extraction into a
shared tool-integration distribution while preserving the same Core integration API.
