# ACMM Experiment Packages

This repository contains deployable Experiment Packages used by the Agent Compliance Metric Model
(ACMM) Core runtime. It is intentionally separate from the Core repository: Core provides the
execution, persistence, campaign, adjudication, and analysis infrastructure, while this repository
owns experiment contracts, package-specific assets, evaluators, integrations, and design records.

Experiment Packages are consumed from filesystem paths and installed into Core's managed package
store. They are not Python packages and are not installed with `pip`.

## Repository contents

| Package | Role | Scientific status |
| --- | --- | --- |
| [`minimal_agent_baseline_v1/`](minimal_agent_baseline_v1/README.md) | Experiment 1: controlled minimal-agent baseline with no experiment-provided tools | Frozen; 384-run acquisition and strict analysis complete |
| [`github_mcp_integration_qualification_v1/`](github_mcp_integration_qualification_v1/README.md) | Engineering qualification for the GitHub MCP integration | Qualification evidence only; not part of an experiment dataset |
| [`github_mcp_project_workspace_v1/`](github_mcp_project_workspace_v1/README.md) | Experiment 2: shared rich GitHub MCP project workspace | Frozen; 288-run acquisition complete |

Development tests live under [`tests/`](tests/README.md), outside deployable package directories, so
test-only maintenance does not silently change an installed package revision.

## Using this repository with ACMM Core

Choose any local checkout path and refer to it explicitly. The examples below use the neutral
placeholder `<experiments-repository>` rather than assuming a particular Windows, WSL, or home-directory
layout.

A typical package lifecycle is:

```text
acmm package validate <experiments-repository>/minimal_agent_baseline_v1
acmm package install <experiments-repository>/minimal_agent_baseline_v1
acmm package apply minimal_agent_baseline_v1
acmm run minimal_agent_baseline_v1 --preview
```

Core installs a content-addressed package revision into its managed store. Scientific campaigns should
therefore use the intended immutable installed revision rather than editing package source during
execution. Consult the Core repository documentation for the complete `acmm run`, `acmm campaign`,
package-upgrade, adjudication, and export workflows.

Run repository-wide development tests from the ACMM development environment with:

```text
pytest <experiments-repository>
```

## Package-specific manual setup

Package installation is not the same as external-provider provisioning. The packages in this repository have
different operator requirements:

| Package | Manual/external setup beyond ACMM Core |
| --- | --- |
| `minimal_agent_baseline_v1` | No experiment-specific external capability. Prepare the Core subject cohort and selected LLM baseline, then use Core readiness checks. |
| `github_mcp_integration_qualification_v1` | A dedicated private GitHub qualification repository plus a fresh repository-scoped GitHub App installation token. The package does not create the App or mint this token for you. |
| `github_mcp_project_workspace_v1` | A dedicated GitHub experiment environment, trusted controller credential, GitHub App and private key, App installation, diagnostic reference repository/identifiers, Git, OpenSSL, and the package's pinned MCP build/runtime prerequisites. |

For GitHub packages, do not infer readiness from `acmm package install` alone. Bind the declared secrets,
apply the package, run `acmm env doctor`, and complete any package-specific live qualification described in
the package README/reproduction guide before scientific execution.

## Secrets

Do not commit provider API keys, GitHub tokens, private keys, or other live credentials to this
repository. Package manifests declare **secret slots**; secret values belong in Core's local secret
store and binding registry.

Initialize the local Core secret store with:

```text
acmm secret init
```

By default, local secret source files live under `~/.config/acmm/secrets/`, and the versioned binding
registry lives at `~/.config/acmm/secret-bindings.yaml`. Older registry formats must be upgraded
explicitly with `acmm secret upgrade` before normal binding/runtime operations.

Local `.env`, `secrets/`, and common key filenames are ignored as a last-resort safeguard, but ignore
rules are not a substitute for keeping credentials outside version control. If the repository is hosted
on GitHub, enable the repository's available secret-scanning and push-protection features.

## Reproduction notes

Experiment 1 is self-contained at the experiment-tool level. Experiment 2 is materially different: it
uses a real GitHub account/App, creates private repositories, drives sustained GitHub API/MCP/Git
traffic, and can take many hours for a full campaign. Read
[`github_mcp_project_workspace_v1/REPRODUCTION.md`](github_mcp_project_workspace_v1/REPRODUCTION.md)
**before** attempting Experiment 2. In particular, do not use a primary everyday personal GitHub
account for Experiment 2 execution.
