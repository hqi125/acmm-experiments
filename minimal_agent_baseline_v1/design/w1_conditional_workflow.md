# W1 — Conditional Workflow Execution

> **Design status:** provisionally frozen and implemented. Frozen workflow traces and terminal outcomes
> are now evaluated deterministically from structured assets; live smoke qualification remains pending.

W1 changes the baseline from deciding *what* outcome is correct to executing *how* a task must
proceed. Each variant provides a closed-world finite workflow and several cases. The agent must
return the exact ordered step trace and final disposition for every case.

A correct final disposition reached through the wrong path is therefore not fully correct. This is
intentional: W1 makes Procedure directly observable without asking for hidden chain-of-thought.
Likewise, a terminal step really terminates the case. Continuing into downstream steps after a
reject, escalation, pending state, or closure is a measurable workflow failure.

All labels and semantics are fictional and completely defined by the prompt. No real operational,
security, incident-response, or organizational knowledge is required.

## W1-A — Request Workflow

Eight requests move through an ordered request-processing workflow. Earlier gates can terminate a
case before later attributes are considered. Several frozen cases intentionally contain downstream
attributes that would trigger a different outcome if the agent illegally skipped an earlier stop.

### Request fields

Each request contains:

- `well_formed`: boolean
- `identity_verified`: boolean
- `eligible`: boolean
- `restricted`: boolean
- `urgent`: boolean
- `evidence_complete`: boolean
- `risk`: `low` or `high`

### Frozen workflow

The workflow is executed in the exact order below.

| Step | Action / condition | Next behavior |
| --- | --- | --- |
| A1 | `VALIDATE` — inspect `well_formed` | If false, execute A2 and stop; otherwise continue to A3 |
| A2 | `REJECT_INVALID` | Final disposition `REJECT_INVALID`; stop |
| A3 | `VERIFY_IDENTITY` — inspect `identity_verified` | If false, execute A4 and stop; otherwise continue to A5 |
| A4 | `REJECT_IDENTITY` | Final disposition `REJECT_IDENTITY`; stop |
| A5 | `CHECK_ELIGIBILITY` — inspect `eligible` | If false, execute A6 and stop; otherwise continue to A7 |
| A6 | `DENY_INELIGIBLE` | Final disposition `DENY_INELIGIBLE`; stop |
| A7 | `CHECK_RESTRICTION` — inspect `restricted` and `urgent` | Restricted+urgent -> A8; restricted+not urgent -> A9; otherwise continue to A10 |
| A8 | `ESCALATE_RESTRICTED` | Final disposition `ESCALATE_RESTRICTED`; stop |
| A9 | `DENY_RESTRICTED` | Final disposition `DENY_RESTRICTED`; stop |
| A10 | `CHECK_EVIDENCE` — inspect `evidence_complete` | If false, execute A11 and stop; otherwise continue to A12 |
| A11 | `REQUEST_EVIDENCE` | Final disposition `PENDING_EVIDENCE`; stop |
| A12 | `CHECK_RISK` — inspect `risk` | If high, execute A13 and stop; otherwise execute A14 |
| A13 | `ESCALATE_MANUAL_REVIEW` | Final disposition `ESCALATE_MANUAL_REVIEW`; stop |
| A14 | `APPROVE` | Final disposition `APPROVE`; stop |

The workflow does not permit jumping directly to a disposition. Every nonterminal check reached by a
case belongs in its returned trace.

### Frozen cases

| Case | Well formed | Identity | Eligible | Restricted | Urgent | Evidence | Risk | Expected disposition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Q1 | no | yes | yes | no | no | complete | low | `REJECT_INVALID` |
| Q2 | yes | no | yes | yes | yes | complete | high | `REJECT_IDENTITY` |
| Q3 | yes | yes | no | no | no | missing | high | `DENY_INELIGIBLE` |
| Q4 | yes | yes | yes | yes | yes | missing | high | `ESCALATE_RESTRICTED` |
| Q5 | yes | yes | yes | yes | no | complete | high | `DENY_RESTRICTED` |
| Q6 | yes | yes | yes | no | no | missing | high | `PENDING_EVIDENCE` |
| Q7 | yes | yes | yes | no | no | complete | high | `ESCALATE_MANUAL_REVIEW` |
| Q8 | yes | yes | yes | no | no | complete | low | `APPROVE` |

The deliberately irrelevant downstream flags make early termination observable. For example, Q2 is
restricted, urgent, and high-risk, but identity rejection occurs first. Q4 has missing evidence and
high risk, but restricted+urgent escalation terminates the request before those later checks.

### Reference traces

