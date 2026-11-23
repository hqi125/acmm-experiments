# GitHub MCP Project Workspace Baseline

> **Status: FROZEN SCIENTIFIC PACKAGE.** The twelve-scenario Experiment 2 design was acquired at
> 3 agents x 12 scenarios x 8 repetitions = **288 scientific runs**. Engineering qualification runs
> are separate from the scientific dataset. The package retains the exact App-native GitHub MCP
> capability envelope, scenario-slice fixture lifecycle, trusted-controller boundary, and provider-
> pressure controls used for acquisition.

`github_mcp_project_workspace_v1` is the second experiment in the reworked ACMM research program. It
follows the tool-free [`minimal_agent_baseline_v1`](../minimal_agent_baseline_v1/README.md) and adds one
real external capability environment: a pinned GitHub MCP Server operating against trusted-controller-
created private repositories.

The experiment is deliberately not a single-tool or golden-tool-sequence benchmark. Every subject sees
the same rich GitHub project workspace. Scenarios define goals, authority, preservation requirements,
and acceptable terminal states while leaving legitimate tool selection and sequencing to the agent.

## Important execution warning

> **Do not run this experiment with your primary everyday personal GitHub account.** A full Experiment 2
> campaign creates and manipulates real private repositories and produces sustained GitHub REST, MCP,
> and Git traffic over a long execution window. Use a dedicated experiment account or similarly isolated
> organization/App environment that you can safely subject to heavy automated activity.
>
> Do not run multiple Experiment 2 campaigns concurrently against the same GitHub account/App/provider
> plane. GitHub recommends serial request behavior to reduce secondary-rate pressure, and concurrency can
> increase throttling while also contaminating the traffic conditions the experiment is trying to control.

Read [`REPRODUCTION.md`](REPRODUCTION.md) before provisioning credentials or starting a campaign. The
provider-control rationale and sourced pacing defaults are recorded in
[`design/provider_rate_policy_sources.md`](design/provider_rate_policy_sources.md).

## Research question

> Under the same qualified LLM and minimal controlled agent configuration, how effectively and reliably
> do Hermes, Open WebUI, and Agent Zero select, compose, sequence, verify, and recover across a realistic
> shared GitHub MCP capability environment while completing controlled software-project tasks?

The study characterizes both **whether project work is completed correctly** and **how the agent system
navigates a non-trivial real-tool environment to get there**.

## Relationship to the other packages

The repository contains three distinct roles:

1. [`minimal_agent_baseline_v1`](../minimal_agent_baseline_v1/README.md) establishes the minimal,
   no-experiment-tool reference condition.
2. [`github_mcp_integration_qualification_v1`](../github_mcp_integration_qualification_v1/README.md)
   is engineering-only qualification evidence for native GitHub MCP discovery and execution. It is not
   part of the Experiment 2 dataset.
3. `github_mcp_project_workspace_v1` is the substantive real-tool experiment described here.

A later study may add an isolated agent-side feature while preserving the real-tool environment, but
that is outside this package's scientific scope.

## Fixed capability envelope

The selected GitHub MCP toolsets are:

```text
repos
issues
pull_requests
users
actions
git
labels
```

The frozen package expects an exact 42-tool App-native surface for every admitted subject run. The
`context` toolset is intentionally absent because its `get_me` path requires a user identity and is
incompatible with the qualified GitHub App installation-token credential. ACMM does not emulate that
identity.

The package pins the maintained ACMM GitHub MCP Server fork to upstream v2.1.0 and records the exact
catalog digest and source commit in `experiment-package.yaml`. See
[`design/pinned_mcp_catalog.md`](design/pinned_mcp_catalog.md) and
[`design/capability_envelope.md`](design/capability_envelope.md).

## Core design rule

> **The experiment controls the world and the goals, not the agent's route through the world.**

The package controls the dedicated fixture state, visible capability envelope, credential scope,
laboratory-protection exclusions, prompts, authorization boundaries, authoritative pre/post-state,
acceptable terminal-state predicates, protected invariants, and genuine dependency constraints.

The agent controls what it inspects first, which relevant tools it chooses, how it sequences legitimate
intermediate work, whether and how it verifies the result, how it responds to tool/schema/state errors,
and which valid route it uses to reach an acceptable terminal state. A novel route is acceptable when it
satisfies the task and preserves every governing invariant.

## Frozen study design

The experiment contains six task families with two independently authored variants each:

