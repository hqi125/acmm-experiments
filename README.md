# ACMM Experiment Packages

This directory is the EP-6 proof workspace for experiment artifacts that are independent of the
ACMM main repository. It is intended to become a separate version-controlled experiments repository;
ACMM consumes packages from filesystem paths and does not install them with `pip`.


## WSL workspace setup

If the Windows checkout is a sibling of the main repo at
`/mnt/d/MEng/4-Fall-2026/ece-699/acmm-experiments`, create a stable WSL link once:

```text
ln -s /mnt/d/MEng/4-Fall-2026/ece-699/acmm-experiments ~/acmm_experiments
```

Verify it with `readlink -f ~/acmm_experiments`. Keep the main repo and experiment-package repo as
separate Git roots; ACMM consumes package source through filesystem paths and copies immutable
revisions into its managed runtime store.

Experiment directories currently include:

- `minimal_agent_baseline_v1/` — contains the final 16-scenario Contract, package-owned structured
  scenario assets, deterministic no-integration runtime evaluators, and the completed 384-run
  acquisition/interpretation baseline.
- `github_mcp_integration_qualification_v1/` — an engineering-only qualification package for the
  first real external-tool integration. It reconciles the pinned local official GitHub MCP Server
  through each pinned agent's native MCP client, verifies exact native tool discovery, and performs
  a small real GitHub read-comment-read workflow with trusted REST pre/post-state observation. Its
  results are qualification evidence, not part of the final Experiment 2 research dataset.
- `github_mcp_project_workspace_v1/` - Experiment 2 implementation in progress. The package now
  contains the frozen 12-scenario Contract, pinned 43-tool GitHub MCP integration, separate
  subject/controller secret slots, and the trusted controller runtime/doctor foundation. Scenario
  fixture materialization and evaluators remain guarded, so scientific `acmm run` is not ready yet.

A normal workflow from the ACMM development environment is:

```text
acmm package validate ~/acmm_experiments/minimal_agent_baseline_v1
acmm package install ~/acmm_experiments/minimal_agent_baseline_v1
acmm package apply minimal_agent_baseline_v1
acmm run minimal_agent_baseline_v1 --preview
```

Development tests stay outside deployable package directories under `tests/<package-id>/`. This keeps
package artifacts focused on material required by the Core-managed store while retaining package-specific
regression ownership. From the ACMM virtual environment, run:

```text
pytest ~/acmm_experiments
```

## Local secrets

Do not place provider API keys or other live credentials in Experiment Packages. Local `.env`,
`secrets/`, and common API-key filenames are ignored as a last-resort safeguard, but secret values
should live outside this repository and be exposed to ACMM only through the global secret-binding
registry. Initialize the local store with `acmm secret init`; the default source directory is
`~/.config/acmm/secrets/` and the versioned registry remains
`~/.config/acmm/secret-bindings.yaml`. Older registry formats are never upgraded implicitly: run
`acmm secret upgrade` explicitly before using normal binding/runtime operations. If this repo is
hosted on GitHub, enable Secret Protection / Push Protection when available.
