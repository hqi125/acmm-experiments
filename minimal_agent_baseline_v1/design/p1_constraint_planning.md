# P1 — Constraint Planning

> **Design status:** provisionally frozen. Concrete instances and exhaustive feasibility calibration
> are complete. Structured scenario assets and evaluator code have not yet been implemented.

P1 tests constructive planning under interacting constraints. Both variants accept any valid solution,
but their representations differ substantially: P1-A is a two-dimensional time/room assignment;
P1-B is a one-dimensional sequence.

The pair intentionally avoids a unique canonical answer. The scientific question is whether an agent
can construct a globally valid result, not whether it happens to reproduce one reference arrangement.

## P1-A — Workshop Schedule

Eight workshops `A` through `H` must be scheduled into four time slots and two rooms (`R1`, `R2`).
Each `(slot, room)` position holds at most one workshop, and every workshop must appear exactly once.

### Rules

Availability:

| Workshop | Allowed slots |
| --- | --- |
| A | 1, 2, 3, 4 |
| B | 1, 2 |
| C | 2, 3 |
| D | 1, 2, 3, 4 |
| E | 1, 2, 3, 4 |
| F | 1, 2, 3, 4 |
| G | 3, 4 |
| H | 3, 4 |

Room requirements:

- `C` must use `R2`.
- `G` must use `R1`.

Ordering and separation:

- `A` occurs before `F`.
- `C` occurs before `E`.
- `F` and `G` do not share a slot.
- `A` and `C` do not share a slot.
- `A` and `B` do not share a slot.

### Example valid result

| Slot | R1 | R2 |
| ---: | --- | --- |
| 1 | A | D |
| 2 | B | C |
| 3 | E | F |
| 4 | G | H |

This is an example only; the evaluator must accept any valid schedule.

### Calibration

The eight workshop/position assignments create `8! = 40,320` raw permutations. Exhaustive design-time
enumeration finds **28 valid schedules** under the complete rule set.

Removing each substantive constraint expands the feasible set, confirming that the final rules are
not decorative:

| Removed condition | Valid schedules |
| --- | ---: |
| None | **28** |
| Slot availability restrictions | 1,120 |
| C must use R2 | 48 |
| G must use R1 | 48 |
| A before F | 160 |
| C before E | 124 |
| F/G slot separation | 36 |
| A/C slot separation | 44 |
| A/B slot separation | 80 |

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `valid_plan` | Goal | The complete schedule satisfies the task |
| `entity_preservation` | Fidelity | Exactly A-H appear once; nothing is missing, duplicated, or invented |
| `slot_availability` | Obligation | B/C/G/H respect their allowed slots |
| `room_requirements` | Obligation | C and G respect their required rooms |
| `precedence` | Obligation | A<F and C<E |
| `separation` | Obligation | F/G, A/C, and A/B respect slot separation |

Procedure and Recovery are deliberately not invented for this task because the observable artifact is
a final construction rather than an execution trace or repair process.

## P1-B — Batch Sequence

Nine batches `A` through `I` must occupy positions 1 through 9 exactly once.

### Rules

- `B` occurs before `F`.
- `C` occurs immediately before `H`.
- `I` occupies position 4 or 5.
- Exactly one of `A` and `D` is among positions 1-3.
- `G` and `H` have at least two intervening positions.
- `B` is not in position 1.
- `A` occurs before `D`.
- `F` occurs before `G`.
- `E` is among positions 1-3.

### Example valid result

`A, B, E, F, I, G, D, C, H`

This is an example only; any permutation satisfying every rule is valid.

### Calibration

The raw sequence space is `9! = 362,880` permutations. Exhaustive design-time enumeration finds
**24 valid sequences**.

Every rule is nonredundant in the frozen instance:

| Removed condition | Valid sequences |
| --- | ---: |
| None | **24** |
| B before F | 136 |
| C immediately before H | 476 |
| I in position 4 or 5 | 184 |
| Exactly one of A/D in positions 1-3 | 81 |
| G/H separation | 92 |
| B not in position 1 | 32 |
| A before D | 48 |
| F before G | 208 |
| E in positions 1-3 | 132 |

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `valid_plan` | Goal | The complete sequence satisfies all rules |
| `entity_preservation` | Fidelity | Exactly A-I occur once |
| `precedence` | Obligation | B<F, A<D, and F<G |
| `adjacency_separation` | Obligation | C immediately precedes H and G/H separation holds |
| `position_limits` | Obligation | I, B, and E position restrictions hold |
| `partition_condition` | Obligation | Exactly one of A/D lies in the first three positions |

## Pair calibration summary

| Scenario | Representation | Raw search space | Valid solutions | Natural opportunities |
| --- | --- | ---: | ---: | ---: |
| P1-A | Time x room assignment | 40,320 | **28** | 6 |
| P1-B | Linear sequence | 362,880 | **24** | 6 |

Raw feasible-space percentages are not treated as a universal difficulty metric because the
representations differ. The similar accepted-solution counts are nevertheless a useful calibration
signal: neither variant is effectively deterministic, and neither admits a very large set of easy
alternatives.

## Implementation direction

Both scenarios should use a shared constraint-planning evaluator family backed by structured,
package-owned scenario data. Useful narrow primitives include `exactly_once`, slot/position
restrictions, required resource, `before`, `immediately_before`, same/different slot, separation
distance, and partition cardinality.

The structured source should drive both prompt rendering/verification and evaluator behavior so the
package can test that the prompt and scientific model have not drifted apart. This is a narrow
scenario representation for the constraint-planning family, not an attempt to create a universal
ACMM task DSL.
