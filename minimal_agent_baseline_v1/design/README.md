# Minimal Agent Baseline Design Notes

This directory is the living design and implementation record for `minimal_agent_baseline_v1`.
The package is now executable, but these notes preserve the scientific reasoning behind each mind
game and the decisions made while translating the frozen drafts into structured assets and runtime
validators. Provisional wording can still be tightened during smoke qualification.

## Documents

- [`scenario_matrix.md`](scenario_matrix.md) — the complete 16-scenario architecture and common
  difficulty/evaluation principles.
- [`p1_constraint_planning.md`](p1_constraint_planning.md) — concrete P1-A Workshop Schedule and
  P1-B Batch Sequence designs, including exhaustive solution-space calibration.
- [`p2_allocation.md`](p2_allocation.md) — concrete P2-A Project Staffing and P2-B Storage Zones
  designs, including capacity/eligibility calibration.
- [`s1_ordered_state_transformation.md`](s1_ordered_state_transformation.md) — concrete S1-A
  Inventory Ledger and S1-B Case Lifecycle designs, including reference event traces and final states.
- [`d1_policy_governed_decisions.md`](d1_policy_governed_decisions.md) — concrete D1-A Access
  Requests and D1-B Service Routing policies, including frozen rule-path and precedence calibration.
- [`r1_information_reconciliation.md`](r1_information_reconciliation.md) — concrete R1-A Canonical
  Records and R1-B Effective Configuration designs, including source/layer authority calibration.
- [`v1_audit_and_correction.md`](v1_audit_and_correction.md) — concrete V1-A Schedule Audit
  and V1-B Manifest Audit designs, including seeded defects and minimum-repair calibration.
- [`w1_conditional_workflow.md`](w1_conditional_workflow.md) — concrete W1-A Request Workflow
  and W1-B Incident Workflow designs, including full step-path and terminal calibration.
- [`g1_goal_decomposition.md`](g1_goal_decomposition.md) — concrete G1-A Project Execution and
  G1-B Conditional Release Sequence designs, including exhaustive staged-plan calibration.
- [`design_checkpoint.md`](design_checkpoint.md) — end-of-design checkpoint summarizing the frozen
  8-family / 16-scenario architecture before package implementation began.
- [`implementation_checkpoint.md`](implementation_checkpoint.md) — first executable checkpoint,
  including Contract/runtime structure, no-tool semantics, response format, and validation status.
- [`structured_output_hardening.md`](structured_output_hardening.md) — post-acquisition JSON
  presentation-noise audit, generic Core recovery policy, and final Contract-directed interpretation path.

## Design-to-implementation convention

Each pair should move through the same sequence:

1. Define two scenarios that share a construct but not a surface template.
2. Author concrete inputs, rules, and requested outputs.
3. Establish a deterministic reference/evaluator model.
4. Validate feasibility and, where meaningful, measure the valid solution space.
5. Remove accidental redundant constraints unless redundancy is scientifically intentional.
6. Define natural ACMM opportunities without forcing symmetric dimension coverage.
7. Record expected failure modes and likely confounds.
8. Freeze the design before populating package code.

For constructive tasks, the evaluator must accept any valid solution rather than compare against one
canonical answer. For unique-result tasks, the reference interpreter should derive the result from
frozen scenario data rather than hard-code an answer string.

- [`output_semantics_v0_2.md`](output_semantics_v0_2.md) records the Contract v0.2 migration that moves R1-B scalar representation tolerance into an explicit, auditable declaration.
