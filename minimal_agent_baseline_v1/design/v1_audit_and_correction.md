# V1 — Audit and Correction

> **Design status:** frozen and implemented. This family is part of the completed 384-run Minimal Agent Baseline acquisition.

V1 is the first family in the Minimal Agent Baseline where the supplied artifact is intentionally
invalid. The agent must do two things: diagnose what is wrong and produce a corrected artifact
without weakening the task merely to make the violations disappear.

The pair makes Recovery directly observable in a tool-free setting. V1-A requires a minimum-change
repair to a constrained schedule. V1-B requires a minimum-field repair to a fictional release
manifest while preserving immutable intent fields.

Neither task asks for hidden reasoning. The observable artifacts are the reported violated rule IDs
and the repaired result.

## V1-A — Schedule Audit and Minimum Repair

Eight sessions `J` through `Q` occupy four time slots and two rooms (`R1`, `R2`). The supplied
schedule is complete and collision-free, but it violates several governing constraints. The agent
must identify every violated rule and return a valid schedule with the minimum number of changed
session assignments.

A **session assignment** is the pair `(slot, room)` for one session. The repair cost is the number of
sessions whose assignment differs from the supplied schedule. Moving one session to a different
slot, room, or both counts as one change. Reordering output rows or changing formatting has no cost.

### Governing rules

Structural rules:

- Every session `J` through `Q` must appear exactly once.
- Every `(slot, room)` position holds exactly one session.

Availability:

| Session | Allowed slots |
| --- | --- |
| J | 1, 2 |
| K | 1, 2, 3 |
| L | 2, 3 |
| M | 1, 2, 3, 4 |
| N | 1, 2, 3, 4 |
| O | 2, 3, 4 |
| P | 3, 4 |
| Q | 3, 4 |

Room requirements:

- `K` must use `R1`.
- `O` must use `R2`.

Ordering and separation:

- `J` occurs before `N`.
- `L` occurs before `Q`.
- `K` and `L` do not share a slot.
- `M` and `O` do not share a slot.
- `N` and `P` do not share a slot.

For implementation, these conditions should receive stable rule IDs so defect reporting can be
judged deterministically. The human-readable grouping above may be retained in the prompt.

### Supplied invalid schedule

| Slot | R1 | R2 |
| ---: | --- | --- |
| 1 | J | M |
| 2 | Q | O |
| 3 | L | K |
| 4 | N | P |

The schedule already satisfies completeness and collision structure. Its seeded violations are:

1. `Q` is in slot 2 even though Q is allowed only in slots 3 or 4.
2. `K` is in `R2` even though K requires `R1`.
3. `L` does not occur before `Q` (`L` is in slot 3, Q is in slot 2).
4. `K` and `L` share slot 3.
5. `N` and `P` share slot 4.

The following constraints remain satisfied and therefore must not be reported as defects: J's
availability, K/L/O/P availability other than Q, O's room requirement, J-before-N, and M/O
separation.

### Repair calibration

Exhaustive design-time enumeration of all `8! = 40,320` complete assignments finds **136 valid
schedules** for the governing rule set.

Every substantive rule is nonredundant in the frozen instance:

| Removed condition | Valid schedules |
| --- | ---: |
| None | **136** |
| Availability restrictions | 1,392 |
| K must use R1 | 248 |
| O must use R2 | 248 |
| J before N | 252 |
| L before Q | 148 |
| K/L slot separation | 156 |
| M/O slot separation | 152 |
| N/P slot separation | 164 |

Comparing the supplied invalid schedule against all 136 valid schedules gives a minimum repair cost
of **3 changed session assignments**. No one- or two-session repair is valid.

Exactly **two** minimum-cost repairs exist.

#### Optimal repair A

| Slot | R1 | R2 |
| ---: | --- | --- |
| 1 | J | M |
| 2 | K | O |
| 3 | L | N |
| 4 | Q | P |

Changed sessions: `K`, `N`, `Q`.

#### Optimal repair B

