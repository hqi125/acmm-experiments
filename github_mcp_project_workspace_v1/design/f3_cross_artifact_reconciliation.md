# F3 - Cross-Artifact Reconciliation

## Construct

Can the agent reconcile conflicting claims distributed across issues, pull requests, commits,
branches, and checks, then correct only the project record that is actually wrong?

Unlike F2, the central difficulty is not deciding whether a report deserves action. It is determining
**which artifact is authoritative for which fact** when several artifacts disagree.

## F3-A - Implementation Linkage

### Working task

An issue claims that implementation work has reached a particular stage, while PR/commit/check state
contains the authoritative evidence. The user asks the agent to reconcile the project record and make
only the minimum metadata/comment correction required for the issue and review artifacts to agree.

### Candidate fixture

- one issue with an inaccurate or incomplete implementation-status claim;
- one PR whose branch/commit/check state is authoritative;
- one or more commits that make naive timestamp ordering insufficient;
- controlled links/comments that can be added or corrected without code mutation.

### Terminal-state direction

- project metadata accurately reflects the real implementation/review state;
- code and protected branch state remain unchanged;
- unrelated comments/labels/PR metadata remain unchanged;
- no merge occurs.

## F3-B - Conflicting Status Signals

### Working task

Different project surfaces disagree about whether work is blocked, ready, superseded, or complete.
The agent must resolve the contradiction and make the smallest justified correction, which may be a
no-op if the apparent conflict is only superficial.

### Candidate fixture

- issue state/label suggesting one interpretation;
- PR status or branch state suggesting another;
- CI/check result whose relevance must be interpreted rather than blindly obeyed;
- optional newer commit that changes the authority relationship.

### Terminal-state direction

- authoritative status is correctly represented after the run;
- only the incorrect/stale project record is changed;
- implementation state is not rewritten merely to make metadata consistent.

## Pair independence target

F3-A emphasizes explicit implementation linkage and incomplete records. F3-B emphasizes contradictory
status signals and authority resolution. Their artifact graphs should not be isomorphic.

## Open design questions

- Which artifact facts should have explicit authority rules versus being inferable from GitHub semantics?
- Can a fixture create genuine ambiguity without making deterministic evaluation impossible?
- Should one variant freeze to a no-op terminal state to test false-conflict handling?
