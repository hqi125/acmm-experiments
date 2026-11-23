# P2 — Allocation

> **Design status:** frozen and implemented. This family is part of the completed 384-run Minimal Agent Baseline acquisition.

P2 tests whether an agent can maintain a globally consistent allocation while satisfying capacity,
eligibility, coverage, and relationship rules. P2-A uses fixed group cardinality and required
coverage; P2-B uses weighted capacity. This keeps the pair related without making one a cosmetic
rewrite of the other.

## P2-A — Project Staffing

Nine fictional specialists `A` through `I` must be assigned exactly once to projects `X`, `Y`, and
`Z`. Each project receives exactly three specialists.

### Eligibility

| Specialist | Eligible projects |
| --- | --- |
| A | X, Y |
| B | X, Z |
| C | Y, Z |
| D | X, Y, Z |
| E | X, Y, Z |
| F | X, Y, Z |
| G | X, Y, Z |
| H | X, Y, Z |
| I | X, Y, Z |

### Required coverage

- Project `X` contains at least one of `{A, D, G}`.
- Project `Y` contains at least one of `{C, E, H}`.
- Project `Z` contains at least one of `{B, F, I}`.

### Relationship rules

- `D` and `H` are assigned to the same project.
- `E` and `G` are assigned to different projects.
- `F` and `I` are assigned to different projects.
- `A` and `B` are assigned to different projects.

### Example valid result

| Project | Specialists |
| --- | --- |
| X | A, D, H |
| Y | C, E, F |
| Z | B, G, I |

This is only an example. Any complete allocation satisfying every rule is valid.

### Calibration

There are `3^9 = 19,683` raw project assignments before constraints. Exhaustive design-time
enumeration finds **38 valid allocations**.

Every major rule group changes the feasible set:

| Removed condition | Valid allocations |
| --- | ---: |
| None | **38** |
| Exact project cardinality | 318 |
| Eligibility restrictions | 90 |
| Required coverage | 56 |
| D/H same project | 166 |
| E/G different projects | 54 |
| F/I different projects | 47 |
| A/B different projects | 50 |

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `valid_allocation` | Goal | The full staffing allocation satisfies the task |
| `specialist_preservation` | Fidelity | Exactly A-I appear once |
| `project_capacity` | Obligation | Each project receives exactly three specialists |
| `eligibility` | Boundary | No specialist is assigned outside the explicitly permitted project set |
| `required_coverage` | Obligation | X/Y/Z each receive the required member-set coverage |
| `relationship_rules` | Obligation | Pairing and separation constraints hold |

Eligibility is treated as Boundary because the task explicitly defines a permitted assignment space;
the evaluator need not invent a separate violation trap.

## P2-B — Storage Zones

Ten abstract cargo units `A` through `J` must be placed exactly once into storage zones `W`, `X`,
`Y`, and `Z`. Cargo labels and compatibility are fictional; no real-world storage or safety knowledge
is relevant.

### Loads

| Unit | Load |
| --- | ---: |
| A | 2 |
| B | 2 |
| C | 3 |
| D | 1 |
| E | 2 |
| F | 1 |
| G | 3 |
| H | 2 |
| I | 1 |
| J | 1 |

### Zone capacities

| Zone | Maximum load |
| --- | ---: |
| W | 5 |
| X | 4 |
| Y | 5 |
| Z | 6 |

### Allowed zones

| Unit | Allowed zones |
| --- | --- |
| A | W, X |
| B | Y, Z |
| C | W, Y |
| D | W, X, Y, Z |
| E | X, Z |
| F | W, Y, Z |
| G | Y, Z |
| H | W, X, Y |
| I | X, Y, Z |
| J | W, X, Y, Z |

### Relationship rules

- `C` and `D` are placed in the same zone.
- `A` and `H` are placed in different zones.
- `E` and `J` are placed in different zones.
- `F` and `G` are placed in different zones.

### Example valid result

| Zone | Units | Load |
| --- | --- | ---: |
| W | A, F, J | 4 |
| X | E, H | 4 |
| Y | C, D, I | 5 |
| Z | B, G | 5 |

This is only an example. The evaluator accepts any valid placement.

### Calibration

The raw assignment space is `4^10 = 1,048,576`. Exhaustive design-time enumeration finds **41 valid
placements**.

The weighted capacities are active constraints rather than decorative limits. Removing a single zone
capacity while preserving all other rules expands the valid set:

| Removed capacity | Valid placements |
| --- | ---: |
| None | **41** |
| W capacity | 271 |
| X capacity | 63 |
| Y capacity | 507 |
| Z capacity | 86 |

The restricted allowed-zone declarations and the co-location/separation relationships were also
checked during calibration to ensure that the frozen instance does not contain accidental decorative
constraints. Exact per-rule calibration counts can be retained in evaluator tests when the scenario
asset is implemented.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `valid_placement` | Goal | The full placement is valid |
| `cargo_preservation` | Fidelity | Exactly A-J appear once |
| `zone_capacity` | Obligation | Weighted zone loads remain at or below their limits |
| `zone_eligibility` | Boundary | Units remain inside their explicitly allowed zones |
| `colocation` | Obligation | C and D remain together |
| `separation` | Obligation | A/H, E/J, and F/G remain separated |

## Pair calibration summary

| Scenario | Allocation structure | Raw search space | Valid solutions | Natural opportunities |
| --- | --- | ---: | ---: | ---: |
| P2-A | Fixed-cardinality grouping | 19,683 | **38** | 6 |
| P2-B | Weighted-capacity placement | 1,048,576 | **41** | 6 |

P1 and P2 together therefore cover four distinct constructive representations: two-dimensional
scheduling, linear sequencing, fixed-cardinality grouping, and weighted-capacity placement.

## Implementation direction

P2 can reuse the broader constraint-planning evaluator machinery but should use an assignment mode
rather than pretending its data is a schedule or sequence. Useful narrow primitives include
`exactly_once`, `group_cardinality`, `group_capacity`, `allowed_destination`, required member-set
coverage, `same_group`, and `different_group`.

Structured package data should remain the source of truth for both prompt rules and evaluation.
