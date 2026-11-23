# Experiment 2 Reproduction and Execution Safety

This document covers the operational boundary for reproducing
`github_mcp_project_workspace_v1`. Read it before creating credentials, attaching a GitHub App, or
starting a scientific campaign.

## Read this first: use an isolated GitHub environment

> **Never use your primary everyday personal GitHub account for Experiment 2 execution.**
>
> Experiment 2 is a live-provider workload. It creates and deletes private repositories, creates and
> mutates issues/PRs/branches/comments and CI-related state, drives Git smart-protocol traffic, and sends
> sustained REST/MCP requests. A complete 288-run campaign is intentionally substantial and can occupy
> the provider plane for many hours.

Use a **dedicated experiment GitHub account** or a similarly isolated organization/account arrangement
whose repositories, GitHub App, quotas, notifications, and operational traffic are not needed for normal
daily work. Do not attach the experiment App broadly to unrelated repositories.

Do not run multiple Experiment 2 campaigns concurrently against the same GitHub account, App installation,
or equivalent provider plane. GitHub recommends serial request behavior to reduce secondary-rate pressure,
and its secondary limits include concurrency-sensitive behavior. Concurrency also changes the traffic shape
seen by ACMM and can contaminate the provider-pressure condition being measured.

The package's sourced provider recommendations and ACMM safety margins are documented in
[`design/provider_rate_policy_sources.md`](design/provider_rate_policy_sources.md). Provider response
headers and explicit recovery guidance remain authoritative at runtime.

## What the experiment touches

The trusted apparatus and subject runs use real GitHub infrastructure. Depending on the scenario, the
apparatus may create or manipulate:

- private repositories and Git refs;
- source/configuration/documentation files;
- issues, labels, comments, and project-state metadata;
- pull requests, branches, review state, and comments;
- deterministic GitHub Actions workflows/runs used as scenario evidence;
- repository-scoped GitHub App installation-token authority;
- Git clone/fetch/push/`ls-remote` traffic through the package's Git content plane.

Repository lifecycle and fixture mutation are intentionally controlled by trusted package code, but this
is still real provider activity. Treat the experiment environment as disposable laboratory infrastructure.

## Frozen apparatus identity versus your reproduction

The checked-in package records the original study's concrete apparatus identity, including GitHub App,
repository, MCP-fork, image, and source-commit provenance. Those values are **not secret credentials**, but
they are also not an invitation to reuse the original study infrastructure.

A public reproduction should provision its own dedicated GitHub account/App/repository environment. If
that requires changing package-owned apparatus identifiers or configuration, install that change as a
**new package revision/digest**. Do not edit a frozen installed revision in place and then describe it as
the original acquisition package.

Preserve the scientific semantics when creating a reproduction revision: the twelve scenarios, capability
envelope, subject configuration, repetitions, evaluation predicates, and provider-control behavior should
remain equivalent unless the purpose of the new study is explicitly to change them.

## Required secret slots

`experiment-package.yaml` declares two required Experiment-scoped secret slots:

| Secret slot | Purpose | Exposure rule |
| --- | --- | --- |
| `controller_access_token` | Trusted repository lifecycle, fixture setup/observation, and selected-repository App-installation management | Trusted apparatus only; never subject-visible |
| `github_app_private_key` | Mint short-lived GitHub App installation tokens | Trusted apparatus only; never committed to package source |

Store secret values through the ACMM Core secret registry. Do not place PATs, private keys, installation
tokens, `.env` files, or copied credential material inside this repository.

Scientific subject runs receive only fresh, repository-scoped App installation-token authority for the
active materialized repository. Run tokens are short-lived and are not package source data.

## GitHub App and repository isolation

Provision a dedicated GitHub App with only the permission envelope required by the experiment. The frozen
scientific capability model uses Metadata read, Contents read/write, Issues read/write, Pull requests
read/write, and Actions read, while excluding Workflows and repository/administrative authority from the
subject credential.

Keep the App installation restricted to experiment-owned private repositories. The trusted controller is
responsible for attaching/detaching the active materialized repository and for minting fresh one-repository
installation tokens. Do not broaden the App installation to unrelated personal or work repositories merely
to simplify setup.

## Provider traffic and duration

The package deliberately serializes and governs provider-facing traffic rather than trying to maximize
throughput. That means a full campaign should be expected to take a long time. Provider-directed cooldowns,
APP suspensions, Event-PPH admission, deterministic CI convergence, repository materialization/restoration,
and trusted pre/post observation all add legitimate wall-clock time.

Do not remove or shorten pacing/cooldown behavior just to make the campaign finish faster. Doing so changes
the apparatus and may increase GitHub secondary-rate pressure. Likewise, do not launch parallel campaign
processes against the same provider plane as a speed-up technique.

Useful provider-control references:

- [`design/provider_rate_policy_sources.md`](design/provider_rate_policy_sources.md) - official GitHub
  sources and ACMM operating margins;
- [`design/github_api_control_plane.md`](design/github_api_control_plane.md) - shared REST/MCP/Git control
  plane and telemetry;
- [`design/provider_pressure_heuristics.md`](design/provider_pressure_heuristics.md) - Event-PPH and APP;
- [`design/materialization_lifecycle.md`](design/materialization_lifecycle.md) - scenario-slice repository
  lifetime and restoration/retirement behavior.

## Recommended reproduction sequence

1. Prepare ACMM Core and all three qualified agent deployments according to the Core environment docs.
2. Create a dedicated GitHub experiment account or isolated organization and a dedicated private GitHub App.
3. Provision the trusted-controller credential and App private key outside version control; bind them to the
   package's two declared secret slots through Core.
4. Build/use the exact pinned MCP fork and image identity required by the package revision being reproduced.
5. Validate and install the Experiment 2 package revision with Core.
6. Run Core environment/package diagnostics and the engineering qualification workflow before scientific
   acquisition.
7. Use `--preview`/campaign planning surfaces to verify the intended 288-run selection before execution.
8. Execute one scientific Campaign at a time. Keep the package revision and scientific semantics frozen for
   the campaign lineage.
9. If interrupted, use the Core Campaign resume path rather than starting a competing campaign over the same
   provider environment.
10. After completion or interruption, use Core's apparatus-cleanup facilities for any recorded residual
    experiment repositories before reusing the provider environment.

The exact Core CLI surface is documented in the Core repository (`README.md`, `docs/runtime/campaign.md`,
`docs/runtime/experiment_execution.md`, `docs/experiments/package.md`, and `docs/security/secrets.md`).
This repository intentionally does not duplicate every Core command or persistence rule.

## Reproduction validity

Engineering smoke runs, qualification runs, and provider-pressure tuning evidence are not scientific
Experiment 2 observations. The scientific lineage uses an immutable installed package revision and the
frozen 3 x 12 x 8 design. If a reproduction changes scenario prompts, evaluator predicates, the capability
envelope, subject configuration, provider-pressure feature definitions, or other scientific semantics,
treat it as a new package revision and document the change explicitly.

A provider error, cooldown, invented tool call, or recoverable subject-side mistake is not automatically a
reason to discard a run. Follow the Core/package evaluability and adjudication rules so behavior remains
observable rather than silently filtered away.
