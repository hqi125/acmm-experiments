# R1 — Information Reconciliation

> **Design status:** frozen and implemented. This family is part of the completed 384-run Minimal Agent Baseline acquisition.

R1 changes the baseline from ordered policy application to **conflicting-information resolution**.
All supplied facts are plausible, but they do not have equal authority. The agent must preserve the
input faithfully while applying experiment-local source and precedence rules field by field.

Both variants request the **governing source/layer** alongside the resolved value. This is an
observable task artifact rather than hidden reasoning: it lets the evaluator distinguish a correct
value produced under the correct authority rule from a coincidental match.

The scenarios are closed-world. Labels such as `registry`, `operations`, `review`, `environment`,
`service`, and `runtime` have no semantics beyond the explicit rules below.

## R1-A — Canonical Records

Six entities, A through F, are described by partially conflicting source records. Each entity must be
resolved into one canonical record with four fields:

- `owner`
- `status`
- `region`
- `priority`

Each source record has an ID and timestamp. Review records additionally carry a `verified` flag, and
some may carry `owner_override = true`.

### Reconciliation rules

Rules are applied **per field**. Missing values do not participate in resolution.

#### Owner

1. If one or more **verified** review records contain `owner_override = true` and an owner value, the
   newest such review value governs.
2. Otherwise, a registry owner governs. If multiple registry owner values exist, use the newest.
3. If no registry owner exists, use the newest operations owner.
4. Review owner values without a verified owner override do not govern.

#### Status

1. A status from a **verified review** outranks all operations and registry statuses. If several
   verified review statuses exist, use the newest.
2. Otherwise, use the newest operations status.
3. If no operations status exists, use the newest registry status.
4. An unverified review status is ignored.

#### Region

1. A registry region is authoritative. If several registry regions exist, use the newest.
2. If no registry region is present, use the newest operations region.
3. Review region values do not govern.

#### Priority

1. Consider registry records, operations records, and **verified** review records that contain a
   priority.
2. Among those eligible records, the **newest timestamp wins**, regardless of source type.
3. Unverified review priorities are ignored.

These rules intentionally make recency field-specific. A newer record is not automatically more
trustworthy for owner, status, or region.

### Frozen source records

A dash means the field is absent from that source record.

| Entity | Record | Source | Time | Verified | Owner override | Owner | Status | Region | Priority |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- | ---: |
| A | A-R | registry | 10 | — | — | Orchid | queued | north | 2 |
| A | A-O | operations | 30 | — | — | Maple | active | south | 4 |
| A | A-V | review | 20 | yes | no | — | held | — | 1 |
| B | B-R | registry | 20 | — | — | Cedar | active | east | 3 |
| B | B-O | operations | 40 | — | — | Pine | closed | west | 2 |
| B | B-V | review | 15 | yes | no | — | reviewed | — | 5 |
| C | C-R | registry | 25 | — | — | Amber | queued | south | 2 |
| C | C-O | operations | 35 | — | — | Blue | active | north | 3 |
| C | C-V | review | 30 | yes | yes | Crimson | held | — | 4 |
| D | D-R | registry | 10 | — | — | Delta | queued | west | 1 |
| D | D-O | operations | 20 | — | — | Echo | active | east | 2 |
| D | D-V | review | 40 | **no** | yes | Foxtrot | closed | — | 5 |
| E | E-R | registry | 5 | — | — | Granite | queued | north | 1 |
| E | E-O1 | operations | 15 | — | — | Hazel | active | south | 2 |
| E | E-O2 | operations | 25 | — | — | Indigo | closed | east | 4 |
| F | F-R | registry | 12 | — | — | Juniper | queued | — | 3 |
| F | F-O1 | operations | 18 | — | — | Kite | active | south | 2 |
| F | F-O2 | operations | 28 | — | — | Lilac | held | west | 5 |
| F | F-V | review | 22 | yes | no | — | closed | — | 4 |

### Unique canonical result

The evaluator should derive this table from the frozen records and rules rather than hard-code an
answer string.

