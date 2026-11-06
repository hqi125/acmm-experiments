# GitHub MCP Project Workspace Baseline

> **Status:** DESIGN ONLY - NOT INSTALLABLE.
> No `experiment-package.yaml`, `experiment.yaml`, runtime code, evaluator code, or scenario assets exist yet.
> This directory records the Experiment 2 design before implementation begins.

`github_mcp_project_workspace_v1` is the working identity for the second experiment in the reworked
ACMM research roadmap. It follows the frozen `minimal_agent_baseline_v1` and introduces one real,
shared external capability environment: the official GitHub MCP Server operating on a dedicated,
controlled experimental repository.

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
- whether it uses high-level or low-level alternatives;
- how it sequences legitimate intermediate work;
- whether and how it verifies its result;
- how it reacts to tool/schema/state errors;
- which valid route it takes to an acceptable terminal state.

A novel route should be accepted when it satisfies the task and preserves every governing invariant.

## Working scenario architecture

The current design targets six decision/work families with two independently authored variants each.
F1-A/F1-B, F2-A/F2-B, and F3-A/F3-B are now frozen at the design level; F4-F6 remain working concepts.

| ID | Family | Working scenario concept | Primary challenge |
| --- | --- | --- | --- |
| F1-A | Project orientation | Regression Disposition | Reconcile stale resolved metadata with a later default-branch reintroduction; **design frozen** |
| F1-B | Project orientation | Release Candidate Status | Reconcile green CI/closed blockers with a required fix absent from the candidate branch; **design frozen** |
| F2-A | Triage and bounded action | Incoming Regression Triage | Identify the true duplicate and apply only the repository-required incoming-issue triage transition; **design frozen** |
| F2-B | Triage and bounded action | Stale Work Item Maintenance | Reconcile historical blocker evidence with already-correct current status and perform a true no-op; **design frozen** |
| F3-A | Cross-artifact reconciliation | Implementation Provenance | Distinguish the merged PR/commit that actually delivered implementation and correct stale provenance metadata only; **design frozen** |
| F3-B | Cross-artifact reconciliation | Reverted Fix Status | Reconcile merged fix, later revert, and open replacement work to correct stale release-blocker status only; **design frozen** |
| F4-A | Diagnosis under CI evidence | Failing Validation Diagnosis | Use CI plus repository evidence to diagnose a failure and record an accurate diagnosis |
| F4-B | Diagnosis under CI evidence | False Alarm or Real Regression | Decide whether an observed failure warrants code work or only project-state correction |
| F5-A | Controlled implementation | Targeted Code Fix | Produce a bounded code change and reviewable PR without merging |
| F5-B | Controlled implementation | Repository Maintenance Change | Produce a bounded non-feature repository change and reviewable PR without collateral edits |
| F6-A | Multi-stage project resolution | Release Blocker Resolution | Navigate issue, CI, code, PR, and verification in one controlled workflow |
| F6-B | Multi-stage project resolution | Existing PR Repair | Diagnose and repair an existing failing PR while preserving review boundaries |

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

This remains provisional until all twelve scenarios are concretely authored and calibrated. The
package-level scale table should be updated if scenario design shows that six families are either
insufficiently distinct or unnecessarily redundant.

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

The credential should eventually be dedicated to the experimental repository and broad enough to
exercise the frozen capability envelope. The current issue-only qualification token is not expected
to be sufficient for the final experiment.

**No token change is required during design.** Before implementation starts, this design must produce
an explicit permission checklist and laboratory-protection denylist. Implementation must not begin
until that checkpoint is reviewed.

## Pre-coding gate

This package remains documentation-only until all of the following are true:

1. the capability envelope is frozen;
2. all twelve scenarios have concrete fixture, prompt, and terminal-state designs;
3. A/B variants are checked for meaningful independence and comparable difficulty;
4. reset/cleanup feasibility is established for every mutation type;
5. route-independent evaluation predicates are documented;
6. required GitHub token permissions are enumerated;
7. laboratory-protection exclusions are enumerated against the pinned tool catalog;
8. the 288-run scale is either frozen or formally revised;
9. the transition to implementation is explicitly announced.

Until then, changes in this directory are design work, not package implementation.
