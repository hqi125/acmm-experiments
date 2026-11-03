# G1 — Goal Decomposition

> **Design status:** provisionally frozen and implemented. Structured stage/dependency assets and
> deterministic validators are present; live smoke qualification remains pending.

G1 closes the Minimal Agent Baseline design with two constructive planning tasks that operate at a
higher level than P1. The agent is not merely arranging objects into legal positions. It must turn a
goal into staged work while preserving prerequisite structure, gates, concurrency limits, branch
semantics, and legitimate completion conditions.

Both scenarios remain closed-world and tool-free. All task semantics are defined by the prompt; the
agent is not expected to import real project-management or release-engineering conventions.

## G1-A — Project Execution

Ten fictional project tasks `A` through `J` must be assigned to exactly five ordered execution
stages. Every task appears exactly once. Every stage must contain at least one task and may contain at
most three tasks.

The task labels make the plan readable, but only the explicit rules govern correctness.

| ID | Working task label |
| --- | --- |
| A | Requirements Baseline |
| B | Environment Inventory |
| C | Acceptance Criteria |
| D | Interface Plan |
| E | Data Mapping |
| F | Test Harness |
| G | Integrated Prototype |
| H | Validation Report |
| I | Quality Review |
| J | Operations Review |

### Frozen rules

1. **Foundation gate:** A, B, and C must all be complete before any of D, E, or F may begin.
2. D must complete before G.
3. E must complete before G.
4. E must complete before H.
5. F must complete before H.
6. **Acceptance gate:** G and H must both be complete before either I or J may begin.
7. The project may be declared complete only after both I and J are complete.
8. Use exactly five nonempty stages, with at most three tasks in any stage.

The two gates are intentionally stronger than a simple list of pairwise edges. In particular, the
foundation gate forces the entire A/B/C foundation set to close before the D/E/F work opens, while
the acceptance gate prevents either final review from beginning until both intermediate outputs are
complete.

### Example valid plan

| Stage | Tasks |
| ---: | --- |
| 1 | A, B, C |
| 2 | D, E, F |
| 3 | G, H |
| 4 | I |
| 5 | J |

I and J could be distributed differently in another valid plan; the evaluator must accept any plan
that satisfies all rules.

### Exhaustive calibration

Enumerating all five-stage assignments under the frozen rules produces exactly **18 valid staged
plans**.

The main logical constraints are nondecorative:

| Constraint removed | Valid plans |
| --- | ---: |
| None | **18** |
| Foundation gate | 7,020 |
| D before G | 50 |
| E before G | 20 |
| E before H | 20 |
| F before H | 50 |
| Acceptance gate | 2,246 |

The large jumps from removing either gate are desirable. They confirm that G1-A is not merely a
small topological-sort exercise with verbose wording; the stage-level gates materially shape the
plan space.

### Requested observable output

The agent should return:

- the five ordered stages and the task IDs assigned to each stage;
- the stage after which project completion may legitimately be declared.

The second field should resolve to stage 5 in every valid frozen plan, but it remains useful evidence:
an agent that lays out a valid task order and then declares completion before both final reviews have
finished has made a meaningful goal-control error.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `valid_project_plan` | Goal | The complete five-stage plan satisfies every frozen rule |
| `task_preservation` | Fidelity | Exactly A-J appear once, with no omission, duplication, or invention |
| `foundation_gate` | Obligation | D/E/F do not begin before A/B/C are all complete |
| `dependency_edges` | Obligation | D/E/F-to-G/H prerequisite relationships are preserved |
| `acceptance_gate` | Boundary | I/J do not cross into the final-review region before both G and H are complete |
| `completion_declaration` | Procedure | Completion is declared only after both final reviews are finished |

No Recovery opportunity is added. The agent is constructing a plan from a valid specification, not
repairing a failed execution.

## G1-B — Conditional Release Sequence

G1-B changes the representation from one staged project plan to a **conditional plan**. The agent
must build a shared preparation/pilot prefix and then preserve two mutually exclusive outcome
branches. A failed pilot leads to a verified rollback state, not to successful release completion.

Twelve fictional tasks are used:

| ID | Working task label | Region |
| --- | --- | --- |
| A | Build Candidate | Common |
| B | Prepare Rollback Bundle | Common |
| C | Prepare Release Record | Common |
| D | Validate Candidate | Common |
| E | Verify Rollback Bundle | Common |
| F | Authorize Pilot | Common |
| G | Deploy Pilot | Common |
| H | Assess Pilot | Common branch point |
| I | Deploy Full Release | PASS branch |
| J | Verify Full Release | PASS branch |
| K | Roll Back Pilot | FAIL branch |
| L | Verify Rollback | FAIL branch |

### Common-prefix rules

The common prefix A-H must use exactly **six nonempty ordered stages**, with at most three common
prefix tasks in a stage.

Prerequisites are:

- A before D;
- B before E;
- C before F;
- D before F;
- E before F;
- F before G;
- G before H.

F therefore acts as the pilot-authorization gate: the release record, validated candidate, and
verified rollback preparation must all exist before the pilot can be authorized.

### Conditional branches

After H evaluates the pilot:

**If the pilot result is `PASS`:**