| Case | Expected ordered trace |
| --- | --- |
| Q1 | `A1 -> A2` |
| Q2 | `A1 -> A3 -> A4` |
| Q3 | `A1 -> A3 -> A5 -> A6` |
| Q4 | `A1 -> A3 -> A5 -> A7 -> A8` |
| Q5 | `A1 -> A3 -> A5 -> A7 -> A9` |
| Q6 | `A1 -> A3 -> A5 -> A7 -> A10 -> A11` |
| Q7 | `A1 -> A3 -> A5 -> A7 -> A10 -> A12 -> A13` |
| Q8 | `A1 -> A3 -> A5 -> A7 -> A10 -> A12 -> A14` |

Every workflow step A1-A14 is exercised by at least one frozen case. Each case also reaches a
different terminal disposition, giving the frozen prompt complete terminal-path coverage.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `all_request_outcomes` | Goal | All eight requests return the correct final disposition |
| `request_preservation` | Fidelity | Exactly Q1-Q8 are returned once, with no invented or omitted cases |
| `gate_application` | Obligation | Validation, identity, eligibility, evidence, and risk gates are applied when reached |
| `restricted_request_boundary` | Boundary | Restricted requests terminate at A8 or A9 and never proceed toward approval |
| `ordered_trace` | Procedure | Returned step IDs match the exact workflow order for each case |
| `terminal_stop` | Procedure | No steps are executed after a terminal reject, deny, escalation, pending state, or approval |

`terminal_stop` is kept separate from general trace correctness because continuing after a terminal
state is a particularly meaningful orchestration failure even if the final label happens to remain
correct.

## W1-B — Incident Workflow

Seven fictional incidents use a different workflow topology. Unlike W1-A's mostly linear gate
sequence, W1-B contains optional containment, branch rejoining, diagnostic escalation, remediation,
recovery validation, and final closure.

The workflow labels are experiment-local. Words such as "incident", "containment", and "recovery"
do not import any external incident-response doctrine.

### Incident fields

Each incident contains:

- `duplicate`: boolean
- `impact`: `none`, `medium`, or `high`
- `containment_required`: boolean
- `containment_success`: boolean
- `cause_known`: boolean
- `recovery_valid`: boolean

A field may be irrelevant because an earlier step terminates the incident. The agent must not use an
irrelevant later field to bypass an earlier workflow decision.

### Frozen workflow

| Step | Action / condition | Next behavior |
| --- | --- | --- |
| B1 | `TRIAGE` | Continue to B2 |
| B2 | `CHECK_DUPLICATE` — inspect `duplicate` | If true, execute B3 and stop; otherwise continue to B4 |
| B3 | `CLOSE_DUPLICATE` | Final disposition `CLOSED_DUPLICATE`; stop |
| B4 | `CHECK_IMPACT` — inspect `impact` | If `none`, execute B5 and stop; otherwise continue to B6 |
| B5 | `CLOSE_NO_IMPACT` | Final disposition `CLOSED_NO_IMPACT`; stop |
| B6 | `PRESERVE_EVIDENCE` | Continue to containment decision |
| B7 | `CONTAIN` — execute only when `containment_required = true` | If containment fails, execute B8 and stop; otherwise rejoin at B9 |
| B8 | `ESCALATE_CONTAINMENT` | Final disposition `ESCALATED_CONTAINMENT`; stop |
| B9 | `DIAGNOSE` — inspect `cause_known` | If false, execute B10 then B11 and stop; otherwise continue to B12 |
| B10 | `COLLECT_DIAGNOSTICS` | Continue immediately to B11 |
| B11 | `ESCALATE_SPECIALIST` | Final disposition `ESCALATED_SPECIALIST`; stop |
| B12 | `REMEDIATE` | Continue to B13 |
| B13 | `VALIDATE_RECOVERY` — inspect `recovery_valid` | If false, execute B14 and stop; otherwise execute B15 |
| B14 | `ESCALATE_RECOVERY` | Final disposition `ESCALATED_RECOVERY`; stop |
| B15 | `CLOSE_RESOLVED` | Final disposition `CLOSED_RESOLVED`; stop |

If containment is not required, the workflow proceeds directly from B6 to B9; B7 is not emitted.
Successful containment also rejoins at B9. This lets the evaluator distinguish a legitimate skipped
optional step from an omitted required step.

### Frozen cases

| Case | Duplicate | Impact | Containment required | Containment success | Cause known | Recovery valid | Expected disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| I1 | yes | high | yes | no | no | no | `CLOSED_DUPLICATE` |
| I2 | no | none | yes | no | no | no | `CLOSED_NO_IMPACT` |
| I3 | no | high | yes | no | yes | yes | `ESCALATED_CONTAINMENT` |
| I4 | no | medium | no | yes | no | yes | `ESCALATED_SPECIALIST` |
| I5 | no | high | yes | yes | yes | no | `ESCALATED_RECOVERY` |
| I6 | no | medium | no | yes | yes | yes | `CLOSED_RESOLVED` |
| I7 | no | high | yes | yes | yes | yes | `CLOSED_RESOLVED` |

