# Structured-Output Hardening After Full Acquisition

The first 384-run Minimal Agent Baseline acquisition completed cleanly at the execution layer, but
post-acquisition review exposed a systematic structured-output adjudication problem. This note records
the correction boundary so the raw model evidence and the evaluator policy remain distinguishable.

## Acquisition status

The scientific acquisition itself is retained unchanged:

- 384 of 384 planned runs resolved;
- all 384 runs were valid on the first attempt;
- no timeouts or retries occurred; and
- the original `final_response.txt` evidence remains immutable.

The issue was downstream: some valid task answers were serialized with harmless JSON presentation
noise and the original package parser could either reject them or, more dangerously, decode a nested
child object instead of the intended result object.

## Corpus audit

Across the 384 saved final responses:

- 352 require no structured-output normalization;
- 32 are not directly usable as strict whole-string JSON objects;
- all 384 can be resolved to the intended result/payload object under the bounded recovery policy;
- 21 previously mis-adjudicated runs change at least one opportunity outcome when only JSON syntax
  recovery is corrected; and
- 123 previously failing judgments recover to their semantic outcome (117 Agent Zero judgments and
  6 Open WebUI judgments). Hermes judgments are unchanged by the JSON syntax correction.

Observed normalization classes in this acquisition are:

| Normalization | Runs | Meaning |
| --- | ---: | --- |
| none | 352 | Direct intended object is readable |
| `embedded_json` | 5 | Valid object surrounded by a fence or surplus trailing material |
| `trailing_delimiter_completion` | 6 | Final `}` / `]` delimiters were omitted |
| `quote_deescape` + `embedded_json` | 19 | One response-wrapper escaping layer obscured the intended payload object |
| `quote_deescape` | 1 | The complete object was emitted with one escaped structural-quote layer |
| `duplicate_property_quote` | 1 | One object key had a duplicated opening quote |

These counts describe presentation normalization only; they do not imply that the recovered task
content is scientifically correct. The ordinary scenario validators still decide semantic compliance.

## Core recovery policy

Structured-output recovery is now implemented as a generic Core interpretation primitive rather than an Agent Zero or Minimal Agent Baseline workaround. Contract v0.2 declares the evidence channel, payload path, and required payload keys; Core performs recovery before the package evaluator runs. Recovery is ordered by conservatism and is bounded to syntax-only presentation artifacts:

1. exact/embedded valid JSON object extraction;
2. one JSON-string wrapper;
3. missing trailing delimiter completion;
4. trailing comma removal;
5. duplicated property-opening quote repair; and
6. up to three escaped structural-quote layers when less invasive recovery does not succeed.

The decoder never mutates persisted evidence and exposes the normalization modes used. Required keys
prevent a malformed outer response from degrading into a valid but unrelated nested row object.

Core records any normalization mode in judgment detail for judgments that cite interpreted evidence. The final baseline design also declares `exact_json_object` as the accepted presentation and adds one explicit `output_representation_fidelity` opportunity to every scenario. A recovered answer can therefore remain semantically compliant while receiving a Fidelity violation for malformed external representation. Contract v0.2 also binds the structured payload and applies declared scalar representation semantics before the package evaluator runs; the package no longer reparses raw evidence itself.

## What this correction does not do

This pass intentionally does **not** perform semantic coercion. R1-B's narrow numeric representation
policy is now declared in Contract v0.2 at `result.configuration.quota.value`: the field is semantic
`integer` and explicitly accepts both native JSON and `canonical_string` serialization. The package
evaluator applies Core's public semantic-scalar comparator, while structured-output syntax recovery
remains separate. Boolean values and symbolic configuration/layer values remain strict. Likewise, the parser
does not invent omitted fields, repair arbitrary prose, or reinterpret genuinely contradictory task
content.

## Re-adjudication implication

Historical trajectories remain immutable and can be replayed through the same deterministic interpretation/adjudication pipeline when qualification requires it. New acquisitions are judged once through the Contract-directed path; no permanent second adjudication layer is introduced.