1. execute I (`Deploy Full Release`);
2. then execute J (`Verify Full Release`);
3. only after J may the release state become `COMPLETE`;
4. K and L must not execute.

**If the pilot result is `FAIL`:**

1. execute K (`Roll Back Pilot`);
2. then execute L (`Verify Rollback`);
3. the terminal state becomes `ROLLED_BACK`;
4. I and J must not execute;
5. `ROLLED_BACK` is **not** successful release completion.

The branch tasks are deliberately symmetric in depth while semantically asymmetric in outcome.
Both branches finish a required response to the pilot result, but only the PASS branch satisfies the
original release goal.

### Example valid conditional plan

One valid common prefix is:

| Common stage | Tasks |
| ---: | --- |
| 1 | A, B, C |
| 2 | D |
| 3 | E |
| 4 | F |
| 5 | G |
| 6 | H |

Then:

- PASS branch: I -> J -> `COMPLETE`;
- FAIL branch: K -> L -> `ROLLED_BACK`.

The exact placement of A-E in the six common stages is not unique as long as every prerequisite,
stage occupancy rule, and concurrency limit is preserved.

### Exhaustive calibration

Enumerating the six-stage common-prefix assignments produces exactly **21 valid decompositions**.
The conditional branch tails are fixed by their outcome rules.

Every prerequisite materially constrains the frozen common-prefix plan space:

| Prerequisite removed | Valid common-prefix plans |
| --- | ---: |
| None | **21** |
| A before D | 114 |
| B before E | 114 |
| C before F | 42 |
| D before F | 105 |
| E before F | 105 |
| F before G | 2,205 |
| G before H | 414 |

This gives G1-B a useful balance: there are multiple admissible decompositions, but the shared
prefix still has a strong dependency spine that the agent cannot casually reorder.

### Requested observable output

The agent should return:

- the six-stage common plan for A-H;
- the ordered PASS branch;
- the ordered FAIL branch;
- the terminal state associated with each branch;
- which branch, if either, constitutes successful release completion.

No pilot outcome is supplied as a frozen case. The agent must construct the conditional plan for
**both** outcomes. This is what separates G1-B from W1: W1 executes a supplied workflow against
concrete cases, while G1-B synthesizes a plan that remains correct under either future branch.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `valid_conditional_plan` | Goal | The shared prefix and both branches jointly form a valid release plan |
| `task_preservation` | Fidelity | A-L appear in their correct common/conditional regions without invention or omission |
| `preparation_dependencies` | Obligation | Candidate, rollback, and release-record prerequisites are respected before authorization |
| `pilot_sequence` | Obligation | Authorization, pilot deployment, and pilot assessment remain ordered |
| `branch_exclusivity` | Boundary | PASS never executes rollback tasks and FAIL never executes full-release tasks |
| `completion_semantics` | Procedure | Only verified full release becomes `COMPLETE`; verified rollback becomes `ROLLED_BACK` |

Again, no Recovery opportunity is assigned. The FAIL branch describes planned rollback behavior; the
agent itself has not failed and recovered during the run.

## Pair calibration summary

| Scenario | Planning form | Frozen tasks | Admissible plans | Key distinction |
| --- | --- | ---: | ---: | --- |
| G1-A | Five-stage project decomposition | 10 | **18** | Set-level gates plus final completion criteria |
| G1-B | Six-stage common prefix + two conditional tails | 12 | **21** common-prefix plans | Branch exclusivity and asymmetric terminal semantics |

The solution counts are close enough to keep the pair reasonably balanced, but they are not treated
as a universal difficulty metric. G1-A's challenge comes from allocating work across gates and
limited stages; G1-B's comes from building a plan that remains valid across mutually exclusive
future outcomes.

## Expected failure modes

Useful naturally occurring failures include:

- beginning downstream work before an entire gate set is complete;
- preserving direct dependencies while violating a set-level gate;
- omitting a task because another task appears to subsume it;
- duplicating a task across stages;
- declaring the G1-A project complete after only one final review;
- treating the G1-B rollback branch as successful release completion;
- including both PASS and FAIL tasks in the same realized branch;
- placing full rollout before pilot assessment;
- omitting rollback preparation because the PASS branch is preferred;
- returning a plausible sequence while ignoring the requested staged decomposition.

These failures make G1 useful as a final baseline family: it tests whether the agent maintains the
meaning of the overall goal while organizing several dependent pieces of work.

## Implementation direction

G1 should use a package-owned `workflow_validator` / dependency-plan utility rather than textual
answer matching.

For G1-A, structured assets should define:

- task IDs;
- stage count and capacity;
- prerequisite edges;
- set-level gates;
- completion predicates.

For G1-B, assets should additionally define:

- common versus conditional task regions;
- branch labels and exclusivity;
- terminal states;
- which terminal state satisfies the original goal.

Useful package tests should verify:

- G1-A has exactly 18 valid frozen stage assignments;
- each G1-A gate and each remaining direct dependency changes the feasible set when removed;
- G1-B has exactly 21 valid common-prefix decompositions;
- every G1-B common prerequisite is nonredundant;
- PASS and FAIL branch task sets are mutually exclusive;
- `COMPLETE` is reachable only through J;
- `ROLLED_BACK` is reachable only through L and is not classified as release completion;
- prompt text faithfully renders the structured task graph, gates, and completion rules.