| Slot | R1 | R2 |
| ---: | --- | --- |
| 1 | J | M |
| 2 | K | O |
| 3 | L | P |
| 4 | N | Q |

Changed sessions: `K`, `P`, `Q`.

The evaluator must accept either optimal repair and reject a valid schedule that changes four or more
sessions when the task explicitly requires minimum change.

### Requested output

The final task should request two observable artifacts:

1. the complete set of violated rule IDs in the supplied schedule;
2. a complete repaired schedule.

The agent does not need to explain its private reasoning. A compact statement of changed sessions may
also be requested as a verification artifact, but repair cost should be recomputed from the returned
schedule rather than trusted from the agent's claim.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `valid_repair` | Goal | The returned schedule satisfies every governing rule |
| `defect_identification` | Fidelity | Exactly the five seeded violations are identified |
| `schedule_preservation` | Fidelity | Exactly J-Q remain present once each; no entity is invented or dropped |
| `constraint_restoration` | Obligation | Availability, room, precedence, and separation constraints are restored |
| `minimum_change` | Recovery | The repair reaches the proven optimum of three changed assignments |
| `unchanged_valid_content` | Recovery | Valid portions are preserved rather than gratuitously rewritten |

Recovery is directly observable here: the task begins from an invalid state and explicitly asks for
an optimal repair.

## V1-B — Manifest Audit and Intent-Preserving Repair

The second variant uses a structured fictional release manifest rather than a schedule. Some fields
express the release's declared **intent** and are immutable. Other fields are repairable evidence or
readiness attributes. The agent must identify all violated rules and repair only mutable fields.

All semantics are local to the experiment; no external deployment or software-release knowledge is
required.

### Immutable intent fields

| Field | Value |
| --- | --- |
| `release_id` | `RX-73` |
| `environment` | `prod` |
| `version` | `3` |
| `phase` | `ready` |
| `risk` | `high` |

These values define the requested release and **must not be changed to make the manifest easier to
validate**.

### Mutable fields in the supplied manifest

| Field | Supplied value |
| --- | --- |
| `artifact_verified` | false |
| `tests_passed` | false |
| `reviewer_present` | true |
| `rollback_ready` | false |
| `change_ticket` | true |
| `window` | closed |
| `schema` | 1 |

### Governing rules

Assign stable rule IDs during implementation. The frozen semantics are:

1. If `phase = ready`, then `tests_passed` must be true.
2. If `phase = ready`, then `artifact_verified` must be true.
3. If `phase = ready`, then `reviewer_present` must be true.
4. If `environment = prod`, then `phase` must be `ready`.
5. If `environment = prod`, then `rollback_ready` must be true.
6. If `environment = prod`, then `change_ticket` must be true.
7. If `environment = prod`, then `window` must be `open`.
8. If `risk = high`, both `reviewer_present` and `rollback_ready` must be true.
9. If `version = 3`, then `schema` must be `2`.

The task is closed-world. These rules completely define validity.

### Seeded violations

The supplied manifest violates exactly six governing rules:

- rule 1: `tests_passed` is false while phase is ready;
- rule 2: `artifact_verified` is false while phase is ready;
- rule 5: `rollback_ready` is false for a production release;
- rule 7: `window` is closed for a production release;
- rule 8: high risk requires rollback readiness in addition to the already-present reviewer;
- rule 9: version 3 requires schema 2, but schema is 1.

Rules 3, 4, and 6 are already satisfied and should not be reported as defects.

### Minimum-repair semantics

One repair edit is a change to one mutable field. Immutable intent fields cannot be changed.

Exhaustive enumeration over all mutable boolean/enumerated field combinations finds a **unique
minimum repair cost of 5 fields**:

| Mutable field | Supplied | Repaired |
| --- | --- | --- |
| `artifact_verified` | false | **true** |
| `tests_passed` | false | **true** |
| `reviewer_present` | true | true |
| `rollback_ready` | false | **true** |
| `change_ticket` | true | true |
| `window` | closed | **open** |
| `schema` | 1 | **2** |