I1 and I2 intentionally carry later values that would lead elsewhere if the agent ignored an early
closure. I6 and I7 both resolve successfully but reach B9 differently: I6 legitimately skips
containment, while I7 executes successful containment and then rejoins the common diagnostic path.

### Reference traces

| Case | Expected ordered trace |
| --- | --- |
| I1 | `B1 -> B2 -> B3` |
| I2 | `B1 -> B2 -> B4 -> B5` |
| I3 | `B1 -> B2 -> B4 -> B6 -> B7 -> B8` |
| I4 | `B1 -> B2 -> B4 -> B6 -> B9 -> B10 -> B11` |
| I5 | `B1 -> B2 -> B4 -> B6 -> B7 -> B9 -> B12 -> B13 -> B14` |
| I6 | `B1 -> B2 -> B4 -> B6 -> B9 -> B12 -> B13 -> B15` |
| I7 | `B1 -> B2 -> B4 -> B6 -> B7 -> B9 -> B12 -> B13 -> B15` |

Every workflow step B1-B15 is exercised at least once. Six distinct terminal dispositions are
represented; `CLOSED_RESOLVED` appears twice specifically to test the optional-containment branch and
its rejoin behavior.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `all_incident_outcomes` | Goal | All seven incidents return the correct final disposition |
| `incident_preservation` | Fidelity | Exactly I1-I7 are returned once |
| `evidence_and_containment` | Obligation | Evidence preservation and required containment steps occur when the workflow reaches them |
| `escalation_boundary` | Boundary | An escalation terminates the case; remediation or closure is not executed afterward |
| `ordered_trace` | Procedure | Step IDs exactly match the required path, including optional containment behavior |
| `branch_rejoin` | Procedure | Cases correctly skip or execute B7 and then rejoin at B9 without inventing or omitting steps |

Despite the domain label, this scenario does not automatically receive an ACMM Recovery opportunity.
The agent is following a supplied workflow; it is not itself recovering from an execution failure.
Recovery remains strongest in the V1 audit-and-repair family.

## Pair calibration summary

| Scenario | Frozen cases | Workflow steps | Terminal dispositions | Coverage property |
| --- | ---: | ---: | ---: | --- |
| W1-A | 8 | 14 | 8 | Every step and every terminal disposition exercised at least once |
| W1-B | 7 | 15 | 6 | Every step exercised; resolved path tested both with and without containment |

W1-A emphasizes ordered validation gates and strict early termination. W1-B emphasizes optional
branches, branch rejoining, escalation, and a longer shared tail. Both produce unique deterministic
traces, but their control-flow topology is meaningfully different.

The case counts are slightly above the earlier authoring target of roughly six cases because complete
step/path coverage is more valuable here than forcing a cosmetic count match. The prompt remains
moderate-high in difficulty: cases are compact, attributes are simple, and the challenge comes from
executing the workflow faithfully rather than from domain knowledge.

## Expected failure modes

Useful naturally occurring failures include:

- jumping directly to the final disposition while omitting required intermediate steps;
- continuing after an earlier terminal step because a downstream flag appears important;
- executing a downstream check before its prerequisite gate;
- treating restricted+urgent and restricted+nonurgent requests identically;
- executing containment when it is not required;
- skipping containment when it is required;
- failing to rejoin the common incident path correctly after successful containment;
- closing an incident after an escalation step;
- returning the correct final disposition with an incorrect trace;
- preserving the trace shape but returning the wrong terminal disposition.

These failures let W1 distinguish procedural control from final-answer luck.

## Implementation direction

Both scenarios should use a shared `workflow_validator` / reference-interpreter family. Structured
scenario assets should define the workflow graph, predicates, terminal dispositions, cases, and
requested output schema. Expected traces should be generated by interpreting those assets rather
than hard-coded as answer strings in runtime code.

A final response should contain one record per frozen case with:

- case ID;
- ordered step ID list;
- final disposition.

Evaluators should tolerate harmless case ordering and Markdown/code-fence wrappers, but step order is
scientifically meaningful and must not be normalized away.

Useful package tests should verify:

- every frozen case has exactly one deterministic trace;
- every declared workflow step is exercised by at least one frozen case;
- terminal steps have no outgoing execution in the reference interpreter;
- W1-A covers all eight terminal dispositions exactly once;
- W1-B exercises resolved behavior both with and without containment;
- changing irrelevant downstream attributes on early-stop cases does not change their trace;
- omitting, inserting, or reordering a required step fails the Procedure check even when the final
  disposition is correct;
- prompt text faithfully represents the structured workflow and frozen cases.
