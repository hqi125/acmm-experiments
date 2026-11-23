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

## Manual prerequisites ACMM does not create

Experiment 2 has provider-side and host-side prerequisites that must exist **before** the package can become
READY. ACMM intentionally does not create these implicitly:

- a dedicated GitHub experiment account or isolated organization/account arrangement;
- a trusted controller credential with enough authority for the package's apparatus lifecycle, including
  private repository creation/deletion, trusted Git/content/issue/PR operations, Actions observation/dispatch,
  and adding/removing experiment repositories from the selected App installation;
- a dedicated GitHub App using the frozen subject permission envelope documented below;
- a GitHub App private key in PEM form, generated/downloaded from GitHub and stored outside version control;
- an installation of that App limited to the experiment environment and usable by the trusted controller for
  dynamic attach/detach of disposable experiment repositories;
- a private **engineering reference repository** used by package diagnostics and fixture-base initialization.
  It is diagnostic-only and is not the scientific scenario workspace. It must satisfy the package's pinned
  identity/default-branch expectations, remain private, and have Issues enabled;
- GitHub Actions enabled for the experiment repositories so the package can create/read/dispatch its deterministic
  scenario workflows where required;
- host `git`, Docker, and `openssl` executables. Package apply uses Git/Docker to fetch and build the exact
  pinned MCP source, and the runtime uses OpenSSL to sign GitHub App JWTs;
- outbound access needed for GitHub API/Git transport and for fetching the pinned MCP source when it is not
  already available locally.

A simple host-side executable check is:

```text
git --version
docker --version
docker compose version
openssl version
```

The ordinary Core/LLM prerequisites still apply. In particular, prepare the selected Ollama model and the three
qualified subject deployments before attempting the Experiment 2-specific gates below.

### Reproduction-specific identifiers

The checked-in `assets/controller.json` contains the **original study's** apparatus coordinates. A public
reproduction must create its own package revision and replace, at minimum, the coordinates that identify its
provider resources:

- `repository_name`, `repository_full_name`, and `repository_id` for the engineering reference repository;
- `github_app.app_id`, `github_app.installation_id`, and `github_app.slug` for the reproduction App/install;
- any other apparatus identity deliberately changed by the reproduction, such as a substituted MCP source
  repository/commit.

Do not edit an already installed frozen revision in place. Validate and install the changed source as a new
content-addressed package revision so the new apparatus identity is represented truthfully in provenance.

## Required secret slots

`experiment-package.yaml` declares two required Experiment-scoped secret slots:

| Secret slot | Purpose | Exposure rule |
| --- | --- | --- |
| `controller_access_token` | Trusted repository lifecycle, fixture setup/observation, and selected-repository App-installation management | Trusted apparatus only; never subject-visible |
| `github_app_private_key` | Mint short-lived GitHub App installation tokens | Trusted apparatus only; never committed to package source |

Store secret values through the ACMM Core secret registry. Do not place PATs, private keys, installation
tokens, `.env` files, or copied credential material inside this repository. A typical binding sequence is:

```text
acmm secret init
acmm secret bind experiment github_mcp_project_workspace_v1 controller_access_token --file <controller-token-file>
acmm secret bind experiment github_mcp_project_workspace_v1 github_app_private_key --file <github-app-private-key-file>
acmm secret validate
```

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

## First-time live verification gate

For a new reproduction environment, use the package's engineering surfaces before creating a scientific
Campaign. These checks intentionally separate provider provisioning from scientific execution.

1. Validate/install the new package revision and bind both Experiment-scoped secrets.
2. Run `acmm package apply <experiment-selector>`. The pinned integration checks for host Git/Docker, fetches
   the exact MCP source commit when needed, builds/verifies the pinned image identity, and reconciles the local
   shared MCP service.
3. Run `acmm run apparatus list` and confirm the expected engineering actions are available.
4. Run `acmm run apparatus exec initialize`. This explicit action initializes or verifies the pinned engineering
   reference fixture base. `package apply` and `env doctor` intentionally do not perform this GitHub mutation.
   The initializer refuses an unrelated/mismatched non-empty repository rather than overwriting it.
5. Run `acmm env doctor --start-if-needed` and require the controller diagnostic, integration resource, selected
   LLM/model, all three subject deployments, and the expected 42-tool App-native MCP surface to report READY.
   Do not proceed by ignoring a failed check.
6. Run `acmm run apparatus exec qualify_disposable_repositories`. This is a **live mutating qualification**: it
   creates a temporary private probe repository, attaches it to the selected App installation, mints a token
   narrowed to that repository, verifies App-token Contents write plus controller readback, revokes the token,
   detaches the repository, deletes it, and verifies deletion. A failure here is a provider/apparatus setup
   failure, not a reason to start scientific acquisition anyway.
7. Optionally run `acmm run apparatus exec api_status` immediately before a long campaign to inspect the package's
   current non-secret GitHub governor/rate-state view.
8. Preview the intended run population with Core's run/campaign preview surface before allowing mutations from
   scientific runs.

This gate is especially important after changing a GitHub App, controller credential, App installation,
reference repository, MCP source pin, Docker installation, or host machine. Re-run the relevant checks rather
than assuming a previously qualified external environment is still equivalent.

## Recommended reproduction sequence

1. Prepare ACMM Core, the host Ollama/model path, and all three qualified agent deployments according to
   the Core environment docs.
2. Create the dedicated GitHub experiment environment, controller credential, GitHub App/private key,
   installation, and private engineering reference repository described above.
3. Create a reproduction package revision containing your provider identifiers while preserving the intended
   scientific semantics and exact MCP source/image provenance.
4. Bind the two declared Experiment secrets and complete the **First-time live verification gate** above.
5. Use `--preview`/campaign planning surfaces to verify the intended 288-run selection before execution.
6. Execute one scientific Campaign at a time. Keep the package revision and scientific semantics frozen for
   the campaign lineage.
7. If interrupted, use the Core Campaign resume path rather than starting a competing campaign over the same
   provider environment.
8. After completion or interruption, use Core's apparatus-cleanup facilities for any recorded residual
   experiment repositories before reusing the provider environment. Use cleanup preview/verification first
   when investigating an interrupted execution.

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
