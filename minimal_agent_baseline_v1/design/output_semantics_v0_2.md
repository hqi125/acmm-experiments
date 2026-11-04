# Contract v0.2 Interpreted-Output Migration

## Motivation

Post-acquisition review showed two independent presentation effects that should not become scientific failures: bounded JSON wrapper/escaping noise, and R1-B returning semantic integer `6` as canonical JSON string `"6"`. Earlier package revisions handled these concerns inside evaluator code, which made interpretation policy harder to audit and duplicated Core responsibilities.

The experiment now uses the normal Contract-directed interpretation pipeline. Raw evidence remains immutable; Core derives an interpreted structured payload once, applies only explicitly declared scalar representation policies, and passes that view to the package evaluator.

## Structured binding

Every Minimal Agent Baseline scenario declares where its structured result lives. For example P1-A declares:

```yaml
output_semantics:
  structured_object:
    evidence_id: final_response
    payload_path: result
    required_payload_keys:
      - schedule
```

The required payload key differs by scenario (`schedule`, `sequence`, `events`, `configuration`, and so on). This declaration replaces package-local JSON parsing and prevents malformed outer responses from being mistaken for an arbitrary nested row.

## R1-B scalar policy

R1-B additionally declares exactly one relaxed scalar field:

```yaml
output_semantics:
  structured_object:
    evidence_id: final_response
    payload_path: result
    required_payload_keys:
      - configuration
  scalar_fields:
    - path: result.configuration.quota.value
      semantic_type: integer
      accepted_serializations:
        - native
        - canonical_string
```

This means integer `6` and canonical string `"6"` are equivalent at this field only. `"06"`, `"6.0"`, booleans, symbolic configuration values, and layer names are not covered by this declaration.

## Responsibility boundary

The final path is:

1. adapters persist raw `final_response.txt` unchanged;
2. Core derives a bounded structured interpretation from the Contract declaration;
3. Core applies declared representation semantics to the interpreted view only;
4. the package evaluator receives `context.interpreted_evidence["final_response"].payload` and judges task correctness; and
5. Core records any interpretation normalization automatically in judgment detail.

The Minimal Agent Baseline runtime no longer calls the JSON decoder or semantic scalar comparator directly. Its validators contain only scientific task logic.

## Corpus replay

Replaying the latest 128-run Agent Zero leg through the integrated path preserves the previously qualified scientific outcome exactly:

| Scenario | Fully compliant runs |
| --- | ---: |
| R1-B Effective Configuration | 6/8 |
| V1-A Schedule Repair | 4/8 |
| V1-B Manifest Repair | 5/8 |
| All other 13 scenarios | 8/8 each |

Thirty-four runs require syntax interpretation, and eight R1-B runs use canonical-string-to-integer semantic interpretation. The remaining failures are substantive rather than representation artifacts.
