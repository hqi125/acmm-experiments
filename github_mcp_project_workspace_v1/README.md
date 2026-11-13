# GitHub MCP Project Workspace Baseline

> **Status:** APP-NATIVE MCP GOVERNOR QUALIFIED; SCENARIO MATERIALIZATION POLICY IMPLEMENTED.
> The exact 42-tool App-native surface and governed v2.1.0 MCP fork are qualified across all three subjects. A 288-run stress campaign exposed repeatable provider secondary-limit pressure from the per-run repository lifecycle, so the apparatus now uses package-declared campaign materialization without changing the subject-visible MCP surface.
> F1-F4 use shared scenario materialization with exact trusted restoration and hard taint for non-restorable provider history. F5 and F6 intentionally remain run-isolated because their successful scientific terminal states create durable Git commits and/or pull-request history that GitHub cannot erase exactly between observations.

`github_mcp_project_workspace_v1` is the working identity for the second experiment in the reworked
ACMM research roadmap. It follows the frozen `minimal_agent_baseline_v1` and introduces one real
external capability environment: the official GitHub MCP Server operating against controller-created,
private disposable repositories. The original apparatus used one scientific repository per run; the current
incremental redesign allows an experiment package to retain provider resources for one declared materialization
slice while Core preserves subject-major execution inside that slice.

The experiment is intentionally **not** a single-tool or tool-call benchmark. Every subject should
receive the same rich GitHub project workspace in every scenario. Scenarios define goals, authority,
preservation requirements, and acceptable terminal states; they should not encode the agent's route
by hiding all tools except the expected one or by naming a golden tool sequence.

## Working research question

> Under the same qualified LLM and minimal controlled agent configuration, how effectively and
> reliably do Hermes, Open WebUI, and Agent Zero select, compose, sequence, verify, and recover across
> a realistic shared GitHub MCP capability environment while completing controlled software-project
> tasks?

The study is intended to characterize both **whether the work is completed correctly** and **how the
agent system navigates a non-trivial real-tool environment to get there**.

## Relationship to earlier work

The roadmap now has three distinct reference conditions:

1. `minimal_agent_baseline_v1` - minimal controlled agent, no experiment-provided tools.
2. `github_mcp_project_workspace_v1` - minimal controlled agent plus a fixed rich GitHub MCP workspace.
3. A later experiment - the same GitHub MCP workspace plus one isolated agent-side feature.

The engineering-only `github_mcp_integration_qualification_v1` remains separate. It proved that the
pinned GitHub MCP integration can be provisioned, discovered, executed, normalized, and adjudicated
across all three agents. Its read-comment-read workflow is infrastructure qualification evidence and
should not be promoted into the Experiment 2 scientific dataset.

## Fixed capability envelope

The App-native toolset envelope is:

```text
repos
issues
pull_requests
users
actions
git
labels
```

This is a coherent GitHub software-development workspace rather than the literal `all` toolset. The same
42-tool surface is expected for every subject and scenario after run-time admission. The `context` toolset
is intentionally absent because its `get_me` path requires a user identity and is incompatible with the
qualified GitHub App installation-token credential. ACMM does not emulate that identity.

The exact pinned server image, 42-tool catalog, and normalized catalog digest are frozen apparatus
provenance before acquisition.

See [`design/capability_envelope.md`](design/capability_envelope.md) for the full boundary model.

Provider/API behavior is governed as a shared apparatus control plane rather than by scenario-local retries.
See [`design/github_api_control_plane.md`](design/github_api_control_plane.md) for persistent request budgeting,
secondary-limit coordination, API telemetry, and the implemented Git repository content/history plane used
to remove controller Contents-API writes/reads before stable acquisition.

## Core design rule

> **The experiment controls the world and the goals, not the agent's route through the world.**

The package controls:

- the dedicated repository and fixture state;
- the pinned GitHub MCP server and visible capability envelope;
- the credential scope and laboratory-protection exclusions;
- scenario prompts and authorization boundaries;
- authoritative pre-state and post-state observation;
- acceptable terminal-state predicates;
- protected invariants and forbidden side effects;
- true dependency/procedure constraints where the task actually requires them.

The agent controls:

- what it inspects first;
- which relevant tools it selects;
- which overlapping repository/discovery/write capabilities it chooses;
- how it sequences legitimate intermediate work;
- whether and how it verifies its result;
- how it reacts to tool/schema/state errors;
- which valid route it takes to an acceptable terminal state.

A novel route should be accepted when it satisfies the task and preserves every governing invariant.

## Working scenario architecture

The current design targets six decision/work families with two independently authored variants each.
All F1-A/F1-B through F6-A/F6-B scenarios are now frozen at the design level.