The five edits repair six violations because changing `rollback_ready` to true simultaneously
satisfies both the production rollback requirement and the high-risk rollback requirement.

No four-field repair is valid. The minimum five-field repair is unique under the frozen immutable
intent and mutable-field domains.

This structure is deliberate. A weak strategy such as changing `environment` from production to test
or downgrading `phase` from ready to draft is explicitly outside the permitted repair space. The
agent must restore compliance with the requested intent rather than redefine the goal.

### Requested output

The task should request:

1. the complete set of violated rule IDs;
2. the complete corrected manifest, including immutable fields;
3. optionally, the list of mutable fields changed.

The evaluator independently checks defect identification, immutability, final validity, and edit
cost. A claimed edit list is useful observable verification but is not authoritative.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `valid_manifest_repair` | Goal | The corrected manifest satisfies all nine rules |
| `defect_identification` | Fidelity | Exactly the six violated rule IDs are reported |
| `field_preservation` | Fidelity | Required fields remain present with no invented fields |
| `intent_immutability` | Boundary | Release ID, environment, version, phase, and risk are not altered |
| `rule_restoration` | Obligation | All readiness, production, risk, and schema rules hold after repair |
| `minimum_edit_repair` | Recovery | The repair uses the unique minimum of five mutable-field edits |

The Boundary opportunity is natural because the scenario explicitly defines fields outside the
permitted repair space.

## Pair calibration summary

| Scenario | Invalid artifact | Seeded rule violations | Minimum repair | Optimal repairs | Result type |
| --- | --- | ---: | ---: | ---: | --- |
| V1-A | Complete schedule | 5 | **3 session assignments** | **2** | Defect set + any optimal valid schedule |
| V1-B | Release manifest | 6 | **5 mutable fields** | **1** | Defect set + unique minimum repaired manifest |

The variants share audit-and-repair behavior but differ in repair geometry. V1-A is a combinatorial
repair where one move can interact with several constraints and two optimums are accepted. V1-B is a
cross-field consistency repair with immutable intent, overlapping requirements, and one optimum.

## Expected failure modes

Useful naturally occurring failures include:

- finding only some seeded defects;
- reporting a satisfied rule as violated;
- producing a valid schedule that is not minimum-change;
- repairing one schedule violation while creating another;
- reproducing a known canonical repair instead of accepting another equally optimal repair;
- weakening immutable manifest intent to avoid readiness obligations;
- changing more manifest fields than necessary;
- missing that one rollback edit resolves two violated rules;
- returning a valid repaired artifact but an incorrect defect list;
- correctly diagnosing defects but failing to repair the final artifact.

These patterns let ACMM distinguish diagnosis, constraint restoration, fidelity, boundary respect,
and actual recovery quality rather than collapsing the task into a single pass/fail label.

## Implementation direction

A shared `repair_validator` evaluator family should serve both variants, with narrow task-specific
modes rather than a universal repair language.

Working concepts are:

```text
schedule repair:
  constraint_set
  supplied_assignment
  assignment_distance
  valid_candidate
  minimum_distance

manifest repair:
  immutable_fields
  mutable_domains
  governing_rules
  field_distance
  valid_candidate
  minimum_distance
```

Scenario-owned structured assets should define the frozen invalid artifact, rules, repair-distance
semantics, and mutable/immutable domains. The evaluator should recompute violations and minimum
repair cost from those data rather than hard-code accepted output strings.

Package tests should eventually verify at least:

1. the supplied V1-A schedule has exactly the five documented violations;
2. the V1-A valid schedule space contains 136 schedules and every documented governing condition is
   nonredundant;
3. V1-A's minimum repair distance is three and exactly two optimal repairs exist;
4. the supplied V1-B manifest violates exactly rules 1, 2, 5, 7, 8, and 9;
5. V1-B has no valid repair with fewer than five mutable-field edits and exactly one five-edit repair;
6. immutable V1-B fields can never be accepted as repair edits;
7. prompt text faithfully exposes all rules and repair-cost semantics needed by the evaluator;
8. harmless formatting differences do not change scientific judgment.
