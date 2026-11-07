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
- [x] Freeze the design-level scientific scale at 12 scenarios x 8 repetitions x 3 agents = 288 runs.

## Phase B - scenario authoring

- [x] Freeze F1-A Regression Disposition.
- [x] Freeze F1-B Release Candidate Status.
- [x] Freeze F2-A Incoming Regression Triage.
- [x] Freeze F2-B Stale Work Item Maintenance.
- [x] Freeze F3-A Implementation Provenance.
- [x] Freeze F3-B Reverted Fix Status.
- [x] Freeze F4-A Failing Validation Diagnosis.
- [x] Freeze F4-B Superseded Failure Alert.
- [x] Freeze F5-A Targeted Code Fix.
- [x] Freeze F5-B Release Metadata Synchronization.
- [x] Freeze F6-A Release Blocker Resolution.
- [x] Freeze F6-B Existing PR Repair.

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

### F5 checkpoint

The fifth pair is frozen as the first authorized repository-content mutation family:

- **F5-A:** a well-scoped HTTP 429 retry defect has protected acceptance tests that already define the
  behavior. The agent must change only the product source, create an isolated branch, and prepare one open
  review PR linked to the still-open issue. Semantic correctness is validated independently of exact source
  syntax.
- **F5-B:** a release source of truth is already correct while two policy-defined maintenance mirrors are
  stale. The agent must synchronize exactly those two non-product artifacts and prepare one open review PR,
  with grouped or separate file-write routes both accepted.

The pair introduces branch/file/PR write permissions while keeping default-branch writes, workflow mutation,
merge authority, and unrelated project state protected.

### F6 checkpoint

The capstone pair is frozen around two end-to-end handoff topologies:

- **F6-A:** a release blocker plus completed candidate-branch CI identifies a deterministic manifest/protocol
  mismatch. Repository policy requires a bounded repair PR against the non-default release branch, followed
  by an issue transition from investigation to fix-in-review while the blocker remains open and unmerged.
- **F6-B:** an existing draft PR breaks legacy configuration compatibility and carries incomplete docs. The
  agent must repair that same head branch in place, preserve protected tests/workflows, mark the same PR ready
  for review, and reconcile the linked issue without creating replacement work or claiming new-head CI passed.

Both deliberately separate "prepared for review" from "merged/released/CI-passed" and use trusted post-run
semantic validation rather than runner timing as the scientific correctness oracle.

## Phase C - cross-scenario calibration

- [x] Check design-level A/B independence within every family. *(Pilot calibration remains pending.)*
- [x] Check design-level within-family difficulty intent. *(Empirical pilot calibration remains pending.)*
- [x] Check progression from orientation through multi-stage work.
- [x] Ensure the matrix contains read-only, conditional-mutation, no-op, and mandatory-mutation cases.
- [x] Ensure no single habitual route or artifact type dominates the experiment by construction.
- [ ] Confirm deterministic fixture reset/isolation for every scenario during implementation planning.
- [x] Confirm the design specifies authoritative pre/post observations for every scored state predicate.
- [x] Freeze the design-level 288-run acquisition target.

## Phase D - pre-coding gate

**Do not begin executable package work until this phase is explicitly reviewed.**

- [ ] Pin the GitHub MCP server revision/image for the experiment.
- [ ] Capture the full discovered individual-tool catalog for the chosen toolsets.
- [ ] Validate and freeze the dedicated-token permission profile against that catalog.
- [ ] Define the exact laboratory-protection excluded-tool list.
- [ ] Confirm the experimental repository/account setup can support the fixtures safely.
- [x] Decide that workflow definitions are always protected infrastructure.
- [x] Decide that frozen scenarios require Actions read/diagnosis, not Actions rerun/cancel/trigger.
- [ ] Choose the fixture reset/isolation strategy, including how unauthorized merges are contained.
- [ ] Confirm reproducible creation/retention of completed CI evidence tied to known SHAs.
- [ ] Announce the transition from design documentation to actual coding.

See [`pre_coding_checkpoint.md`](pre_coding_checkpoint.md) for the consolidated permission, fixture,
Actions, merge-boundary, and scale implications.

## Current blocker status

**Scenario design is complete; actual coding has not started.** The current issue-only GitHub token remains
adequate for qualification but is insufficient for the frozen scientific scenario set. The next task is to
review the pre-coding checkpoint, pin/inspect the exact MCP catalog, and then tell the user exactly which
credential permissions/setup changes are required before executable package work begins.
