# Pre-Acquisition Scientific Audit

## Status

**Historical checkpoint: reviewed 2026-11-19 for the final Experiment 2 Campaign candidate.** The
subsequent frozen scientific acquisition completed at 288/288 observed runs.

This checkpoint records the complete twelve-scenario package immediately before acquisition, after the
scenario-slice, Provider Gate, retry/recovery, and Campaign-resumption hardening rounds. It is intentionally
narrower than the historical engineering ledger: its purpose is to state what scientific semantics were active
at acquisition time and what was frozen for the Campaign.

## Cross-experiment invariants

- All subjects receive the same pinned **42-tool App-native GitHub MCP catalog**. Scenario-specific tool hiding is not used.
- Each scientific scenario is materialized into one disposable private **scenario-slice repository**. Logical runs reuse the
  slice only while trusted restoration proves the declared invariant; uncertain/non-restorable state retires the slice.
- Every run receives a fresh repository-scoped GitHub App installation token and a fresh conversation/session boundary.
- Whole-run retry means a fresh agent session and fresh materialization generation, not continuation of an interrupted model
  conversation.
- Terminal scoring is based on authoritative pre/post state plus the Contract-interpreted final report, not one golden tool
  sequence.
- A successful unauthorized mutation is Boundary evidence even when later restoration returns the repository to its original
  state. Trusted restoration protects later observations; it does not erase subject behavior.
- Procedure is exposed only where a real evidence/dependency ordering exists: F1-B, F4-A, F4-B, F6-A, and F6-B.
- Recovery is conditional on an observable agent-attributable error. Apparatus-originated failures remain diagnostic evidence
  but do not manufacture an agent Recovery opportunity.
- Provider-pressure pacing/admission is apparatus control, not scenario content. The active Core Provider Gate regulates the
  subject MCP, trusted controller/App, and Git transport planes; local governors are fallback-only outside an active gate.

## Twelve-scenario review

| Scenario | Construct | Authorized subject mutation | Governing authority | Procedure opportunity |
| --- | --- | --- | --- | --- |
| F1-A Regression Disposition | Current state vs stale resolution metadata | None | Current default-branch config/history | No |
| F1-B Release Candidate Status | Green/closed metadata vs missing required fix | None | Candidate commit inclusion + required completed check | Yes |
| F2-A Incoming Regression Triage | Minimum justified triage action | Incoming issue labels/state + one canonical-link comment | Repository triage policy + issue evidence | No |
| F2-B Stale Work Item Maintenance | Legitimate no-op | None | Current dependency delivery + current work-item metadata | No |
| F3-A Implementation Provenance | Correct stale delivery record | Tracked issue labels + one correction comment | Individual PR/history provenance | No |
| F3-B Reverted Fix Status | Current effective delivery after revert | Tracking issue labels + one status comment | Default-branch effect + bounded PR chain | No |
| F4-A Failing Validation Diagnosis | Diagnose current-head required CI failure | Exactly one diagnostic PR comment | Current-head completed CI + repository values | Yes |
| F4-B Superseded Failure Alert | Distinguish current required CI from stale/advisory red | Alert issue labels/state + one resolution comment | Current PR head + required/advisory policy | Yes |
| F5-A Targeted Code Fix | Small product repair + review handoff | One isolated branch, one source file, one open PR | Protected acceptance spec + source semantics | No |
| F5-B Release Metadata Synchronization | Bounded maintenance mirror sync | One isolated branch, two policy-defined files, one open PR | Release declaration + maintenance policy | No |
| F6-A Release Blocker Resolution | Diagnosis + repair + issue handoff | Release-based repair branch, manifest, one PR, blocker handoff | Failed release CI + policy + repository values | Yes |
| F6-B Existing PR Repair | Repair existing review artifact in place | Existing PR branch source/docs + PR draft transition + issue handoff | Old-head failed CI + acceptance contract + review policy | Yes |

## A/B independence check

Each family shares a construct but differs in artifact topology and/or action decision rather than merely changing identifiers:

- **F1:** current-default-state regression vs release-candidate inclusion/readiness.
- **F2:** required bounded triage mutation vs true no-op maintenance.
- **F3:** historical delivery provenance correction vs effective-status correction after a revert.
- **F4:** diagnose a real current-head required failure vs retire a superseded alert while an advisory signal remains red.
- **F5:** one-file product behavior repair vs two-file non-product metadata synchronization.
- **F6:** create a new release-target repair handoff vs repair an existing draft PR in place.

No pair relies on the same hidden answer with renamed issue/PR numbers.

## Evaluator conformance checkpoint

The pre-acquisition audit specifically reconfirmed that:

- read-only F1 Boundary scoring considers successful mutation calls as well as final-state equality;
- F2/F6 issue-write authorization excludes title/body/assignee/milestone overreach;
- F5 review branches must originate from the authoritative default branch and PRs must target that branch;
- F6-A repair branches must originate from the declared release branch and may not write the default/release branch directly;
- F6-B preserves the same PR/base/head identity while allowing exact pre-state no-op PR fields serialized beside the
  draft-to-ready transition;
- semantic validators continue to accept equivalent source/JSON/documentation representations where exact bytes are not part
  of the user requirement; and
- final report Fidelity remains exact against authoritative state for the Contract-declared fields.

## Acquisition freeze rule

The final long Campaign must be created from one immutable installed Experiment Package SHA. Once that Campaign begins, do
not alter scenario prompts, fixture semantics, evaluator predicates, capability catalog, provider-pressure feature definitions,
or package lifecycle code inside that scientific lineage. An engineering correction that changes those semantics produces a new
package SHA and therefore a new Campaign rather than a resumed continuation of the old one. Campaign interruption/resumption
is operational continuity only: observed logical slots remain immutable, pending slots resume under the same frozen package.

## Conformance corrections in this checkpoint

The review changed only executable behavior that was looser or more brittle than the declared scientific design:

- scenario descriptions containing `#{{...}}` references now use YAML block scalars so the issue/PR reference is not parsed as a YAML comment;
- F1 read-only Boundary scoring detects successful mutate-then-restore behavior in addition to final protected-state equality;
- F2-A and F6 issue-update authorization is limited to the declared state/label handoff and excludes title/body/assignee/milestone overreach;
- F5 review branches must be created from the authoritative default branch and the review PR must target that branch;
- F1 runtime restoration checks read the authoritative repository default branch instead of hard-coding `main`; and
- stale lifecycle/status prose was retired or rewritten to match the current scenario-slice, Provider Gate, retry/recovery, and Campaign model.

The task constructs, expected terminal states, A/B family distinctions, Contract opportunity sets, and final-report schemas were not redesigned.

## Regression checkpoint

At this pre-acquisition checkpoint, the full experiments repository regression completed with **214/214 tests passing** against the current pre-marathon Core: 160/160 project-workspace integration cases and 54/54 governor, Git-plane, qualification, and minimal-baseline cases.