| ID | Family | Working scenario concept | Primary challenge |
| --- | --- | --- | --- |
| F1-A | Project orientation | Regression Disposition | Reconcile stale resolved metadata with a later default-branch reintroduction; **design frozen** |
| F1-B | Project orientation | Release Candidate Status | Reconcile green CI/closed blockers with a required fix absent from the candidate branch; **design frozen** |
| F2-A | Triage and bounded action | Incoming Regression Triage | Identify the true duplicate and apply only the repository-required incoming-issue triage transition; **runtime implemented, live smoke qualified** |
| F2-B | Triage and bounded action | Stale Work Item Maintenance | Reconcile historical blocker evidence with already-correct current status and perform a true no-op; **runtime implemented, live smoke qualified** |
| F3-A | Cross-artifact reconciliation | Implementation Provenance | Distinguish the merged PR/commit that actually delivered implementation and correct stale provenance metadata only; **runtime implemented, live smoke qualified** |
| F3-B | Cross-artifact reconciliation | Reverted Fix Status | Reconcile merged fix, later revert, and open replacement work to correct stale release-blocker status only; **runtime implemented, live smoke qualified** |
| F4-A | Diagnosis under CI evidence | Failing Validation Diagnosis | Diagnose a current required-check failure from completed CI + repository evidence and record only the diagnosis; **live-smoke qualified** |
| F4-B | Diagnosis under CI evidence | Superseded Failure Alert | Reconcile superseded required-check failure plus current advisory failure, then correct only the stale CI alert; **live-smoke qualified** |
| F5-A | Controlled implementation | Targeted Code Fix | Repair one product-code behavior and prepare an isolated review PR while preserving tests, issue state, and protected infrastructure; **live-smoke qualified** |
| F5-B | Controlled implementation | Release Metadata Synchronization | Synchronize two policy-defined maintenance mirrors with repository release authority and prepare one review PR; **live-smoke qualified** |
| F6-A | Multi-stage project resolution | Release Blocker Resolution | Diagnose a candidate-branch blocker, prepare the bounded release-targeted repair PR, and leave an accurate review handoff; **live-smoke qualified** |
| F6-B | Multi-stage project resolution | Existing PR Repair | Repair an existing draft PR in place, preserve its identity, and transition PR/issue state to an accurate review handoff; **live-smoke qualified** |

The detailed matrix and per-family notes live under [`design/`](design/README.md).

## Candidate scale

The design should aim directly at a statistically useful balance point rather than use a deliberately
undersized scientific acquisition. Engineering smoke runs are separate from the final study.

| Candidate design | Runs / agent | Total runs | Main tradeoff |
| --- | ---: | ---: | --- |
| 10 scenarios x 6 reps | 60 | 180 | Economical, but narrow task breadth and weaker repeatability |
| 12 scenarios x 6 reps | 72 | 216 | Good breadth, moderate within-scenario stability |
| **12 scenarios x 8 reps** | **96** | **288** | **Current preference: strong breadth and repeatability for a narrower real-tool domain** |
| 16 scenarios x 6 reps | 96 | 288 | More breadth at the cost of shallower scenario repetition and more fixture burden |
| 12 scenarios x 10 reps | 120 | 360 | Excellent stability, but less marginal value than adding/validating task diversity |

The current working target is therefore:

**3 agents x 6 task families x 2 scenario variants x 8 repetitions = 288 planned executions.**

With all twelve scenarios concretely authored, **288 executions is now the frozen design-level
acquisition target**. Engineering smoke/pilot runs remain separate, and the scale should be reopened only
if implementation or pilot evidence shows a scenario is infeasible, non-independent, or materially
miscalibrated.

As in the baseline, ACMM opportunities inside one run are nested diagnostic evidence, not independent
scientific samples. Headline analysis should remain scenario/family balanced.

## Evaluation direction

Evaluation should be route-independent wherever possible. Each scenario should define:

- authoritative initial state;
- acceptable terminal-state predicates;
- required preservation predicates;
- forbidden side effects;
- task-specific obligations;
- true partial-order dependencies, if any;
- expected final-response claims that can be checked against authoritative state.

Tool trajectories are then analyzed as behavioral evidence rather than compared against one golden
sequence. Useful trace-level observations include tool relevance, exploration breadth, redundant
calls, mutation timing, verification, recovery, collateral activity, and route complexity.

See [`design/evaluation_model.md`](design/evaluation_model.md).

## Credential and safety boundary

The experiment now separates a trusted controller PAT from the subject-facing credential model. The controller
PAT performs repository lifecycle, fixture materialization, deterministic CI setup, authoritative observation, and
selected-repository App-installation assignment. The subject receives no persistent GitHub credential.

For each scientific run, trusted package code attaches only that disposable repository to the private
`acmm-github-app` installation and mints one installation token narrowed to the exact repository. The token
contains Metadata read, Contents read/write, Issues read/write, Pull requests read/write, and Actions read;
Workflows and repository/administrative authority are absent. Core admits the token only across the subject
execution window, then explicitly revokes it and restores the static integration to an unadmitted sentinel before
trusted post-state capture.

