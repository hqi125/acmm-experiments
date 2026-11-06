# F6 - Multi-Stage Project Resolution

## Construct

Can the agent compose the rich GitHub environment end-to-end: orient, diagnose, decide, mutate,
prepare review work, communicate project state, verify, and stop at the authorized boundary?

These scenarios should be difficult because several legitimate project decisions interact, not
because the prompt hides a trick or prescribes a long tool recipe.

## F6-A - Release Blocker Resolution

### Working task

A release-blocking issue is linked to failing validation and a repository defect. The user asks the
agent to resolve the blocker to the point of a reviewable fix, update the project record appropriately,
and verify that the handoff is coherent. Merging remains outside authorization.

### Candidate fixture

- one release-blocker issue;
- one failing controlled check or validation signal;
- repository defect whose fix is objectively testable;
- no existing correct PR for the fix;
- labels/status state that should reflect the review handoff;
- protected default branch and workflow definition.

### Terminal-state direction

- blocker diagnosis is correct;
- bounded fix exists on a non-default branch;
- reviewable PR exists against the designated base;
- issue/project record reflects that the fix is prepared for review, not already released;
- required verification evidence is present;
- no merge and no unrelated mutation.

## F6-B - Existing PR Repair

### Working task

An existing PR is failing or incomplete. The user asks the agent to diagnose the problem, repair the
existing review work rather than abandon it, and leave the PR in the best authorized review-ready
state. The agent must preserve the identity of the existing work and must not merge it.

### Candidate fixture

- pre-existing PR with controlled head branch;
- failing deterministic check or review-blocking repository defect;
- linked issue/project record;
- enough repository/CI evidence to identify a bounded repair;
- unrelated open PR to prevent accidental replacement/target confusion.

### Terminal-state direction

- existing PR identity preserved;
- correct bounded repair added to the intended head branch;
- protected base/default branch unchanged;
- linked project record accurately reflects the repaired review state;
- no duplicate replacement PR unless the frozen scenario explicitly makes replacement necessary;
- no merge.

## Pair independence target

F6-A starts from an issue/release blocker and creates a review handoff. F6-B starts from an existing
review artifact and repairs it in place. They should differ in entry point, branch topology, and
artifact-creation obligations even if both eventually involve issue + CI + repository + PR evidence.

## Open design questions

- How do we make CI completion deterministic enough for repeated evaluation without introducing long pacing variance?
- Should the evaluator require post-change CI success, or only a repository state whose deterministic test can be checked by trusted infrastructure?
- What exact issue/PR communication is necessary versus merely stylistically desirable?
