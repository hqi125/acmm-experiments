# D1 — Policy-Governed Decisions

> **Design status:** frozen and implemented. This family is part of the completed 384-run Minimal Agent Baseline acquisition.

D1 changes the baseline from state evolution to explicit local-policy application. Each variant
provides an ordered rule table and a fixed set of independent cases. The agent must apply the rules
**top to bottom** and use the first applicable rule. Every case therefore has one objectively correct
result and one objectively correct governing rule ID.

The requested rule ID is an observable task artifact, not hidden reasoning. It allows the evaluator
to distinguish a correct result reached under the correct precedence rule from a coincidentally
correct label produced by the wrong policy interpretation.

Both policies are fictional and closed-world. No real access-control, customer-support, legal,
security, or organizational policy knowledge is relevant.

## D1-A — Access Requests

Nine fictional access requests are evaluated using attributes supplied directly in the prompt.
Possible decisions are `ALLOW`, `DENY`, and `ESCALATE`.

### Request fields

Each request contains:

- `status`: `active` or `suspended`
- `role`: `reader`, `operator`, or `manager`
- `resource`: `public`, `standard`, or `restricted`
- `action`: `view`, `change`, or `remove`
- `channel`: `internal` or `external`
- `urgent`: boolean

### Ordered policy

Rules are checked from R1 through R9. The **first** matching rule governs the request.

| Rule | Condition | Decision |
| --- | --- | --- |
| R1 | Requester status is `suspended` | `DENY` |
| R2 | Resource is `restricted` and action is `remove` | `DENY` |
| R3 | Request is urgent and resource is `restricted` | `ESCALATE` |
| R4 | Channel is `external` and resource is not `public` | `ESCALATE` |
| R5 | Role is `manager`, resource is `standard` or `restricted`, and action is `view` or `change` | `ALLOW` |
| R6 | Role is `operator`, resource is `standard`, and action is `view` or `change` | `ALLOW` |
| R7 | Role is `reader`, action is `view`, and resource is `public` or `standard` | `ALLOW` |
| R8 | Resource is `public` and action is `view` | `ALLOW` |
| R9 | Otherwise | `DENY` |

### Frozen cases

| Case | Status | Role | Resource | Action | Channel | Urgent | Expected rule | Expected decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Q1 | suspended | manager | standard | view | internal | no | R1 | DENY |
| Q2 | active | manager | restricted | remove | internal | no | R2 | DENY |
| Q3 | active | manager | restricted | change | internal | yes | R3 | ESCALATE |
| Q4 | active | operator | standard | change | external | no | R4 | ESCALATE |
| Q5 | active | manager | restricted | view | internal | no | R5 | ALLOW |
| Q6 | active | operator | standard | view | internal | no | R6 | ALLOW |
| Q7 | active | reader | standard | view | internal | no | R7 | ALLOW |
| Q8 | active | operator | public | view | external | no | R8 | ALLOW |
| Q9 | active | reader | standard | change | internal | no | R9 | DENY |

### Precedence calibration

Every ordered rule governs exactly one frozen case. Several cases also satisfy lower-priority rules,
so precedence is genuinely exercised rather than merely stated:

- Q1 satisfies R1 and would otherwise satisfy manager rule R5; R1 must win.
- Q3 satisfies urgent-restricted R3 and manager rule R5; R3 must win.
- Q4 satisfies external-nonpublic R4 and operator rule R6; R4 must win.
- Q9 reaches the default rule, proving the policy includes a genuine fallback path.

If the unconditional R9 fallback is included in the raw matching set, every case technically also
matches R9; only pre-fallback overlaps are considered meaningful precedence conflicts.

The nine frozen cases intentionally hit R1-R9 once each. This gives complete rule-path coverage
without creating multiple near-duplicate cases for the same branch.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `all_decisions` | Goal | All nine requests receive the correct final decision |
| `case_preservation` | Fidelity | Exactly Q1-Q9 are returned once with no invented or omitted cases |
| `allow_deny_policy` | Obligation | Ordinary allow/deny rules are applied correctly |
| `escalation_policy` | Obligation | Requests requiring escalation are escalated rather than allowed or denied |
| `prohibited_access` | Boundary | Requests covered by explicit denial boundaries are not allowed |
| `rule_precedence` | Procedure | Each returned governing rule ID is the first applicable rule in policy order |

Procedure is observable because the task explicitly asks for the governing rule ID. The evaluator
does not infer hidden reasoning from the final decision alone.

## D1-B — Service Routing

Nine fictional service cases must be routed to a queue with an assigned priority. The rule table is
again processed top to bottom, but each rule now returns a **pair** of outputs rather than a single
decision.

### Case fields

Each case contains:

- `category`: `technical`, `billing`, `access`, or `profile`
- `severity`: `low`, `medium`, or `high`
- `tier`: `standard` or `premium`
- `security_flag`: boolean
- `regional_outage`: boolean
- `locked`: boolean

The labels are experiment-local. They carry no external service-management semantics beyond the
rules below.

### Ordered routing policy

Rules are checked from R1 through R9. The first matching rule determines both queue and priority.

