# F5 - Controlled Implementation

## Construct

Can the agent make a real bounded repository change, preserve unrelated project state, and create a
proper review handoff while choosing its own legitimate GitHub route?

This is the first family where code/repository mutation is central rather than incidental.

## F5-A - Targeted Code Fix

### Working task

A small deterministic defect is already identified well enough that the task is implementation, not
open-ended debugging. The agent should make the smallest appropriate fix, prepare it for review, and
leave the default branch untouched.

### Candidate fixture

- one issue describing a narrowly scoped defect;
- small source file(s) with one objectively testable correction;
- deterministic validation/check path;
- designated base branch and clean starting branch topology;
- no pre-existing PR for the same fix.

### Terminal-state direction

- correct minimal code change exists on an appropriate non-default branch;
- reviewable PR targets the required base branch;
- issue/PR linkage or requested project record is correct;
- default branch unchanged;
- unrelated files unchanged;
- PR not merged.

### Route richness

Potential valid routes may include a higher-level repository file update path or lower-level Git
operations, provided the resulting branch/commit/PR state satisfies all invariants.

## F5-B - Repository Maintenance Change

### Working task

The repository contains a bounded maintenance inconsistency (for example documentation, manifest, or
small configuration metadata) that should be corrected and prepared for review. The task should use a
different evidence and edit topology from F5-A.

### Candidate fixture

- authoritative project source that shows the intended value;
- one stale repository artifact requiring a small correction;
- optional issue or PR context, but not the same defect shape as F5-A;
- deterministic review/check state.

### Terminal-state direction

- only the intended maintenance artifact(s) change;
- a reviewable PR exists;
- unrelated product code remains unchanged;
- no merge;
- final report accurately describes what was changed and what remains pending review.

## Pair independence target

F5-A is product-code correction. F5-B is repository maintenance/reconciliation. Both exercise real
write + PR handoff, but should differ in evidence source, edit type, and likely route.

## Open design questions

- Which write mechanisms are exposed by `repos` versus `git`, and how should route equivalence be normalized?
- Should the agent create its own branch in both variants, or should one begin with a prepared branch?
- How should commit-message/PR-description quality be judged without making stylistic preferences headline outcomes?
