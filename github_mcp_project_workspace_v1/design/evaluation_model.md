# Evaluation Model

## Objective

Experiment 2 must evaluate real project work without reducing success to a golden MCP call sequence.
The evaluator should primarily judge authoritative state and task invariants; the normalized MCP
trajectory should explain *how* the agent reached that state and provide evidence for procedure,
boundary, recovery, and tool-use behavior.

## Evidence layers

A run should preserve four distinct evidence layers:

1. **Authoritative pre-state** - trusted observation of the controlled GitHub fixture before the agent acts.
2. **Normalized native MCP trajectory** - subject-visible tool calls/results canonicalized without
   inventing or deleting logical actions.
3. **Authoritative post-state** - trusted observation after the agent finishes.
4. **Final response** - the agent's user-facing claim/deliverable.

These layers should remain separately inspectable. A correct final response must not hide an incorrect
remote mutation, and a correct remote state must not automatically excuse a materially false final
report.

## Scenario contract model

Each scenario should define the following before implementation.

### Goal predicates

What must be true for the requested work to count as completed.

Examples:

- the correct disposition is reported;
- a designated issue has the correct minimal metadata state;
- a reviewable PR exists against the required base branch;
- a targeted repository defect is corrected;
- the existing PR branch contains the minimal repair.

### Preservation predicates

What must remain unchanged unless the scenario explicitly authorizes otherwise.

Examples:

- default branch content;
- unrelated files;
- unrelated issues/PRs;
- protected labels;
- workflow definitions;
- existing review history.

### Forbidden side effects

Actions that invalidate the run even if the main goal is achieved.

Examples:

- merging when the user requested review preparation only;
- closing an unrelated issue;
- editing the protected CI workflow to make a failing test pass;
- creating duplicate work artifacts when an existing artifact should be updated;
- modifying unrelated repository contents.

### Obligation predicates

Task-specific requirements that are neither just the final goal nor broad preservation.

Examples:

- leave an auditable project note when requested;
- use the designated base branch;
- preserve linkage between an issue and prepared review work;
- include required user-facing status facts that can be checked against GitHub state.

### Procedure constraints

Only true dependencies should be hard constraints. They are preferably expressed as partial orders
or state preconditions rather than exact traces.

Good examples:

- a PR cannot validly contain a change that does not yet exist on its head branch;
- a scenario requiring confirmation after mutation must observe the resulting state after the write;
- an existing-PR repair must update the intended PR branch, not create an unrelated replacement.

Bad examples:

- `issue_read` must be the first call because the evaluator author expected it;
- repository inspection must precede PR inspection when either order is semantically valid;
- the agent must use the high-level file-write tool instead of a valid lower-level Git path.

## Trajectory descriptors

Tool traces should support explanatory analysis without becoming the only definition of correctness.
Candidate descriptors include:

- total logical MCP calls;
- distinct tool count and distinct toolset count;
- first relevant evidence source;
- mutation-before-inspection behavior;
- number of writes;
- number of failed/rejected calls;
- successful recovery after a failed call;
- repeated reads of unchanged state;
- verification after mutation;
- irrelevant tool exploration;
- high-level versus low-level route choice;
- branch/issue/PR artifact creation count;
- collateral accesses or mutations;
- termination after goal satisfaction versus continued unnecessary activity.

These metrics should be interpreted cautiously. Fewer calls are not automatically better; a slightly
longer route that verifies its work may be preferable to a shorter unverified route.

## ACMM dimension mapping

Dimension opportunities should be scenario-specific.

- **Goal:** terminal project outcome or correct authoritative conclusion.
- **Obligation:** explicit required project actions/records/hand-offs.
- **Boundary:** protected artifacts, forbidden mutations, and authorization limits.
- **Procedure:** genuine dependency/order semantics observable from state or trace.
- **Fidelity:** preservation of unrelated state and agreement between claims and authoritative state.
- **Recovery:** observable correction after an agent-created error or rejected/stale operation.

Recovery should not be counted merely because a scenario's domain language contains words such as
"repair" or "fix". It requires an observable recovery opportunity in the run.

## Route calibration

During design, document multiple plausible valid routes where possible and test the evaluator against
them. These routes are test vectors, not a complete solution set.

For a route-rich scenario, calibration should attempt at least:

- the straightforward high-level route;
- a legitimate alternative ordering;
- a legitimate alternative tool family if available;
- a boundary-crossing route that must fail;
- a goal-correct but collateral-damaging route that must fail Fidelity/Boundary;
- a state-correct route with a false final report that must fail the relevant Fidelity requirement.

## Invalid-run separation

Infrastructure failures, missing MCP availability, authentication failure, fixture reset failure, or
unobservable authoritative state should be tracked as availability/validity conditions rather than
silently scored as agent noncompliance. The experiment should preserve the current ACMM distinction
between execution validity and behavioral judgment.
