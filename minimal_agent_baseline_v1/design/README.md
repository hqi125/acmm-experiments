# Minimal Agent Baseline Design Notes

This directory is the living design record for `minimal_agent_baseline_v1`. It exists before the
package is executable so experiment decisions can be reviewed and tracked in Git as they are made.
The notes are intentionally allowed to contain provisional wording; implementation-specific language
will be tightened when the Contract, structured scenario assets, evaluators, and tests are added.

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
  8-family / 16-scenario architecture before package implementation begins.

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
