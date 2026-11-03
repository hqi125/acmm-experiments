# Minimal Agent Baseline

> **Status:** design draft. This directory is not yet an executable Experiment Package. The
> Contract, runtime, evaluators, and package manifest will be added after the scenario design is
> frozen.

`minimal_agent_baseline_v1` is the first experiment in the reworked ACMM research roadmap. It
establishes a statistically mature, tool-free reference baseline for the three qualified agent
systems before later experiments add a controlled real tool and then isolated agent-side features.

The experiment is intentionally designed as an independent study rather than as a continuation of
the retired built-in Experiment 1-4 series. ACMM is the measurement instrument; the scientific
question and task design lead the experiment.

## Research question

The working research question is:

> Under the same qualified LLM and each agent system's minimal controlled configuration, how
> reliably do the agent systems complete structured, multi-step tasks when no experiment-provided
> tools or optional agent features are available?

The study does **not** attempt to determine which agent is universally best. It characterizes the
behavior of the agent layer under a shared minimal condition: instruction handling, planning,
constraint preservation, state maintenance, policy application, reconciliation, verification,
workflow control, goal decomposition, termination, and run-to-run consistency.

The current qualified cohort uses the shared `gpt_oss_120b_cloud_v1` LLM baseline. Agent-native
orchestration, unavoidable system prompting, response mechanisms, and other irreducible agent
behavior remain part of the system under study; the experiment does not pretend that the three
agents are internally identical.

## Why this baseline is tool-free

The roadmap intentionally separates two useful baselines:

1. **Minimal Agent Baseline** — no experiment-provided tools. This is the cleanest reference for
   the agent layer itself.
2. **Real-tool baseline** — a later independent experiment introduces exactly one controlled real
   capability and asks what changes when the agent must orchestrate it.

Combining both into this experiment would turn the first study into a tool-availability factorial,
double the condition space, and blur the reference condition. The later tool experiment can be
statistically mature in its own right and can deliberately carry forward matched task constructs
where causal comparison is useful.

No dummy tool, empty fake apparatus, or artificial tool-violation scenario should be introduced to
make a tool-free study fit old infrastructure assumptions.

## Planned scale

The scientific plan targets breadth and within-scenario stability directly rather than starting
with an intentionally undersized study. Small engineering smoke runs remain appropriate, but the
planned acquisition should be mature from the outset.

| Candidate design | Runs / agent | Total runs | Main tradeoff |
| --- | ---: | ---: | --- |
| 12 scenarios x 6 reps | 72 | 216 | Economical mature minimum, but weaker scenario and repetition depth |
| 12 scenarios x 8 reps | 96 | 288 | Strong repeatability, moderate task breadth |
| 16 scenarios x 6 reps | 96 | 288 | Better breadth, somewhat weaker within-scenario stability |
| **16 scenarios x 8 reps** | **128** | **384** | **Selected: strongest balance of breadth and repeatability** |
| 20 scenarios x 8 reps | 160 | 480 | Excellent breadth, but authoring and validation burden rises substantially |

The selected design is therefore:

**3 agents x 8 task families x 2 independently authored scenario variants x 8 repetitions = 384
planned executions.**

Sixteen scenarios provide breadth across task constructs. Eight fresh repetitions per scenario
provide substantially better resolution of stochastic stability than five repetitions while keeping
the experiment operationally realistic.

## Statistical interpretation of the hierarchy

ACMM's evidence hierarchy creates many observations below the run level, but those observations are
nested and must not be treated as independent samples merely to inflate `N`.

| Level | What it tells us | What increasing it improves |
| --- | --- | --- |
| Agent / subject | System being compared | Cross-agent comparison |
| Scenario family | Capability/task construct being sampled | Construct breadth and generalizability |
| Scenario | One concrete experimental situation | Breadth across task instances |
| Repetition | Fresh execution of the same scenario | Stochastic stability and repeatability |
| Run | Scenario x repetition x agent | Precision of run-level outcomes |
| Opportunities / judgments | Observable requirement-level evidence inside a run | Diagnostic resolution |
| Dimension aggregation | G/O/B/P/F/R summaries | Interpretation of behavioral mechanisms |

There is no single law-of-large-numbers count for the whole hierarchy. The relevant count depends on
the claim. Repetitions support claims about stability on a scenario; scenarios and families support
claims about task-space behavior; lower-level opportunities explain how a run succeeded or failed.
They do not turn one trajectory into many independent experiments.

Headline analysis should therefore remain scenario- or family-balanced rather than allowing a
scenario with more ACMM opportunities to silently receive more scientific weight. Uncertainty
analysis should respect nesting, with a hierarchical/cluster bootstrap as the leading design:
resample scenarios or families, then repetitions within those scenarios, and recompute the agent
metric.

A useful shorthand for the design is:

> **Scenarios provide generalization. Repetitions provide reliability. Opportunities provide
> diagnostic resolution.**

## Scenario architecture

The study contains eight conceptual task families with two variants each. Variant A and Variant B
share a construct, not a template: surface representation, entities, and solution path should differ
while overall difficulty remains comparable.