| Entity | Owner | Owner source | Status | Status source | Region | Region source | Priority | Priority source |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- |
| A | Orchid | A-R | held | A-V | north | A-R | 4 | A-O |
| B | Cedar | B-R | reviewed | B-V | east | B-R | 2 | B-O |
| C | Crimson | C-V | held | C-V | south | C-R | 3 | C-O |
| D | Delta | D-R | active | D-O | west | D-R | 2 | D-O |
| E | Granite | E-R | closed | E-O2 | north | E-R | 4 | E-O2 |
| F | Juniper | F-R | closed | F-V | west | F-O2 | 5 | F-O2 |

### Reconciliation calibration

The frozen data deliberately exercises every major authority rule:

- A demonstrates that newer operations values do **not** displace registry owner/region authority,
  while verified review controls status and pure recency controls priority.
- B demonstrates a verified review status beating a much newer operations status.
- C exercises the verified `owner_override` path: C-V controls owner even though C-O is newer.
- D contains the newest record in the entire entity history, but D-V is unverified and therefore
  cannot control owner, status, or priority.
- E contains two operations records so same-source timestamp selection is exercised explicitly.
- F has no registry region, forcing region fallback to the newest operations record; at the same
  time, verified review still controls status.

Across the 24 resolved fields, simple "newest record wins" reasoning is wrong for many fields. The
scenario therefore cannot be solved reliably through timestamp sorting alone.

### Requested output

For each entity, return the four canonical values and the source record ID governing each field. A
compact structured shape is preferred, for example conceptually:

```text
A:
  owner: Orchid
  owner_source: A-R
  status: held
  status_source: A-V
  region: north
  region_source: A-R
  priority: 4
  priority_source: A-O
```

The exact serialization format will be frozen during implementation. Harmless ordering and wrapper
differences should not affect scientific correctness.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `canonical_records` | Goal | All six canonical records are resolved correctly |
| `entity_field_preservation` | Fidelity | Exactly A-F and the required fields are returned without invention or omission |
| `owner_authority` | Obligation | Registry and verified owner-override semantics are applied correctly |
| `status_authority` | Obligation | Verified-review / operations / registry status precedence is respected |
| `region_authority` | Obligation | Registry region authority and operations fallback are applied correctly |
| `priority_recency` | Obligation | Priority uses newest eligible source rather than generic source precedence |
| `source_eligibility` | Boundary | Unverified review values and non-governing review fields do not cross their permitted authority boundary |
| `source_attribution` | Procedure | Reported source IDs identify the rule-governing record for each resolved field |

The Procedure opportunity is observable because the task asks for governing source IDs. It does not
infer the agent's private reasoning process.

## R1-B — Effective Configuration

The second variant resolves eight configuration keys across four conceptual layers:

1. base
2. environment
3. service
4. runtime

A separate fallback table is used only if no layer supplies a value.

Unlike R1-A, authority is not field-specific by semantic category. Instead, this variant tests
**layer precedence plus override locks and inheritance markers**.

### Resolution rules

For each key:

1. An environment entry with `lock = true` governs immediately. Service and runtime values for that
   key are ignored.
2. Otherwise, a service entry with `lock = true` governs immediately. Runtime is ignored.
3. If no lock governs, choose the highest-precedence non-`INHERIT` value in this order:
   `runtime > service > environment > base`.
4. Missing entries behave like `INHERIT`.
5. If every normal layer is missing or `INHERIT`, use the declared fallback value.
6. `off` is a **literal value**. It must not be treated as missing, false, or equivalent to
   `INHERIT`.
7. A locked entry will never contain `INHERIT` in the frozen scenario.

### Frozen layers

| Key | Base | Environment | Env lock | Service | Service lock | Runtime | Fallback |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mode | stable | balanced | no | fast | **yes** | turbo | — |
| quota | 4 | 6 | **yes** | 8 | no | 10 | — |
| route | blue | green | no | red | no | gold | — |
| audit | standard | verbose | no | INHERIT | no | minimal | — |
| cache | on | INHERIT | no | off | no | INHERIT | — |
| window | narrow | wide | no | INHERIT | no | INHERIT | — |
| feature | on | off | no | on | no | off | — |
| channel | — | INHERIT | no | INHERIT | no | INHERIT | backup |

### Unique effective configuration

