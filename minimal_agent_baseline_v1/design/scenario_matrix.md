# Scenario Matrix

The Minimal Agent Baseline targets 16 scenarios: eight conceptual task families with two independently
authored variants each. A/B variants should be comparable in overall difficulty but should differ in
representation and solution path strongly enough that family-level consistency means more than
surviving a wording change.

## Matrix

| ID | Family | Scenario concept | Primary challenge | Objective evaluation |
| --- | --- | --- | --- | --- |
| P1-A | Constraint planning | Workshop Schedule | Maintain availability, room, collision, precedence, and separation constraints | Accept any complete valid time/room assignment |
| P1-B | Constraint planning | Batch Sequence | Maintain precedence, adjacency, separation, partition, and position rules | Accept any valid permutation |
| P2-A | Allocation | Project Staffing | Maintain cardinality, eligibility, coverage, pairing, and separation globally | Accept any valid project allocation |
| P2-B | Allocation | Storage Zones | Maintain weighted capacities, allowed zones, co-location, and separation | Accept any valid placement |
| S1-A | Ordered state transformation | Inventory Ledger | Apply chronological conditional updates without losing intermediate state | Replay operations and compare exact final state |
| S1-B | Ordered state transformation | Case Lifecycle | Apply legal transitions and conditional side effects in order | Replay state machine and compare exact records |
| D1-A | Policy-governed decisions | Access Requests | Apply allow/deny/escalate rules with explicit precedence and exceptions | Rule engine derives exact decision per case |
| D1-B | Policy-governed decisions | Service Routing | Apply queue, priority, eligibility, exception, and fallback rules | Rule engine derives exact route/disposition |
| R1-A | Information reconciliation | Canonical Records | Select authoritative values field-by-field across conflicting sources | Precedence resolver derives canonical records |
| R1-B | Information reconciliation | Effective Configuration | Merge base/environment/service values with locks and fallbacks | Deterministic configuration merge |
| V1-A | Audit and correction | Schedule Repair | Detect violations and produce a minimum-change valid repair | Defect checks + constraint validation + edit-cost optimum |
| V1-B | Audit and correction | Manifest Repair | Detect missing/inconsistent/dependency-invalid fields and repair them | Known-defect checks + final artifact validation |
| W1-A | Conditional workflow | Request Workflow | Execute validation/review/escalation/termination branches in order | Reference workflow trace and final disposition |
| W1-B | Conditional workflow | Incident Workflow | Execute a different branching workflow from supplied evidence flags | Finite-state workflow interpreter |
| G1-A | Goal decomposition | Project Execution | Stage tasks while respecting prerequisites, gates, concurrency, and acceptance | DAG/stage validation |
| G1-B | Goal decomposition | Conditional Release Sequence | Build a common staged prefix and mutually exclusive PASS/FAIL tails with distinct terminal semantics | Dependency/branch/completion validation |

## Pair-level difficulty targets

These values are authoring targets, not scoring quotas.

| Pair | Entities / state | Rules / events | Conditional depth | Answer space |
| --- | ---: | ---: | --- | --- |
| P1 | 7-9 entities | 8-10 constraints | Low-medium | Multiple valid solutions |
| P2 | 9-10 entities | 8-10 constraints | Low-medium | Multiple valid solutions |
| S1 | 5-7 records | 9-10 events plus transition rules | Medium | Unique final state |
| D1 | 8-10 cases | About 9 policy rules | Medium | Unique decisions |
| R1 | 6-8 entities/keys | About 8 precedence rules | Medium | Unique resolved state |
| V1 | One invalid artifact | About 9 governing rules, 4-6 seeded defects | Medium | One or several optimal repairs |
| W1 | 7-8 cases | 14-15 workflow steps | Medium-high | Unique traces |
| G1 | 10-12 tasks | 4-7 direct prerequisites plus set/branch gates | Medium-high | 18 / 21 admissible decompositions |

## Common output philosophy

The task output should be structured enough for deterministic evaluation but should not turn the
study into a formatting benchmark. A small outer result structure is appropriate when useful; the
inner schema may vary by task family. Evaluators should tolerate harmless wrappers such as Markdown
code fences and harmless ordering differences.

A compact verification artifact may be requested when it is a natural observable task output (for
example executed workflow step IDs or claimed satisfied constraint IDs). It must not request hidden
reasoning. Correctness of the result and correctness/completeness of the verification artifact may
be judged separately where scientifically useful.

## ACMM dimension philosophy

Dimension coverage is not quota-engineered.

- **Goal** should arise in essentially every scenario.
- **Obligation** naturally appears in rule- and workflow-heavy tasks.
- **Boundary** is strongest where the prompt defines an explicit permitted action/assignment space.
- **Procedure** is strongest in state transformations, workflows, and staged dependency tasks where
  procedure is observable from required outputs.
- **Fidelity** is strongest in preservation, reconciliation, transformation, and audit tasks.
- **Recovery** is expected to be relatively sparse in this tool-free experiment and should arise
  naturally in audit/repair tasks rather than through artificial failure injection.

This asymmetry is desirable. ACMM measures the task; the task is not constructed to make G/O/B/P/F/R
look numerically symmetric.
