# Working Scenario Matrix

## Status

**Early design draft.** IDs and families are stable enough for discussion, but no scenario is frozen.
The names below are working labels. Concrete repository fixtures, prompts, terminal predicates, and
calibration are developed in the corresponding family documents.

## Matrix

| ID | Family | Working scenario | Mutation expectation | Cross-artifact emphasis | Difficulty target |
| --- | --- | --- | --- | --- | --- |
| F1-A | Project orientation | Regression Disposition | No mutation | issue + PR/commit/repo evidence | Low-medium |
| F1-B | Project orientation | Release Candidate Status | No mutation | PR + actions + issue/repo evidence | Low-medium |
| F2-A | Triage and bounded action | Incoming Regression Triage | Conditional issue-level mutation | issue + repo/history + labels | Medium |
| F2-B | Triage and bounded action | Stale Work Item Maintenance | Conditional issue-level mutation/no-op | issue + PR/commit state | Medium |
| F3-A | Cross-artifact reconciliation | Implementation Linkage | Minimal metadata/comment correction | issue + PR + commit + checks | Medium |
| F3-B | Cross-artifact reconciliation | Conflicting Status Signals | Minimal state correction or no-op | issue + PR + branch/check state | Medium |
| F4-A | Diagnosis under CI evidence | Failing Validation Diagnosis | Diagnostic record, no code change | actions/check + PR + repo contents | Medium-high |
| F4-B | Diagnosis under CI evidence | False Alarm or Real Regression | Conditional diagnostic/project-state action | actions + repo + PR/issue | Medium-high |
| F5-A | Controlled implementation | Targeted Code Fix | Code change + reviewable PR | issue + repo/git + PR | High |
| F5-B | Controlled implementation | Repository Maintenance Change | Bounded repository change + reviewable PR | repo/git + PR + optional issue | High |
| F6-A | Multi-stage project resolution | Release Blocker Resolution | Multi-stage bounded mutation | issue + actions + repo/git + PR | High |
| F6-B | Multi-stage project resolution | Existing PR Repair | Repair existing PR branch, no merge | PR + actions + repo/git + issue | High |

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

This is not frozen until the scenario matrix survives concrete fixture authoring and calibration.
