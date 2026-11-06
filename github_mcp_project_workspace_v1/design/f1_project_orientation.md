# F1 - Project Orientation

## Construct

Can the agent orient itself inside a rich GitHub workspace, identify which project artifacts are
actually authoritative for the user's question, and synthesize the correct current state without
unnecessary mutation?

The entire MCP capability envelope remains visible. The challenge is **relevance selection and
state interpretation**, not tool scarcity.

## F1-A - Regression Disposition

### Working task

A reported regression has an issue and related development history. The user asks whether the
regression is still outstanding and what its current disposition is. The agent should investigate the
project and report the authoritative state without modifying anything.

### Candidate fixture

- one open regression issue containing an older problem statement;
- one related PR/commit path that may or may not fully resolve it;
- current repository contents that reveal whether the problematic behavior remains;
- optional check/status evidence that helps disambiguate implementation state;
- unrelated nearby issues/PRs to prevent simple "take the latest object" heuristics.

### Terminal-state direction

- no GitHub mutation anywhere in the protected fixture;
- final response correctly states whether the regression remains outstanding;
- final response cites/checks the relevant current project state rather than trusting stale issue text.

### Plausible valid routes

Examples only:

- issue -> linked PR -> changed files/current source -> conclusion;
- repository search/history -> issue/PR confirmation -> conclusion;
- PR/commit evidence first -> issue context -> current source verification.

### Failure modes to preserve

- treating an open issue as proof the bug still exists;
- treating a merged/closed PR as proof the bug is fixed without inspecting relevant state;
- mutating labels/comments despite a read-only user request;
- reporting a status inconsistent with current repository state.

## F1-B - Release Candidate Status

### Working task

The user asks whether a named release candidate is currently ready for review/release and, if not,
what concrete blocker remains. The answer must be derived from current PR/check/issue/repository
state. No mutation is authorized.

### Candidate fixture

- one release-oriented PR or branch;
- deterministic Actions/check state;
- one linked blocker issue or project note;
- repository state that distinguishes a genuine blocker from stale project metadata;
- unrelated passing/failing checks for noise control.

### Terminal-state direction

- project state remains byte/state equivalent to pre-state;
- final response correctly identifies readiness and the governing blocker/no-blocker evidence;
- response does not invent required work not supported by the fixture.

## Pair independence target

F1-A is issue/regression centered and uses implementation state to interpret a report. F1-B is
release/readiness centered and uses CI/PR state to interpret project readiness. Both are read-only,
but the authoritative evidence topology should differ materially.

## Open design questions

- How much source inspection is needed in F1-A without turning it into code diagnosis?
- Should F1-B use one failing check with a stale blocker issue, or one passing check with a still-real
  non-CI blocker?
- What final response structure gives deterministic checking without forcing tool-trace disclosure?
