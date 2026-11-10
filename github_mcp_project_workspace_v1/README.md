# GitHub MCP Project Workspace Baseline

> **Status:** IMPLEMENTATION IN PROGRESS - F1-A QUALIFIED, F1-B DISPOSABLE SCIENTIFIC RUNTIME IMPLEMENTED.
> F1-A is scientifically runnable and cross-agent qualified. F1-B now uses the same one-private-repository-per-run
> typed lifecycle, including deterministic Actions evidence seeded before subject execution. F2 through F6 remain
> design-frozen only.

`github_mcp_project_workspace_v1` is the working identity for the second experiment in the reworked
ACMM research roadmap. It follows the frozen `minimal_agent_baseline_v1` and introduces one real
external capability environment: the official GitHub MCP Server operating against controller-created,
private disposable repositories, one scientific repository per run.

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

The working toolset envelope is:

```text
context
repos
issues
pull_requests
users
actions
git
labels
```

This is a coherent GitHub software-development workspace rather than the literal `all` toolset. The
same envelope should be visible to every subject in every scenario. Scenario difficulty comes from
what the work requires, not from changing the visible tool palette.

The current official GitHub MCP Server default toolsets are `context`, `repos`, `issues`,
`pull_requests`, and `users`; this design adds `actions`, `git`, and `labels`. The design was checked
against the official server README and server-configuration documentation on 2026-11-06. The exact
pinned server image, discovered tool catalog, and a catalog digest should become execution provenance
before acquisition.

See [`design/capability_envelope.md`](design/capability_envelope.md) for the full boundary model.

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
| F2-A | Triage and bounded action | Incoming Regression Triage | Identify the true duplicate and apply only the repository-required incoming-issue triage transition; **design frozen** |
| F2-B | Triage and bounded action | Stale Work Item Maintenance | Reconcile historical blocker evidence with already-correct current status and perform a true no-op; **design frozen** |
| F3-A | Cross-artifact reconciliation | Implementation Provenance | Distinguish the merged PR/commit that actually delivered implementation and correct stale provenance metadata only; **design frozen** |
| F3-B | Cross-artifact reconciliation | Reverted Fix Status | Reconcile merged fix, later revert, and open replacement work to correct stale release-blocker status only; **design frozen** |
| F4-A | Diagnosis under CI evidence | Failing Validation Diagnosis | Diagnose a current required-check failure from completed CI + repository evidence and record only the diagnosis; **design frozen** |
| F4-B | Diagnosis under CI evidence | Superseded Failure Alert | Reconcile superseded required-check failure plus current advisory failure, then correct only the stale CI alert; **design frozen** |
| F5-A | Controlled implementation | Targeted Code Fix | Repair one product-code behavior and prepare an isolated review PR while preserving tests, issue state, and protected infrastructure; **design frozen** |
| F5-B | Controlled implementation | Release Metadata Synchronization | Synchronize two policy-defined maintenance mirrors with repository release authority and prepare one review PR; **design frozen** |
| F6-A | Multi-stage project resolution | Release Blocker Resolution | Diagnose a candidate-branch blocker, prepare the bounded release-targeted repair PR, and leave an accurate review handoff; **design frozen** |
| F6-B | Multi-stage project resolution | Existing PR Repair | Repair an existing draft PR in place, preserve its identity, and transition PR/issue state to an accurate review handoff; **design frozen** |

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

The experiment uses two fine-grained credentials with **All repositories** access under the dedicated
experiment account so newly created disposable run repositories are reachable. The subject MCP PAT retains
Metadata read, Contents read/write, Issues read/write, Pull requests read/write, Actions read, and Commit
statuses read, with no Repository creation or Administration permission. The trusted controller PAT additionally
has Actions write, Workflows read/write, Repository creation read/write, and Administration read/write for
trusted repository lifecycle. GitHub fine-grained PATs do not expose a separate Checks permission, so it is
intentionally absent from both profiles.

The dedicated subject/controller PATs have now been created by the user. Their values remain outside the
repository and are consumed only through ACMM secret bindings. The recommended local source files are
`~/.config/acmm/secrets/acmm-experiment-2-mcp-subject-pat` and
`~/.config/acmm/secrets/acmm-experiment-2-mcp-controller-pat`; these paths are operator convention,
not package identity.
The v2.0.3 catalog/exclusions and fixture strategy are frozen in
[`design/pinned_mcp_catalog.md`](design/pinned_mcp_catalog.md),
[`design/fixture_lifecycle.md`](design/fixture_lifecycle.md), and
[`design/pre_coding_checkpoint.md`](design/pre_coding_checkpoint.md).

## Implementation checkpoint

The design/pre-coding gate is closed and executable implementation is underway. The package now provides:

- package schema v0.3 with separate Experiment/controller and Integration/subject secret scopes;
- the frozen 12-scenario x 8-repetition Contract;
- pinned GitHub MCP Server v2.0.3 integration with the qualified 43-tool catalog;
- exact tool-catalog and container-image provenance checks across Hermes, Open WebUI, and Agent Zero;
- a trusted controller diagnostic and explicit `initialize` apparatus action for the pinned private repository;
- an engineering-reference repository used to qualify F1-A/F1-B semantics, while final scientific acquisition
  uses one disposable private repository per run;
- `qualify_disposable_repositories`, now invoked through `acmm run apparatus`, with one successful live
  create/subject-write/controller-read/exact-ID-delete qualification cycle;
- a Core-owned typed execution lifecycle with package hooks for session/run prepare, observe, and deferred
  evidence-last finalization;
- a fully runnable/cross-agent-qualified F1-A Regression Disposition scenario now instantiated into a fresh
  private repository per scientific run;
- an F1-B `prepare_f1_b` materializer that creates the release milestone, blocker label, included/missing
  blocker histories, release candidate branch/PR, non-blocker noise, and a deterministic passing Actions run
  on the candidate head.

F1-B scientific execution now uses the disposable lifecycle. Its controller creates the fresh private repository,
materializes the release topology, dispatches and waits for the deterministic required-check workflow, captures
authoritative pre/post state, and deletes the exact repository only after durable run evidence. The immediate
checkpoint is live F1-B qualification before later scenario implementation resumes.

See [`design/controller_runtime_checkpoint.md`](design/controller_runtime_checkpoint.md),
[`design/fixture_lifecycle.md`](design/fixture_lifecycle.md), and
[`design/design_progress.md`](design/design_progress.md).