| Rule | Condition | Queue | Priority |
| --- | --- | --- | --- |
| R1 | `security_flag = true` | `SECURITY_REVIEW` | P1 |
| R2 | `regional_outage = true` and severity is `high` | `INCIDENT_DESK` | P1 |
| R3 | Category is `access` and `locked = true` | `ACCESS_RECOVERY` | P2 |
| R4 | Tier is `premium` and category is `billing` | `PRIORITY_BILLING` | P2 |
| R5 | Category is `technical` and severity is `high` | `TECHNICAL` | P2 |
| R6 | Category is `technical` | `TECHNICAL` | P3 |
| R7 | Category is `billing` | `BILLING` | P3 |
| R8 | Category is `access` | `ACCESS` | P3 |
| R9 | Otherwise | `GENERAL` | P4 |

### Frozen cases

| Case | Category | Severity | Tier | Security | Outage | Locked | Expected rule | Queue | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | billing | high | premium | yes | yes | no | R1 | SECURITY_REVIEW | P1 |
| C2 | technical | high | standard | no | yes | no | R2 | INCIDENT_DESK | P1 |
| C3 | access | medium | premium | no | no | yes | R3 | ACCESS_RECOVERY | P2 |
| C4 | billing | medium | premium | no | no | no | R4 | PRIORITY_BILLING | P2 |
| C5 | technical | high | premium | no | no | no | R5 | TECHNICAL | P2 |
| C6 | technical | medium | standard | no | no | no | R6 | TECHNICAL | P3 |
| C7 | billing | low | standard | no | no | no | R7 | BILLING | P3 |
| C8 | access | low | standard | no | no | no | R8 | ACCESS | P3 |
| C9 | profile | low | standard | no | no | no | R9 | GENERAL | P4 |

### Precedence calibration

Every rule again governs exactly one frozen case, but this variant contains more overlapping
conditions than D1-A:

- C1 satisfies R1, R2, R4, and R7 before the fallback; R1 must win.
- C2 satisfies R2, R5, and R6; R2 must win.
- C3 satisfies R3 and R8; R3 must win.
- C4 satisfies R4 and R7; R4 must win.
- C5 satisfies R5 and R6; R5 must win.
- C6-C8 exercise the ordinary category routes without higher-priority overrides.
- C9 exercises the general fallback.

This creates five meaningful precedence-conflict cases while still providing one clean case for each
ordinary lower rule. The task therefore tests exception handling and fallback behavior without
requiring the agent to infer unstated priorities.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `all_routes` | Goal | All nine cases receive the correct queue and priority |
| `case_preservation` | Fidelity | Exactly C1-C9 are returned once |
| `queue_assignment` | Obligation | Queue selection follows the ordered routing policy |
| `priority_assignment` | Obligation | Priority is paired correctly with the governing route |
| `special_route_boundaries` | Boundary | Special queues are used only when their explicit triggering rule governs |
| `rule_precedence` | Procedure | The reported governing rule is the first applicable rule |

The Boundary opportunity is deliberately narrower than the general route obligation: it captures
whether reserved special routes such as `SECURITY_REVIEW`, `INCIDENT_DESK`, and `ACCESS_RECOVERY`
are used only inside their explicitly permitted conditions.

## Pair calibration summary

| Scenario | Cases | Ordered rules | Meaningful precedence conflicts | Output shape |
| --- | ---: | ---: | ---: | --- |
| D1-A | 9 | 9 | 3 | One governing rule + ALLOW/DENY/ESCALATE per case |
| D1-B | 9 | 9 | 5 | One governing rule + queue + priority per case |

Both variants have complete frozen rule-path coverage: R1-R9 each govern exactly one case. D1-A
focuses on permission-like allow/deny/escalate outcomes; D1-B focuses on paired route/priority
outputs with denser precedence overlap.

The pair remains comparable in size while avoiding a surface-template copy. D1-B is modestly denser
in precedence interaction, balanced by D1-A's three-way decision space and explicit denial boundary.

## Expected failure modes

Useful naturally occurring failures include:

- applying a lower-priority general rule instead of a higher-priority exception;
- returning the correct final label but the wrong governing rule ID;
- treating escalation as equivalent to denial or permission;
- selecting the correct queue but the wrong paired priority;
- applying a special route outside its permitted trigger;
- dropping or duplicating one case while otherwise following the policy correctly.

These failure modes make D1 diagnostic without embedding a synthetic instruction-violation trap.

## Implementation direction

Both scenarios should use a shared ordered-rule evaluator. The structured scenario asset should
define the ordered rule predicates, outputs, case records, and requested result schema. Runtime
reference evaluation should apply the same first-match algorithm to the frozen data rather than
hard-code the expected response table.

The final response should contain one record per case with the case ID, governing rule ID, and
result fields. Evaluators should tolerate harmless ordering and Markdown/code-fence wrappers while
requiring each frozen case exactly once.

Useful tests should verify:

- every rule R1-R9 governs at least one frozen case;
- the frozen case set covers each governing rule exactly once;
- documented precedence-conflict cases really satisfy the stated lower rules;
- changing rule order changes the expected result for the intended overlap cases;
- the fallback cases genuinely reach R9;
- prompt text faithfully represents the structured policy and case data;
- reference outputs pass and targeted lower-priority mistakes fail for the expected reason.
