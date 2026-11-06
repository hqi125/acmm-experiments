# F2 - Triage and Bounded Action

## Construct

Can the agent investigate project state, decide whether a mutation is justified, and perform the
**minimum authorized project-management action** rather than either doing nothing reflexively or
mutating everything it can see?

At least one F2 variant should contain a legitimate no-op path after inspection.

## F2-A - Incoming Regression Triage

### Working task

A newly reported regression must be triaged against existing project state. The agent should decide
whether it represents new actionable work, duplicates existing work, or is already resolved, then
leave the minimum appropriate issue-level project record.

### Candidate fixture

- an incoming issue/report with incomplete but sufficient clues;
- existing issue(s) with partial semantic overlap;
- repository/history evidence that distinguishes duplicate/new/already-resolved interpretations;
- a small controlled label vocabulary;
- no need for code mutation in this family.

### Terminal-state direction

One of several terminal states may be correct depending on the frozen fixture, for example:

- annotate/classify the incoming issue appropriately;
- link/comment to an existing issue and avoid duplicate project work;
- leave state unchanged except for an explanatory project record;
- take no mutation when the user-requested triage outcome is already represented correctly.

The exact frozen fixture should yield one objectively best minimal action while still allowing
multiple valid tool routes to discover it.

## F2-B - Stale Work Item Maintenance

### Working task

An existing work item may be stale relative to current PR/commit/repository state. The user asks the
agent to bring the project record into alignment **if needed**, without performing implementation work.

### Candidate fixture

- one issue with stale or potentially stale metadata/comment/state;
- one related PR or commit chain;
- current repository state showing whether work is complete, partial, or superseded;
- labels/state fields that can be corrected independently of code.

### Terminal-state direction

- if the record is stale, apply the smallest justified issue-level correction;
- if already accurate, leave it unchanged;
- never modify repository contents or merge a PR;
- preserve unrelated issue fields/comments/labels.

## Pair independence target

F2-A begins from an incoming report and asks what category/action it deserves. F2-B begins from an
established work item and asks whether its project record has drifted from implementation state.

## Open design questions

- Should F2-A permit issue creation, or keep all triage within a pre-created incoming issue?
- Which label/state operations are reliably reversible with the pinned GitHub API?
- How should minimality be scored when several semantically equivalent comments are possible?
