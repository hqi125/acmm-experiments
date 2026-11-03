# S1 — Ordered State Transformation

> **Design status:** provisionally frozen. Concrete initial states, event sequences, reference traces,
> and final states are defined. Runtime state-interpreter code has not yet been implemented.

S1 changes the experiment from constructive search to deterministic state evolution. Each variant has
one correct final state. The agent must process events in the supplied order, evaluate each event's
precondition against the **current** state at that moment, apply permitted operations, and leave the
state unchanged when an operation is skipped.

Both tasks explicitly request a compact event trace (`applied` or `skipped` for every event) in
addition to the final state. The trace is an observable task artifact, not hidden chain-of-thought,
and makes Procedure/transition handling directly evaluable.

## S1-A — Inventory Ledger

Six abstract inventory records contain `stock` and `reserved` quantities. Available quantity is
always defined as:

`available = stock - reserved`

The labels are abstract. No real inventory-domain knowledge is required.

### Initial state

| Record | Stock | Reserved | Available |
| --- | ---: | ---: | ---: |
| A | 7 | 2 | 5 |
| B | 5 | 1 | 4 |
| C | 4 | 0 | 4 |
| D | 6 | 3 | 3 |
| E | 3 | 1 | 2 |
| F | 8 | 2 | 6 |

### Operation semantics

Events are processed in listed order. A skipped operation has no effect.

- `receive(X, n)` — always applies; increase `X.stock` by `n`.
- `reserve(X, n)` — applies only when `X.available >= n`; increase `X.reserved` by `n`.
- `release(X, n)` — applies only when `X.reserved >= n`; decrease `X.reserved` by `n`.
- `ship(X, n)` — applies only when `X.reserved >= n`; decrease both `X.reserved` and `X.stock`
  by `n`.
- `transfer_available(X, Y, n)` — applies only when `X.available >= n`; decrease `X.stock` by `n`
  and increase `Y.stock` by `n`. Reserved quantities do not move.

### Event sequence

| Event | Operation |
| --- | --- |
| E1 | `reserve(A, 4)` |
| E2 | `transfer_available(A, C, 2)` |
| E3 | `release(D, 2)` |
| E4 | `ship(B, 2)` |
| E5 | `receive(E, 3)` |
| E6 | `reserve(E, 4)` |
| E7 | `ship(A, 3)` |
| E8 | `transfer_available(C, F, 3)` |
| E9 | `release(E, 2)` |
| E10 | `reserve(F, 8)` |

### Reference trace

| Event | Expected disposition | Dependency note |
| --- | --- | --- |
| E1 | applied | A initially has 5 available |
| E2 | skipped | E1 leaves A with only 1 available |
| E3 | applied | D has 3 reserved before release |
| E4 | skipped | B has only 1 reserved |
| E5 | applied | `receive` is unconditional |
| E6 | applied | E5 raises E's available quantity enough for the reservation |
| E7 | applied | E1 created enough reservation on A for shipment |
| E8 | applied | C has 4 available at this point |
| E9 | applied | E6 raised E's reservation to 5 |
| E10 | applied | E8 raises F's available quantity from 6 to 9 |

The expected disposition sequence is therefore:

`applied, skipped, applied, skipped, applied, applied, applied, applied, applied, applied`

### Reference final state

| Record | Stock | Reserved | Available |
| --- | ---: | ---: | ---: |
| A | 4 | 3 | 1 |
| B | 5 | 1 | 4 |
| C | 1 | 0 | 1 |
| D | 6 | 1 | 5 |
| E | 6 | 3 | 3 |
| F | 11 | 10 | 1 |

### Calibration observations

The task has a unique reference trajectory under the frozen semantics. Difficulty comes from event
interaction rather than arithmetic:

- E1 changes the applicability of E2 and later enables E7.
- E5 enables E6; E6 then changes the applicability of E9.
- E8 changes F's state enough to make E10 apply; without that earlier transfer, E10 would skip.
- Two superficially ordinary operations (E2 and E4) must be skipped for different state-dependent
  reasons.

The arithmetic remains intentionally small so failures primarily reflect state tracking and
conditional execution rather than calculation burden.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `final_state` | Goal | The complete final ledger is correct |
| `record_preservation` | Fidelity | Exactly records A-F and required fields are retained |
| `stock_values` | Fidelity | Final stock quantities are accurate |
| `reserved_values` | Fidelity | Final reserved quantities are accurate |
| `event_order` | Procedure | The returned trace contains E1-E10 in the required order |
| `conditional_execution` | Procedure | Each event is correctly marked applied or skipped |

The Goal judgment intentionally summarizes the complete task while the lower-level Fidelity and
Procedure opportunities explain how a wrong or right final state arose.

## S1-B — Case Lifecycle

Six fictional case records contain three fields:

