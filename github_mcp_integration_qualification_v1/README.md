# GitHub MCP Integration Qualification v1

This package is an engineering qualification package, not a behavioral ACMM experiment. It proves
that one pinned local deployment of GitHub's official MCP Server can be reconciled through the
native external-tool mechanisms of Hermes Agent, Open WebUI, and Agent Zero without adding GitHub-
or MCP-specific branches to ACMM Core.

## Local-pinned preset

The current preset is `local_pinned`. It owns one shared Docker resource using:

- image: `ghcr.io/github/github-mcp-server:v2.0.3`;
- transport: Streamable HTTP;
- subject-visible endpoint: `http://host.docker.internal:8082`;
- server-side tool allow-list: `issue_read`, `issue_write`, `add_issue_comment`.

The server is the official GitHub MCP bridge; authoritative repository and issue state remains on
GitHub.com. The MCP container does not receive the GitHub credential. Each native MCP client sends
the same bearer credential when it connects.

A future hosted preset can reuse the same integration identity, secret slot, scientific tool list,
and subject reconciliation language. Hosted-versus-local differences belong inside this integration,
not in Core or the Contract.

## Secret binding

The manifest declares one generic integration secret slot named `access_token`. The secret value and
its machine-local path are not part of the package or Contract.

For the current ACMM workstation, bind the existing token file once:

```text
chmod 600 ~/.config/acmm/github_mcp_access_token
acmm secret bind \
    github_mcp_integration_qualification_v1 \
    github_mcp \
    access_token \
    --file ~/.config/acmm/github_mcp_access_token
```

`acmm secret list` shows binding identities and source paths but never reads or prints secret values.
The local binding file defaults to `~/.config/acmm/secret-bindings.yaml` and contains only the source
path, not the credential.

## Intended qualification workflow

Do not run the placeholder Contract scenario as scientific data. Once the code checkpoint is merged,
the first live qualification will be:

```text
acmm package validate ~/acmm_experiments/github_mcp_integration_qualification_v1
acmm package install ~/acmm_experiments/github_mcp_integration_qualification_v1
acmm package apply github_mcp_integration_qualification_v1
acmm env status
acmm env doctor --start-if-needed
```

Package apply reconciles the shared MCP image/service definition before subject provisioning and
preserves the resource's prior running state. On a normal stopped environment, the image is pulled
if missing and the Compose definition is validated, but no stopped container is retained.
`env doctor --start-if-needed` temporarily creates/starts the shared MCP resource before native
subject discovery, keeps it available while all subject checks run, and removes the container again
afterward. The pinned Docker image remains cached; runtime container state is ephemeral.

## Ownership boundary

- Core owns generic integration loading, secret binding, shared-resource lifecycle, provenance, and
  subject management.
- This package owns GitHub MCP deployment mechanics, the local/hosted preset distinction, and
  host-specific native MCP reconciliation.
- The future behavioral experiment owns controlled GitHub state, scenarios, requirements, and
  adjudication.
