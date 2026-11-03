# Minimal Agent Baseline — End-of-Design Checkpoint

This checkpoint closes the conceptual scenario-design phase for `minimal_agent_baseline_v1`.
All eight task families now have two concrete independently authored variants. The experiment remains
**design-only** at this checkpoint: no Contract, runtime evaluator implementation, or executable
package manifest has been populated yet.

## Frozen-draft scale

The planned acquisition remains:

**3 agents x 16 scenarios x 8 repetitions = 384 executions**

The experiment-level [`README.md`](../README.md) contains the full scale tradeoff table and statistical
rationale. The scale is intentionally not reduced merely because ACMM yields many requirement-level
judgments inside each run; those observations are nested diagnostic evidence, not independent runs.

## Family summary

| Family | Variant A | Variant B | Primary construct | Calibration anchor |
| --- | --- | --- | --- | --- |
| P1 Constraint planning | Workshop Schedule | Batch Sequence | Construct a valid arrangement under interacting constraints | 28 / 24 valid solutions |
| P2 Allocation | Project Staffing | Storage Zones | Maintain globally consistent allocation, eligibility, and capacity | 38 / 41 valid solutions |
| S1 Ordered state transformation | Inventory Ledger | Case Lifecycle | Preserve evolving state through ordered conditional operations | 10 events each; unique final state and trace |
| D1 Policy-governed decisions | Access Requests | Service Routing | Apply ordered local policy with precedence and exceptions | 9 cases + 9 rules each; every rule governs a frozen case |
| R1 Information reconciliation | Canonical Records | Effective Configuration | Resolve conflicting information under explicit authority semantics | Unique canonical outputs with governing source/layer evidence |
| V1 Audit and correction | Schedule Audit | Manifest Audit | Diagnose an invalid artifact and produce a minimum repair | 3-move optimum / 5-field optimum |
| W1 Conditional workflow | Request Workflow | Incident Workflow | Execute exact branching paths with early termination and rejoin behavior | Complete frozen workflow-step coverage |
| G1 Goal decomposition | Project Execution | Conditional Release Sequence | Build staged/conditional plans while preserving gates and completion semantics | 18 / 21 admissible decompositions |

The calibration anchors are deliberately family-appropriate. A valid-solution count is meaningful for
constructive tasks, while state machines, policy tables, reconciliation tasks, repair tasks, and
workflow tasks are calibrated through different structural properties. The study does not force one
artificial difficulty metric across all sixteen scenarios.

## Cross-family design properties

The full scenario set now covers several distinct forms of agent behavior without requiring an
experiment-provided tool:

- constructive constraint satisfaction;
- resource allocation and global consistency;
- ordered state maintenance;
- rule precedence and exception handling;
- source authority and reconciliation;
- defect detection and repair;
- branching workflow control;
- staged and conditional goal decomposition.

All scenarios remain closed-world. No task depends on current events, external factual knowledge,
web access, file access, or hidden state. Headline outcomes can therefore be evaluated
programmatically without an LLM judge.

## ACMM measurement philosophy

The scenario set was not engineered to give equal G/O/B/P/F/R counts. Dimensions arise where the
observable task actually supports them.

- **Goal** is broadly present through complete task success.
- **Obligation** is common wherever explicit constraints, rules, or gates must be honored.
- **Boundary** is strongest where eligibility, policy, branch exclusivity, or protected regions define
  actions that must not occur.
- **Procedure** is strongest where traces, governing rules/sources, ordered transitions, or completion
  semantics are observable in the requested output.
- **Fidelity** is broadly measured through preservation of supplied entities, records, state, and
  task facts.
- **Recovery** is intentionally concentrated in V1, where the agent must detect and repair a supplied
  invalid state. Recovery-like domain vocabulary elsewhere does not automatically create a Recovery
  opportunity.

This asymmetry is intentional and should be preserved during implementation.

## Implementation transition

The next phase should convert the design into executable package artifacts in a controlled order:

1. define the package/Contract skeleton and all 16 stable scenario IDs;
2. introduce structured package-owned scenario assets rather than embedding evaluator state in
   environment configuration;
3. implement the reusable evaluator families established during design;
4. render or validate Contract prompts against those structured assets so prompt and evaluator rules
   cannot silently diverge;
5. populate natural ACMM opportunities and checks;
6. add exhaustive/reference tests for every calibration claim recorded in the pair notes;
7. add package validation/integration tests against the current ACMM Core API;
8. perform small engineering smoke runs before the planned 384-run acquisition.

The smoke runs are engineering validation only. They should not quietly replace or reduce the
scientific acquisition target unless the frozen design itself is formally revised with justification.

## Core prerequisite carried into implementation

The earlier repository audit found that the Experiment Package model supports a no-apparatus study,
but the current execution adapters still contain tool-bearing assumptions: Open WebUI and Agent Zero
expect experiment tool configuration, while Hermes currently requests the `acmm` toolset. Before the
baseline is executed, Core should gain a clean no-tool adapter path rather than giving this package a
dummy tool or fake apparatus.

That infrastructure fix is intentionally outside the scientific scenario design and should remain a
generic Core capability.