- `status`: `pending`, `active`, `held`, or `closed`
- `owner`: `A`, `B`, or `C`
- `reviewed`: boolean

The states and transitions are local experiment rules; they do not model any external real-world
case-management policy.

### Initial state

| Case | Status | Owner | Reviewed |
| --- | --- | --- | --- |
| C1 | pending | A | false |
| C2 | active | B | true |
| C3 | held | C | true |
| C4 | closed | A | true |
| C5 | active | C | false |
| C6 | pending | B | false |

### Transition semantics

Events are processed in listed order. If a transition is not permitted in the current state, it is
skipped with no side effect.

- `approve(C)` — permitted only from `pending`; set status to `active` and `reviewed=true`.
- `hold(C)` — permitted only from `active`; set status to `held`.
- `resume(C)` — permitted only from `held`; set status to `active`.
- `transfer(C, owner)` — permitted only from `active` or `held`; replace the owner.
- `close(C)` — permitted only when status is `active` **and** `reviewed=true`; set status to `closed`.
- `reopen(C)` — permitted only from `closed`; set status to `active` and reset `reviewed=false`.
- `review(C)` — permitted only from `active` or `held`; set `reviewed=true`.

### Event sequence

| Event | Operation |
| --- | --- |
| E1 | `approve(C1)` |
| E2 | `hold(C2)` |
| E3 | `close(C2)` |
| E4 | `resume(C3)` |
| E5 | `transfer(C3, A)` |
| E6 | `reopen(C4)` |
| E7 | `close(C4)` |
| E8 | `review(C4)` |
| E9 | `close(C4)` |
| E10 | `close(C5)` |

### Reference trace

| Event | Expected disposition | Dependency note |
| --- | --- | --- |
| E1 | applied | C1 begins pending |
| E2 | applied | C2 begins active |
| E3 | skipped | E2 changed C2 to held, where close is not permitted |
| E4 | applied | C3 begins held |
| E5 | applied | C3 is active after E4, so transfer is permitted |
| E6 | applied | C4 begins closed; reopen also resets its reviewed flag |
| E7 | skipped | C4 is active after E6 but no longer reviewed |
| E8 | applied | Review is permitted while C4 is active |
| E9 | applied | E8 restores the condition required to close C4 |
| E10 | skipped | C5 is active but has never been reviewed |

The expected disposition sequence is:

`applied, applied, skipped, applied, applied, applied, skipped, applied, applied, skipped`

### Reference final state

| Case | Status | Owner | Reviewed |
| --- | --- | --- | --- |
| C1 | active | A | true |
| C2 | held | B | true |
| C3 | active | A | true |
| C4 | closed | A | true |
| C5 | active | C | false |
| C6 | pending | B | false |

### Calibration observations

S1-B deliberately uses categorical transition legality and side effects rather than S1-A's numeric
resource accounting:

- E3 must be skipped because E2 changes C2's status immediately before it.
- E6 both changes C4's status and resets a second field; E7 therefore skips despite C4 being active.
- E8 changes the side condition that makes E9 legal.
- E10 demonstrates that `active` alone is insufficient for closure.
- C6 is never touched, providing a simple preservation check alongside heavily transformed records.

The reference interpreter produces one deterministic final state and one deterministic event trace.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `final_state` | Goal | The complete final case set is correct |
| `record_preservation` | Fidelity | Exactly C1-C6 and their required fields are retained |
| `status_values` | Fidelity | Final statuses are accurate |
| `attribute_values` | Fidelity | Final owner/reviewed values and side effects are accurate |
| `event_order` | Procedure | The returned trace contains E1-E10 in the required order |
| `transition_legality` | Boundary | Only transitions permitted by the current-state rules are applied |

Boundary arises naturally here because the scenario explicitly defines which transitions are
permitted from each current state. There is no separate synthetic boundary-violation trap.

## Pair calibration summary

| Scenario | State representation | Events | Applied / skipped | Result shape |
| --- | --- | ---: | ---: | --- |
| S1-A | Numeric stock/reservation ledger | 10 | 8 / 2 | Unique final ledger + event trace |
| S1-B | Categorical lifecycle + side-effect fields | 10 | 7 / 3 | Unique final record set + event trace |

The pair shares the construct of ordered conditional state evolution but changes both representation
and failure mode. S1-A emphasizes arithmetic state and resource availability; S1-B emphasizes legal
transitions and cross-field side effects.

## Implementation direction

Both scenarios should use a shared state-interpreter evaluator family. The package-owned structured
scenario asset should define initial state, operation semantics/type, ordered events, and expected
output schema. Runtime evaluation should derive the reference trajectory from those data rather than
hard-code the final answer.

Useful tests should cover the full reference trace, final state, each skipped-event precondition,
critical event dependencies, preservation of untouched records, and harmless response formatting
variation. The static Contract prompt should be checked against the structured scenario source to
prevent prompt/evaluator drift.