The App private key is the package secret `github_app_private_key`; the controller PAT remains
`controller_access_token`. Neither secret nor any run token is stored in package source, campaign provenance,
or the runtime resource ledger. See [`design/fixture_lifecycle.md`](design/fixture_lifecycle.md) and
[`design/pinned_mcp_catalog.md`](design/pinned_mcp_catalog.md).

## Implementation checkpoint

The design/pre-coding gate is closed and executable implementation is underway. The package now provides:

- package schema v0.3 with Experiment-scoped controller PAT and GitHub App private-key secrets;
- the frozen 12-scenario x 8-repetition Contract;
- pinned GitHub MCP Server v2.1.0 integration built from the maintained ACMM governor fork while preserving the qualified 42-tool App-native catalog;
- static subject deployments remain intentionally unadmitted; exact 42-tool catalog verification occurs after each run-scoped App token is bound;
- a trusted controller diagnostic and explicit `initialize` apparatus action for the pinned private repository;
- an engineering-reference repository used to qualify F1-A/F1-B semantics, while final scientific acquisition
  uses one disposable private repository per run;
- `qualify_disposable_repositories`, now invoked through `acmm run apparatus exec`, with one successful live
  create/App-attach/one-repo-token-write/revoke/detach/exact-ID-delete qualification workflow;
- a Core-owned typed execution lifecycle with package hooks for session/run prepare, observe, and deferred
  evidence-last finalization;
- typed apparatus cleanup via `acmm run apparatus cleanup --execution <execution-dir>`, using the controller
  credential and exact repository IDs recorded by legacy quarantines or failed archive/delete cleanup to remove
  residual disposable repositories;
- archive-then-delete failure isolation: ordinary invalid/preparation failures preserve a forensic ZIP inside the
  execution directory, delete and verify the exact remote repository, then allow later independent runs to proceed;
  a new session still refuses stale `acmm-e2-run-*` repositories left by crashes or failed cleanup;
- a fully runnable/cross-agent-qualified F1-A Regression Disposition scenario now instantiated into a fresh
  private repository per scientific run;
- the GitHub App + Campaign path is live-qualified across Hermes, Open WebUI, and Agent Zero with one clean F1-A
  observation per subject, exact 42-tool admission, explicit token revocation, repository detach/delete, credential
  log redaction, and a provenance-preserving partial Campaign merge;
- an F1-B `prepare_f1_b` materializer that creates the release milestone, blocker label, included/missing
  blocker histories, release candidate branch/PR, non-blocker noise, and a deterministic passing Actions run
  on the candidate head.
- F3-A/F3-B live qualification completed with six valid disposable runs and exact-ID cleanup; the calibrated
  task surfaces now bound candidate artifacts so fresh-repository search indexing is not a hidden treatment variable;
- F4-A/F4-B executable Actions fixtures: trusted controller-seeded completed workflow runs/jobs/logs, immutable
  run/head association, authoritative pre/post Actions inventory, real Procedure opportunities requiring evidence before
  mutation, and bounded diagnosis/alert-reconciliation evaluators.
- controller/App transport hardening for Actions/job-log downloads and GitHub abuse protection: API redirect hops are
  captured without forwarding the controller PAT to signed download hosts, trusted controller and App lifecycle
  mutations share provider pacing/cooldown state, primary quota snapshots remain separated by credential domain, and
  only explicit secondary-rate-limit responses are retried according to GitHub backoff guidance; ambiguous transport
  failures remain fail-closed;
- a production Git content/history plane now transparently backs controller file writes and ref-addressed file reads,
  keeps the PAT out of remote URLs/command arguments through `GIT_ASKPASS`, reports Git transport telemetry, and
  exposes a canonical ref fingerprint for later unchanged-state fast paths.

F1-B scientific execution now uses the disposable lifecycle. Its controller creates the fresh private repository,
materializes the release topology, dispatches and waits for the deterministic required-check workflow, captures
authoritative pre/post state, and deletes the exact repository only after durable run evidence. F2-A/F2-B reuse
that lifecycle with bounded-mutation versus true-no-op semantics. The first F2-A live smokes exposed two apparatus
issues now covered by regressions: GitHub default-label convergence and eventual-consistency lag in newly created
issue list views. Historical PAT-era smoke work demonstrated that remotely quarantined repositories were scientifically
discoverable under all-repositories subject access. The lifecycle therefore no longer uses normal remote quarantine:
failed apparatus state is archived locally first, the exact repository is deleted and disappearance verified, and only
then may the next independent run begin.

See [`design/controller_runtime_checkpoint.md`](design/controller_runtime_checkpoint.md),
[`design/fixture_lifecycle.md`](design/fixture_lifecycle.md), and
[`design/design_progress.md`](design/design_progress.md).
