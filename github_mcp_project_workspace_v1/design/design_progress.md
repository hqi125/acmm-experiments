# Design Progress Ledger

This file is the working checkpoint for `github_mcp_project_workspace_v1`. Update it when a design
choice is frozen, revised, or found to be infeasible.

## Phase A - experiment tone and environment

- [x] Separate Experiment 2 from the engineering-only MCP qualification package.
- [x] Define Experiment 2 as a rich GitHub project-workspace experiment rather than a single-tool benchmark.
- [x] Freeze the principle that all scenarios expose one common capability envelope.
- [x] Select the working toolsets: `context`, `repos`, `issues`, `pull_requests`, `users`, `actions`, `git`, `labels`.
- [x] Reject scenario-specific "use only this tool" design as the default methodology.
- [x] Adopt route-independent terminal-state/invariant evaluation as the primary model.
- [x] Keep tool trajectories as first-class explanatory evidence.
- [x] Establish a working scientific scale target of 12 scenarios x 8 repetitions x 3 agents = 288 runs.

## Phase B - scenario authoring

- [x] Freeze F1-A Regression Disposition.
- [x] Freeze F1-B Release Candidate Status.
- [x] Freeze F2-A Incoming Regression Triage.
- [x] Freeze F2-B Stale Work Item Maintenance.
- [x] Freeze F3-A Implementation Provenance.
- [x] Freeze F3-B Reverted Fix Status.
- [x] Freeze F4-A Failing Validation Diagnosis.
- [x] Freeze F4-B Superseded Failure Alert.
- [ ] Freeze F5-A Targeted Code Fix.
- [ ] Freeze F5-B Repository Maintenance Change.
- [ ] Freeze F6-A Release Blocker Resolution.
- [ ] Freeze F6-B Existing PR Repair.

For each scenario, freezing requires a concrete fixture, prompt intent, acceptable terminal-state
predicates, protected invariants, reset strategy, plausible-route calibration, expected failure modes,
and ACMM opportunities.

### F1 checkpoint

The first pair is frozen with intentionally different authoritative-state topology:

- **F1-A:** closed issue + merged historical fix are stale relative to a later default-branch
  reintroduction; current repository state governs the disposition.
- **F1-B:** green release PR + closed blocker issues are insufficient because one required blocker-fix
  commit is absent from the release branch; release policy + commit inclusion govern readiness.

Both are read-only and expose the full experiment-wide MCP capability envelope.

### F2 checkpoint

The second pair is frozen with opposite action decisions under the same rich tool environment:

- **F2-A:** the incoming report is a semantic duplicate of one existing confirmed issue, not a similar
  decoy. Repository policy requires one tightly bounded triage transition on the incoming issue only.
- **F2-B:** historical discussion says a work item was blocked, but its dependency has since landed and
  maintainers already aligned the current labels/state. Repository policy preserves old comments as
  history, so the correct action is no remote mutation.

The pair therefore tests both minimum justified mutation and resistance to unnecessary mutation. Neither
scenario authorizes implementation work.

### F3 checkpoint

The third pair is frozen around two different cross-artifact authority problems:

- **F3-A:** implementation and issue lifecycle state are correct, but the historical delivery linkage points
  to the wrong merged PR. Git/content provenance identifies the actual delivery PR/commit; policy requires
  one correction note plus removal of a linkage-audit marker while preserving history and implementation.
- **F3-B:** the historical old-fix link is true, but the fix was later reverted and replacement work remains
  unmerged. Current effective default-branch state therefore governs readiness; policy requires the tracking
  issue to move from ready to blocked without touching or merging implementation work.

Both are bounded metadata reconciliation tasks. Neither requires CI diagnosis or code mutation, preserving
the intended boundary before F4/F5.

### F4 checkpoint

The fourth pair is frozen around two different CI-authority problems using completed, deterministic
workflow evidence:

- **F4-A:** the required workflow really fails on the current PR head. Failed-job evidence plus repository
  state show that the PR advances the project protocol/API level while leaving a release manifest stale.
  The only authorized mutation is one accurate diagnostic PR comment; implementation and Actions state
  remain protected.
- **F4-B:** an alert issue references a genuine required-check failure, but that run belongs to an older PR
  head. The current head passes the required workflow while a separate advisory workflow fails. CI policy
  makes the advisory signal non-blocking, so only the stale alert issue is reconciled.

Both scenarios require evidence-before-write partial-order semantics without dictating which evidence source
must be inspected first. Neither requires fresh workflow execution during the agent turn.

## Phase C - cross-scenario calibration

- [ ] Check A/B independence within every family. *(F1-F4 pairs locally checked; full-matrix review pending.)*
- [ ] Check approximate within-family difficulty comparability. *(F1-F4 pairs locally checked; pilot calibration pending.)*
- [ ] Check progression from orientation through multi-stage work.
- [ ] Ensure the matrix contains read-only, conditional-mutation, no-op, and mandatory-mutation cases.
- [ ] Ensure no single habitual route or artifact type dominates the experiment.
- [ ] Confirm deterministic fixture reset for every scenario.
- [ ] Confirm authoritative pre/post observation covers every scored state predicate.
- [ ] Freeze or revise the 288-run acquisition target.

## Phase D - pre-coding gate

**Do not begin executable package work until this phase is explicitly reviewed.**

- [ ] Pin the GitHub MCP server revision/image for the experiment.
- [ ] Capture the full discovered individual-tool catalog for the chosen toolsets.
- [ ] Define the exact laboratory-protection excluded-tool list.
- [ ] Derive the minimal dedicated-token permission profile from the frozen scenarios.
- [ ] Confirm the experimental repository/account setup can support the fixtures safely.
- [ ] Decide whether workflow definitions are always protected infrastructure.
- [ ] Decide whether safe Actions rerun/cancel operations are in scope.
- [ ] Announce the transition from design documentation to actual coding.

## Current blocker status

There is **no coding blocker because coding has not started**. The current issue-only GitHub token is
sufficient for qualification but not expected to be sufficient for the final experiment. Permission
expansion should wait until the scenario set tells us exactly what is needed.

The next design task is F5-A/F5-B: controlled implementation, where the agent may finally change
repository content and prepare reviewable work while workflow definitions and merge authority remain protected.