| ID | Family | Scenario | Primary challenge |
| --- | --- | --- | --- |
| F1-A | Project orientation | Regression Disposition | Reconcile stale resolved metadata with a later default-branch reintroduction |
| F1-B | Project orientation | Release Candidate Status | Reconcile green CI/closed blockers with a required fix absent from the candidate branch |
| F2-A | Triage and bounded action | Incoming Regression Triage | Identify the true duplicate and perform only the repository-required triage transition |
| F2-B | Triage and bounded action | Stale Work Item Maintenance | Reconcile historical blocker evidence with already-correct current status and perform a true no-op |
| F3-A | Cross-artifact reconciliation | Implementation Provenance | Identify the PR/commit that actually delivered implementation and correct stale provenance only |
| F3-B | Cross-artifact reconciliation | Reverted Fix Status | Reconcile a merged fix, later revert, and open replacement work to correct stale status only |
| F4-A | Diagnosis under CI evidence | Failing Validation Diagnosis | Diagnose a required-check failure from completed CI and repository evidence before acting |
| F4-B | Diagnosis under CI evidence | Superseded Failure Alert | Reconcile superseded/current CI evidence and correct only the stale alert |
| F5-A | Controlled implementation | Targeted Code Fix | Make one bounded product-code repair and prepare an isolated review PR |
| F5-B | Controlled implementation | Release Metadata Synchronization | Synchronize policy-defined maintenance mirrors and prepare one review PR |
| F6-A | Multi-stage project resolution | Release Blocker Resolution | Diagnose, repair against the correct release target, and leave an accurate review handoff |
| F6-B | Multi-stage project resolution | Existing PR Repair | Repair an existing PR in place and transition PR/issue state to an accurate handoff |

The scientific scale is fixed at:

**3 agents x 6 task families x 2 scenario variants x 8 repetitions = 288 executions.**

ACMM opportunities inside one run are nested diagnostic evidence, not independent scientific samples.
Headline analysis should therefore remain scenario/family balanced rather than treating every opportunity
as an independent observation.

See [`design/scenario_matrix.md`](design/scenario_matrix.md) for the complete scenario matrix and the
per-family design documents.

## Evaluation model

Evaluation is route-independent wherever possible. Each scenario defines authoritative initial state,
acceptable terminal-state predicates, required preservation predicates, forbidden side effects,
task-specific obligations, genuine partial-order dependencies, and final-response claims that can be
checked against trusted state.

Tool trajectories are behavioral evidence rather than a golden sequence. Useful trace-level observations
include tool relevance, exploration breadth, redundant calls, mutation timing, verification, recovery,
collateral activity, and route complexity. See [`design/evaluation_model.md`](design/evaluation_model.md).

## Credential and fixture boundary

Experiment 2 separates trusted apparatus credentials from subject authority:

- `controller_access_token` is a trusted-controller secret used for repository lifecycle, fixture
  materialization, authoritative observation, and App-installation management.
- `github_app_private_key` is used to mint short-lived GitHub App installation tokens.
- Each scientific subject run receives only fresh, repository-scoped App authority for the active
  materialized repository; persistent controller credentials are never exposed to the subject.

The checked-in repository/App identifiers are **apparatus provenance, not credentials**. Secret values
and run tokens are not stored in package source, campaign provenance, or the runtime resource ledger.
For public reproduction, provision your own isolated GitHub apparatus and create a new package revision
rather than treating the original-study identifiers as reusable infrastructure. See
[`REPRODUCTION.md`](REPRODUCTION.md) and [`design/fixture_lifecycle.md`](design/fixture_lifecycle.md).

## Scenario-slice lifecycle and provider control

The package groups campaign materialization by `scenario_id`. One private repository can therefore span
multiple logical runs of the same scenario while Core preserves the intended subject-major run order
inside the slice. Trusted package code restores or retires run-owned active state between observations;
explicitly allowed closed/unmerged history may remain slice-owned evidence. Non-restorable contamination
taints and retires the slice.

During an active logical run, the Core Provider Gate is the admission surface for participating GitHub
REST/GraphQL/raw, trusted-controller/App, MCP, and Git smart-protocol traffic. Event-PPH and APP remain
separate controls, and provider-directed recovery overrides shorter local heuristic waits. Local MCP/Git
governors are conservative fallback controls when no active Core gate owns the action.

See [`design/github_api_control_plane.md`](design/github_api_control_plane.md),
[`design/provider_pressure_heuristics.md`](design/provider_pressure_heuristics.md), and
[`design/provider_rate_policy_sources.md`](design/provider_rate_policy_sources.md).

## Documentation map

- [`REPRODUCTION.md`](REPRODUCTION.md) - public execution prerequisites, account isolation, credential
  setup boundaries, traffic/runtime warnings, and reproduction rules.
- [`design/README.md`](design/README.md) - design-document index.
- [`design/scenario_matrix.md`](design/scenario_matrix.md) - frozen twelve-scenario matrix.
- [`design/evaluation_model.md`](design/evaluation_model.md) - state- and trajectory-level evaluation.
- [`design/fixture_lifecycle.md`](design/fixture_lifecycle.md) - trusted fixture and credential lifecycle.
- [`design/github_api_control_plane.md`](design/github_api_control_plane.md) - provider-facing transport
  and traffic control.
- [`design/pre_acquisition_audit.md`](design/pre_acquisition_audit.md) - historical final audit performed
  before the long scientific campaign.
- [`design/design_progress.md`](design/design_progress.md) - concise historical design/implementation
  chronology.
