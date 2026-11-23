# Minimal Agent Baseline — First Executable Checkpoint

> **Historical checkpoint.** This file records the first executable package milestone. The package later
> completed live qualification, the 384-run scientific acquisition, post-acquisition structured-output
> hardening, and final analysis. The milestone-specific future tense below is intentionally historical.

This checkpoint records the first complete translation of the frozen 16-scenario design into an
executable Experiment Package. It is an implementation checkpoint, not the final experimental freeze.
Live execution has not yet been used to tune parsing tolerance, timeout behavior, or agent-specific
prompt ergonomics.

## Package shape

The package now contains:

```text
minimal_agent_baseline_v1/
    experiment-package.yaml
    experiment.yaml
    README.md

    assets/
        scenarios/
            <16 JSON scenario assets>

    runtime/
        __init__.py
        components.py
        evaluator.py
        parsing.py
        validators.py

    design/
        ...
```

No integration component is declared. Every Contract scenario explicitly declares
`capabilities.tools: []`, which distinguishes the baseline from tool-bearing packages and allows Core
to skip the experiment Tool overlay/configuration path.

## Contract structure

The Contract binds the three qualified shared-model subjects:

- `hermes_gpt_oss120b`;
- `open_webui_gpt_oss120b`;
- `agent_zero_gpt_oss120b`.

It declares all 16 frozen scenario IDs, 8 repetitions, `subject_repetition_scenario` ordering, cyclic
scenario rotation, and therefore **384 planned executions**.

Rather than creating a top-level requirement for every local rule, the Contract uses six broad
experiment requirements — Goal, Obligation, Boundary, Procedure, Fidelity, and Recovery. Scenario
opportunities instantiate those requirements at the level where the concrete evidence exists. This
keeps the top-level ACMM hierarchy readable while preserving detailed judgments inside each run.

All opportunities currently use one evaluator ID, `minimal_baseline`. The evaluator receives both the
scenario and opportunity IDs and dispatches into the relevant deterministic validator. This is an
interface simplification, not a collapse of scientific distinctions: each opportunity still produces
its own judgment and dimension mapping.

## Structured scenario assets

One JSON asset is stored for each scenario under `assets/scenarios/`. The assets contain the frozen
entities, rules, initial state, policy tables, source records, repair state, workflow expectations, or
dependency graph required by that task. Scientific task data is therefore package-owned and separate
from generic runtime environment configuration.

Prompts in the Contract currently mirror these frozen assets manually. Prompt/asset drift should be
rechecked whenever either side changes. A generation/checking helper may be introduced later if that
manual invariant becomes burdensome.

## Output format and parser

Each task requests one compact JSON result object. The runtime parser accepts a direct JSON object or
a recoverable JSON object surrounded by harmless prose/Markdown, then validates scenario-specific
semantics. It does not require hidden reasoning.

Constructive tasks accept any valid solution. Unique-result tasks derive or store their deterministic
reference state from package assets. Rule/source IDs, event traces, and workflow traces are treated as
observable task artifacts when the design intentionally uses them for Procedure measurement.

## Runtime validator modes

The first pass implements validators for all frozen families:

- schedule and sequence constraints;
- fixed-cardinality and weighted allocation;
- inventory and lifecycle state interpretation;
- ordered first-match policy application;
- record and layered-configuration reconciliation;
- schedule and manifest repair;
- workflow case traces;
- staged and conditional dependency plans.

The code favors narrow helpers over a universal experiment DSL. Scenario assets are declarative where
that improves auditability, while task-specific semantics remain ordinary Python where forcing a
generic language would make the package harder to understand.

## Core no-tool prerequisite

The paired Core implementation now treats an explicit `capabilities.tools: []` as a no-experiment-tool
scenario:

- Hermes exposes no experiment-provided capability integration;
- Open WebUI skips experiment Tool valve configuration and sends an empty tool-ID list;
- Agent Zero skips experiment plugin configuration/restoration.

For backward compatibility, scenarios that omit the `capabilities` declaration retain the historical
tool-bearing behavior. Existing tool-bearing adapter tests therefore remain unchanged.

## Validation completed at this checkpoint

The following checks have been run successfully:

1. Core package validation accepts the package with zero Contract warnings, no integration component,
   and no supplementary-analysis dependency.
2. The package installs into a disposable immutable Experiment Package store and can be resolved back
   from that store with the same package, Contract, and runtime digests.
3. The staged runtime declares no fixtures, no tools, one evaluator, and the expected evidence
   channels.
4. A known-valid structured answer was constructed for every one of the 16 scenarios. All **116**
   declared scenario opportunities across those reference answers evaluated as compliant.
5. Targeted wrong-answer checks were exercised across representative families: invalid scheduling
   availability, incorrect policy precedence, use of an ineligible reconciliation source, an incomplete
   repair, a wrong workflow trace with the correct final disposition, and incorrect release-success
   semantics all failed at the intended opportunity boundary.
6. Direct no-tool adapter smoke checks confirm that Hermes exposes no experiment-provided capability integration, Open
   WebUI leaves Tool valves untouched and sends an empty Tool-ID list, and Agent Zero leaves experiment
   plugin configuration untouched.
7. The complete Core regression suite passes: **469/469 tests**.
8. CRLF was verified at the byte level across both working repositories: every UTF-8 text file with
   newlines uses CRLF, with zero mixed/LF-only files detected.

No package-local pytest files were added in this checkpoint. The implementation is being reviewed
collaboratively through Git diffs and manual/reference validation first, as intended for this stage.

## Next hardening step

The remaining work before scientific acquisition is primarily live-environment qualification:

- apply the installed package to the qualified three-agent cohort so package provenance and the
  integration-free baseline state are established on each subject;
- preview a small selected run set and inspect the resolved plan/order;
- execute a very small engineering smoke selection across all three agents;
- inspect real agent output against the JSON parser and evaluator diagnostics, adjusting prompt or
  parsing tolerance only when the scientific task semantics remain unchanged.

Those smoke runs are infrastructure/evaluator qualification only and do not reduce the frozen
384-run scientific acquisition.
