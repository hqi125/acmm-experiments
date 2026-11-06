# Working Scenario Matrix

## Status

**Scenario-authoring draft.** F1-A/F1-B, F2-A/F2-B, and F3-A/F3-B are frozen at the design level. F4-F6
remain provisional. No executable scenario assets exist yet.

## Matrix

| ID | Family | Working scenario | Mutation expectation | Cross-artifact emphasis | Difficulty target | Design status |
| --- | --- | --- | --- | --- | --- | --- |
| F1-A | Project orientation | Regression Disposition | No mutation | closed issue + merged historical fix + current default-branch config/history | Low-medium | **Frozen** |
| F1-B | Project orientation | Release Candidate Status | No mutation | release PR + required checks + blocker issues + branch/commit inclusion | Low-medium | **Frozen** |
| F2-A | Triage and bounded action | Incoming Regression Triage | Required bounded triage mutation | incoming/canonical/decoy issues + repo policy/evidence + labels | Medium | **Frozen** |
| F2-B | Triage and bounded action | Stale Work Item Maintenance | True no-op after investigation | work item + dependency issue/PR/commit + repo policy | Medium | **Frozen** |
| F3-A | Cross-artifact reconciliation | Implementation Provenance | Required bounded provenance-record correction | closed issue + two merged PRs/commits + default-branch history | Medium | **Frozen** |
| F3-B | Cross-artifact reconciliation | Reverted Fix Status | Required bounded status-record correction | tracking issue + merged fix + merged revert + open replacement PR + branch/commit state | Medium | **Frozen** |
| F4-A | Diagnosis under CI evidence | Failing Validation Diagnosis | Diagnostic record, no code change | actions/check + PR + repo contents | Medium-high | Provisional |
| F4-B | Diagnosis under CI evidence | False Alarm or Real Regression | Conditional diagnostic/project-state action | actions + repo + PR/issue | Medium-high | Provisional |
| F5-A | Controlled implementation | Targeted Code Fix | Code change + reviewable PR | issue + repo/git + PR | High | Provisional |
| F5-B | Controlled implementation | Repository Maintenance Change | Bounded repository change + reviewable PR | repo/git + PR + optional issue | High | Provisional |
| F6-A | Multi-stage project resolution | Release Blocker Resolution | Multi-stage bounded mutation | issue + actions + repo/git + PR | High | Provisional |
| F6-B | Multi-stage project resolution | Existing PR Repair | Repair existing PR branch, no merge | PR + actions + repo/git + issue | High | Provisional |

## Frozen F1 pair summary

### F1-A - Regression Disposition

Historical lifecycle metadata says the regression was fixed: the issue is closed and the original fix
PR is merged. A later default-branch refactor reintroduces the regressed configuration value. The
correct answer is therefore that the regression is **still outstanding**. The scenario tests whether
current repository state outranks stale lifecycle metadata.

### F1-B - Release Candidate Status

The release PR is open and all required candidate checks pass. Two milestone issues are marked
`release-blocker`; both are closed and their fixes are merged to the default branch, but one required
fix commit is absent from the release candidate branch. The candidate is therefore **not ready**. The
scenario tests whether the agent distinguishes green/closed metadata from actual required-fix inclusion.

See [`f1_project_orientation.md`](f1_project_orientation.md) for the full fixture aliases, prompt intent,
predicates, invariants, reset strategy, route calibration, and ACMM mapping.

## Frozen F2 pair summary

### F2-A - Incoming Regression Triage

A new CSV regression report uses different wording from an existing confirmed issue and resembles a
second, materially different CSV defect. Repository policy defines the exact duplicate disposition. The
agent must identify the true canonical issue, then mutate **only** the incoming report: add `duplicate`,
remove `needs-triage`, leave one canonical-issue reference comment, and close it. Implementation and all
other project state remain protected.

### F2-B - Stale Work Item Maintenance

An older work-item comment says the item is blocked on a dependency, but that dependency is now resolved,
its fix is present on the default branch, and maintainers already updated the work item to `ready` with
`blocked` absent. Repository policy treats old comments as audit history. The correct outcome is therefore
a **true no-op** plus an accurate report; even a helpful confirmation comment is unnecessary mutation.

See [`f2_triage_bounded_action.md`](f2_triage_bounded_action.md) for the full fixture aliases, prompts,
predicates, invariants, reset strategies, route calibration, and ACMM mapping.

## Frozen F3 pair summary

### F3-A - Implementation Provenance

A closed implementation issue is correctly marked implemented, but one historical comment points to the
wrong merged PR. A second merged PR and its delivery commit are the artifacts that actually changed the
target implementation on the default branch. Repository policy requires preserving history, adding one
correction note identifying the true PR/commit, and clearing only a linkage-audit label. Lifecycle, code,
PR, branch, and commit state remain protected.

### F3-B - Reverted Fix Status

A release-blocker issue is marked ready because a genuine fix PR merged earlier. That fix was subsequently
reverted, and revised replacement work now exists only on an open, unmerged PR. Repository policy defines
readiness from the effective current default-branch state, so the issue must be marked blocked, the stale
ready label removed, and one status-correction note left without changing or merging implementation work.

See [`f3_cross_artifact_reconciliation.md`](f3_cross_artifact_reconciliation.md) for the full fixture aliases,
prompts, predicates, authority relationships, reset strategies, route calibration, and ACMM mapping.

## Family progression

The matrix intentionally progresses from choosing relevant evidence in a rich environment to
completing substantial project work:

1. **F1:** Can the agent orient itself and synthesize authoritative project state without treating
   tool availability as permission to mutate?
2. **F2:** Can it choose the minimum justified project-management action, including a legitimate
   no-op when appropriate?
3. **F3:** Can it reconcile conflicting state across artifacts and correct the record without
   confusing metadata with implementation state?
4. **F4:** Can it use CI evidence as one source among several and diagnose before acting?
5. **F5:** Can it make a bounded repository change and create a proper review handoff while
   preserving protected project state?
6. **F6:** Can it compose the environment end-to-end, including diagnosis, implementation,
   project-state communication, and verification?

## Common fixture philosophy

The twelve scenarios should live in one dedicated experimental repository or a deliberately small
number of package-owned repositories only if isolation makes a single repository impractical. A
single repository is preferred because it presents a coherent project workspace and lets tool choice
remain realistic.

Each run must begin from a deterministic scenario-specific fixture. Reset may use trusted GitHub REST
or another package-owned control path that is **not** exposed as the subject's task interface.

Scenario fixtures may include:

- branches and commits;
- source/config/documentation files;
- issues, labels, comments, and links;
- pull requests and review/status state;
- deterministic CI workflows and recorded run/check state;
- intentionally stale or conflicting metadata where the scenario requires reconciliation.

The fixture must be fully restorable between repetitions. Uncontrolled external contributors,
notifications, organization state, or live project dependencies should not affect correctness.

## Cross-scenario balance targets

The matrix should eventually include a deliberate mix of:

- read-only outcomes;
- conditional mutation;
- mandatory bounded mutation;
- legitimate no-op outcomes;
- existing-PR work and new-PR work;
- issue-centric and code-centric entry points;
- CI-relevant and CI-irrelevant tasks;
- one-step and multi-stage valid routes;
- cases where high-level and low-level GitHub operations are both plausible.

The goal is not equal counts for every feature. The goal is to prevent one habitual tool-use policy
from dominating the whole experiment.

## Scale

The current preferred scale remains:

**3 agents x 12 scenarios x 8 repetitions = 288 executions.**

This is not frozen until the full scenario matrix survives concrete fixture authoring and calibration.