| ID | Family | Working scenario | Primary challenge |
| --- | --- | --- | --- |
| P1-A | Constraint planning | Workshop Schedule | Two-dimensional time/room construction under interacting constraints |
| P1-B | Constraint planning | Batch Sequence | Linear sequencing with precedence, adjacency, separation, and position rules |
| P2-A | Allocation | Project Staffing | Cardinality-constrained grouping with eligibility and coverage |
| P2-B | Allocation | Storage Zones | Weighted-capacity placement with eligibility and relationship rules |
| S1-A | Ordered state transformation | Inventory Ledger | Preserve state through ordered conditional numeric/resource updates |
| S1-B | Ordered state transformation | Case Lifecycle | Preserve legal categorical transitions and side effects |
| D1-A | Policy-governed decisions | Access Requests | Apply allow/deny/escalate policy with precedence and exceptions |
| D1-B | Policy-governed decisions | Service Routing | Apply routing, priority, exception, and fallback rules |
| R1-A | Information reconciliation | Canonical Records | Resolve conflicting records using field authority and timestamps |
| R1-B | Information reconciliation | Effective Configuration | Resolve layered configuration using overrides, locks, and fallbacks |
| V1-A | Audit and correction | Schedule Repair | Detect defects and produce a minimum-change valid repair |
| V1-B | Audit and correction | Manifest Repair | Detect missing/inconsistent fields and repair the artifact |
| W1-A | Conditional workflow | Request Workflow | Execute required branching steps and stop/escalation conditions |
| W1-B | Conditional workflow | Incident Workflow | Execute a different finite workflow from supplied evidence flags |
| G1-A | Goal decomposition | Project Execution | Build a staged plan from dependencies, gates, and acceptance criteria |
| G1-B | Goal decomposition | Conditional Release Sequence | Build a shared release prefix plus mutually exclusive pass/fail branches |

Detailed design notes live under [`design/`](design/README.md). All eight families — P1, P2, S1,
D1, R1, V1, W1, and G1 — now have concrete frozen-draft instances and calibration results. The
scenario-design phase is complete; the next phase is to translate the frozen drafts into structured
scenario assets, Contract entries, deterministic evaluators, and package tests.

## Common task-design rules

All scenarios should obey the following rules:

- Everything needed to solve the task is supplied in the prompt; external knowledge is irrelevant.
- No hidden state or experiment-provided tools are required.
- Core outcomes are deterministically evaluable; no LLM-as-judge is needed for headline outcomes.
- Harmless Markdown, whitespace, or field-order differences should not become scientific failures.
- The prompt asks for observable task outputs, never hidden chain-of-thought.
- Difficulty should arise from interacting task constraints, state, precedence, or workflow rules,
  not from wording tricks.
- A scenario should admit multiple meaningful failure modes where appropriate instead of hinging on
  one artificial trap.
- ACMM dimensions arise naturally from the task. Dimension symmetry is not a design requirement.

The final scenarios should cluster around moderate-high difficulty. Task type should vary more than
overall difficulty so that family effects are not confounded with a deliberately easy/hard split.

## Evaluation direction

The current design expects a small set of reusable evaluator families backed by scenario-specific
structured data rather than sixteen unrelated evaluator programs. The working families are:

| Evaluator family | Primary scenarios | Purpose |
| --- | --- | --- |
| Constraint validator | P1, P2 | Validate candidate schedules, sequences, allocations, and placements |
| State interpreter | S1 | Replay ordered transitions to obtain the unique reference state |
| Rule engine | D1 | Apply precedence-controlled policy rules |
| Precedence resolver | R1 | Resolve conflicting values from explicit authority rules |
| Repair validator | V1 | Detect invalidity, validate repaired artifacts, and measure edit cost |
| Workflow/dependency validator | W1, G1 | Validate traces, dependencies, gates, and legitimate completion |

Structured scenario assets should be package-owned and should drive prompt/evaluator consistency.
The scientific task data should not be stuffed into generic environment configuration merely because
that mapping accepts arbitrary keys.

Package tests should eventually check, where applicable, that a scenario is solvable, declared rules
are nonredundant, prompt text faithfully represents the structured specification, reference
solutions pass, known invalid solutions fail for the expected reasons, and evaluator behavior is
stable under harmless output formatting differences.

## Current design checkpoint

All eight pairs are provisionally frozen at the design level:

- **P1 Constraint Planning** — concrete rules and exhaustive feasibility calibration complete.
- **P2 Allocation** — concrete rules and exhaustive feasibility calibration complete.
- **S1 Ordered State Transformation** — concrete initial states, deterministic event traces, and
  final states complete.
- **D1 Policy-Governed Decisions** — concrete ordered policies, frozen case sets, complete rule-path
  coverage, and precedence calibration complete.
- **R1 Information Reconciliation** — concrete conflicting records/configuration layers, unique
  resolved outputs, and source/layer authority calibration complete.
- **V1 Audit and Correction** — concrete invalid artifacts, seeded defect sets, and minimum-repair
  calibration complete.
- **W1 Conditional Workflow** — concrete workflows, frozen case sets, complete step coverage, and
  terminal/branch calibration complete.
- **G1 Goal Decomposition** — concrete staged and conditional plans, exhaustive decomposition
  calibration, and completion-semantics rules complete.

The scenario-design phase is therefore complete. See
[`design/design_checkpoint.md`](design/design_checkpoint.md) for the cross-family checkpoint and
implementation transition.