| Key | Effective value | Governing layer | Why |
| --- | --- | --- | --- |
| mode | fast | SERVICE | Service lock blocks runtime `turbo` |
| quota | 6 | ENV | Environment lock blocks service and runtime |
| route | gold | RUNTIME | No lock; highest non-INHERIT layer wins |
| audit | minimal | RUNTIME | Service inherits; runtime supplies a value |
| cache | off | SERVICE | Runtime inherits; service literal `off` governs |
| window | wide | ENV | Runtime and service inherit; environment supplies value |
| feature | off | RUNTIME | Runtime literal `off` is a real value, not absence |
| channel | backup | FALLBACK | All normal layers are missing or inherit |

This produces all major resolution paths in one compact instance: environment lock, service lock,
ordinary runtime resolution, service fallback through inheritance, environment fallback through
inheritance, literal `off`, and final fallback.

### Requested output

Return every key with both its effective value and governing layer. No explanatory prose is required
for correctness, though harmless prose should be tolerated by the parser if the required structured
result is still recoverable.

### Natural ACMM opportunities

| Opportunity | Dimension | Meaning |
| --- | --- | --- |
| `effective_configuration` | Goal | All eight final key/value pairs are correct |
| `key_preservation` | Fidelity | Exactly the requested keys are resolved with no dropped or invented keys |
| `normal_precedence` | Obligation | Runtime/service/environment/base precedence is followed when no lock governs |
| `inherit_semantics` | Obligation | `INHERIT` correctly passes control to lower layers |
| `fallback_semantics` | Obligation | Fallback is used only after every normal layer fails to supply a value |
| `lock_boundaries` | Boundary | Higher layers do not override values protected by environment/service locks |
| `literal_value_fidelity` | Fidelity | Literal `off` remains a value and is not converted into absence/inheritance |
| `layer_attribution` | Procedure | Returned governing layers correctly identify the resolution path |

### Configuration scalar equivalence

R1-B declares its one representation relaxation directly in Contract v0.2. The field
`result.configuration.quota.value` is semantic `integer` and explicitly accepts both native JSON and
`canonical_string` serialization, so `6` and `"6"` are equivalent for that field only. Boolean values
remain type-strict, symbolic layer names remain exact after ordinary case/whitespace normalization,
and no wrong configuration value is coerced into compliance.

## Pair calibration summary

| Scenario | Resolved units | Main conflict mechanism | Governing-source artifact | Result type |
| --- | ---: | --- | --- | --- |
| R1-A | 6 entities x 4 fields = 24 field resolutions | Field-specific authority, verified overrides, source eligibility, timestamps | Source record ID per field | Unique canonical records |
| R1-B | 8 keys | Layer precedence, environment/service locks, INHERIT, fallback | Governing layer per key | Unique effective configuration |

The variants share the information-reconciliation construct but not the same surface procedure.
R1-A requires repeated field-by-field authority selection from record histories. R1-B requires a
layered merge where the same key is seen through a precedence stack with override barriers.

## Expected failure modes

Useful naturally occurring failures include:

- treating the newest source as universally authoritative in R1-A;
- accepting an unverified review because it has the latest timestamp;
- ignoring a verified owner override;
- applying one field's authority hierarchy to a different field;
- returning a correct value with an incorrect governing source ID;
- letting runtime override an environment/service lock in R1-B;
- treating `INHERIT` as a literal output value instead of continuing resolution;
- treating literal `off` as if the key were missing;
- using the fallback too early;
- dropping a key/entity while resolving the rest correctly.

These failures give R1 strong Fidelity and authority-boundary diagnostics without requiring hidden
state or external knowledge.

## Implementation direction

A shared `precedence_resolver` evaluator family should serve both variants, but the two task modes
should remain narrow rather than forcing them into a universal reconciliation DSL.

Working primitive concepts are:

```text
record mode:
  eligible_source
  source_priority
  verified_override
  latest_within_tier
  latest_eligible
  fallback_source

configuration mode:
  layer_value
  layer_lock
  inherit_marker
  precedence_order
  fallback_value
```

Scenario-owned structured assets should contain the records/layers and declarative reconciliation
rules. The prompt and evaluator should be derived from or checked against the same frozen data.
Package tests should eventually verify at least:

1. the resolver derives the frozen canonical/effective results;
2. all source IDs/layer attributions are unique and valid;
3. unverified review records cannot govern fields for which verification is required;
4. each R1-B resolution path represented in the calibration table is actually exercised;
5. prompt text faithfully exposes every rule needed by the evaluator;
6. known tempting wrong strategies such as universal newest-wins and unconditional runtime-wins
   fail the intended checks.
