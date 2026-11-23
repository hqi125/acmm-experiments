# Experiment 2 Design and Implementation Chronology

This file is a historical ledger, not an active checklist. It records the major decisions that produced
the frozen `github_mcp_project_workspace_v1` package. Current behavior is defined by the package manifest,
Contract, runtime, and the current design references linked from [`README.md`](README.md).

## 1. Separate engineering qualification from scientific acquisition

The first decision was to keep GitHub MCP integration qualification separate from the scientific study.
`github_mcp_integration_qualification_v1` established native MCP discovery/execution, trusted observation,
and cross-agent interoperability. Its smoke workflow remained engineering evidence rather than becoming a
scientific scenario.

Experiment 2 therefore began with a cleaner research question: give every subject the same rich GitHub
workspace and measure how the agent selects, composes, verifies, and recovers while performing realistic
project work.

## 2. Freeze the scientific shape before scaling apparatus work

The scenario program converged on six task families with two independently authored variants each:
F1 project orientation, F2 triage/bounded action, F3 cross-artifact reconciliation, F4 CI diagnosis,
F5 controlled implementation, and F6 multi-stage resolution.

The final scientific scale was fixed at **3 agents x 12 scenarios x 8 repetitions = 288 runs**. Engineering
smokes and qualification executions remained outside that count. The experiment retained route-independent
terminal-state evaluation and treated tool traces as behavioral evidence rather than a golden sequence.

## 3. Move from the early PAT/43-tool prototype to App-native authority

Early engineering checkpoints used a PAT-oriented 43-tool GitHub MCP surface. Qualification showed that a
GitHub App provided a stronger subject-authority boundary. The final scientific design therefore moved to:

- a trusted controller credential kept outside the subject boundary;
- a package-owned GitHub App private key used to mint short-lived installation tokens;
- a fresh token narrowed to the active repository for each subject run;
- an exact **42-tool** App-native capability surface;
- deliberate exclusion of the `context/get_me` identity path because it requires a user credential.

The frozen toolset/catalog and source provenance are recorded in
[`pinned_mcp_catalog.md`](pinned_mcp_catalog.md) and [`capability_envelope.md`](capability_envelope.md).

## 4. Replace one-repository-per-run with scenario-slice materialization

The original disposable-repository design created one remote repository per logical run. That topology was
scientifically clean but provider-heavy. The final lifecycle instead lets the package group materialization
by `scenario_id`: one private repository spans many logical runs for the same scenario while Core preserves
subject-major ordering inside the slice.

Trusted post-state is captured before restoration. Reversible run-owned state is normalized/retired between
runs; explicitly allowed closed/unmerged history may become protected slice-owned evidence. Unexpected durable
provider effects or restoration uncertainty taint and retire the slice rather than contaminating a later run.

See [`fixture_lifecycle.md`](fixture_lifecycle.md) and
[`materialization_lifecycle.md`](materialization_lifecycle.md).

## 5. Reduce trusted provider traffic and centralize transport behavior

Live F4/F6 engineering profiles showed that repository creation and Contents-API traffic would dominate a
long campaign if left unoptimized. The apparatus consequently introduced a Git content/history plane for
trusted file/ref work, preserved REST for collaboration/control surfaces, and made Git transport separately
observable.

Fixture publication was also batched so static scenario content can be composed before the first necessary
remote-visible barrier. Provider interactions enter shared transport/control layers instead of accumulating
scenario-local HTTP clients, retry loops, or sleeps.

See [`github_api_control_plane.md`](github_api_control_plane.md).

## 6. Introduce one active-run Provider Gate

Experiment 2 evolved from local pacing into a Core-owned Provider Gate covering participating subject MCP,
trusted controller/App, and Git smart-protocol actions during an active logical run. The final architecture
keeps three concepts distinct:

- **Event-PPH** learns feature/event pressure and actuates admission without episode semantics;
- **APP** models local pressure pockets and burst/probe behavior;
- **provider-directed recovery** remains authoritative when GitHub supplies a longer wait/reset signal.

Local MCP/Git governor pacing is fallback-only when the Core gate is active, avoiding stacked sleeps. Sourced
cold-start intervals and recovery rules are documented in
[`provider_rate_policy_sources.md`](provider_rate_policy_sources.md), with the adaptive model in
[`provider_pressure_heuristics.md`](provider_pressure_heuristics.md).

## 7. Qualify all six families and harden failure containment

F1-F6 engineering work progressively exercised read-only reasoning, bounded metadata mutation, cross-artifact
reconciliation, Actions evidence, code changes, PR creation, existing-PR repair, and release-targeted work.

Qualification exposed and corrected apparatus issues such as provider-auth refresh, bounded retry, materializer
timeouts, exact cleanup, run-scoped authority, scenario-slice restoration, and transport telemetry. The final
lifecycle records invalid/preparation failures without silently promoting them into scientific observations and
retires provider state when exact continuation safety cannot be established.

## 8. Freeze package semantics before the scientific Campaign

The pre-acquisition audit checked the complete twelve-scenario Contract, capability surface, fixture/evaluator
semantics, provider-control path, and campaign lifecycle. Scientific acquisition then used one immutable
installed package revision. Changes to prompts, evaluator predicates, provider-pressure feature definitions,
capability envelope, or other scientific semantics require a new package revision and a new scientific lineage.

See [`pre_acquisition_audit.md`](pre_acquisition_audit.md).

## 9. Acquisition completion

The frozen design was executed at the intended scale: **288/288 scientific runs were observed**. Post-acquisition
adjudication and merge were handled through Core's separate adjudication/merge workflow rather than by mutating
this package source. The package remains the reproducible scientific contract/apparatus record; analysis outputs
and execution artifacts belong outside the source tree.

## What remains stable for reproduction

A reproduction should preserve the twelve scenarios, eight repetitions, three qualified subjects, exact
capability/evaluation semantics, and provider-control model unless it intentionally defines a new study. Public
reproduction should use its own dedicated GitHub apparatus; changing concrete account/App/repository identity
therefore produces a new package revision while preserving the scientific design.

See [`../REPRODUCTION.md`](../REPRODUCTION.md) for the public execution boundary.
