# GitHub MCP Project Workspace - Design Notes

This directory is the frozen design, apparatus, and implementation record for
`github_mcp_project_workspace_v1`. The experiment was designed documentation-first because capability
availability, fixture state, credential scope, provider behavior, and route-independent evaluation are
part of the scientific apparatus rather than incidental implementation details.

All twelve F1-A through F6-B scenarios were implemented and qualified before the 288-run scientific
acquisition. Documents that describe earlier checkpoints are retained as historical records and are
labeled accordingly; current behavior is defined by the frozen package revision and the current lifecycle,
control-plane, and evaluation documents.

## Current design references

- [`capability_envelope.md`](capability_envelope.md) - fixed GitHub MCP toolset envelope,
  capability/credential/scenario boundaries, laboratory protection, and provenance rules.
- [`pinned_mcp_catalog.md`](pinned_mcp_catalog.md) - frozen v2.1.0 upstream + maintained ACMM source
  identity, exact selected-toolset catalog, exclusions, and effective-catalog digest.
- [`fixture_lifecycle.md`](fixture_lifecycle.md) - scenario-slice repository lifecycle, subject/controller
  credential separation, taint/retirement containment, CI seeding, restoration, and run isolation.
- [`materialization_lifecycle.md`](materialization_lifecycle.md) - package-defined scenario materialization
  and reusable-slice rules.
- [`github_api_control_plane.md`](github_api_control_plane.md) - provider-facing REST/MCP/Git transport,
  telemetry, pacing, recovery, and content/history plane.
- [`provider_pressure_heuristics.md`](provider_pressure_heuristics.md) - Event-PPH and Adaptive Pressure
  Pocket (APP) model used by Experiment 2.
- [`provider_rate_policy_sources.md`](provider_rate_policy_sources.md) - authoritative GitHub sources and
  ACMM operating margins for rate/pacing defaults.
- [`scenario_architecture.md`](scenario_architecture.md) - common authoring philosophy, difficulty model,
  A/B independence, and route-choice principles.
- [`scenario_matrix.md`](scenario_matrix.md) - frozen twelve-scenario matrix and cross-family progression.
- [`evaluation_model.md`](evaluation_model.md) - authoritative state, acceptable terminal-state predicates,
  protected invariants, procedure constraints, and trajectory analysis.

## Scenario-family records

- [`f1_project_orientation.md`](f1_project_orientation.md) - F1-A/F1-B project-orientation designs.
- [`f2_triage_bounded_action.md`](f2_triage_bounded_action.md) - F2-A/F2-B triage and bounded-action designs.
- [`f3_cross_artifact_reconciliation.md`](f3_cross_artifact_reconciliation.md) - F3-A/F3-B cross-artifact
  reconciliation designs.
- [`f4_ci_diagnosis.md`](f4_ci_diagnosis.md) - F4-A/F4-B CI-diagnosis designs.
- [`f5_controlled_implementation.md`](f5_controlled_implementation.md) - F5-A/F5-B controlled-implementation
  designs.
- [`f6_multi_stage_resolution.md`](f6_multi_stage_resolution.md) - F6-A/F6-B multi-stage resolution designs.

## Historical checkpoints

- [`controller_runtime_checkpoint.md`](controller_runtime_checkpoint.md) - historical trusted-controller
  runtime checkpoint; later lifecycle documents supersede its earlier PAT/per-run assumptions where noted.
- [`pre_coding_checkpoint.md`](pre_coding_checkpoint.md) - concise historical snapshot of the design before
  runtime implementation and later GitHub App/scenario-slice refinements.
- [`pre_acquisition_audit.md`](pre_acquisition_audit.md) - final scientific/conformance audit performed
  before the long Campaign acquisition.
- [`design_progress.md`](design_progress.md) - condensed chronology from the initial tool-rich concept through
  final acquisition freeze.

## Design-to-implementation convention

Each A/B pair follows the same scientific pattern:

1. State the real project-work construct being sampled.
2. Define two scenarios sharing that construct without sharing one surface template or one required route.
3. Specify the dedicated GitHub fixture and authoritative pre-state.
4. Write the user-facing goal and authorization boundary without naming a preferred tool sequence.
5. Enumerate acceptable terminal-state predicates and protected invariants.
6. Add only procedure constraints corresponding to real task dependencies or explicit user intent.
7. Identify multiple plausible valid routes without attempting exhaustive path enumeration.
8. Establish deterministic restoration/cleanup and repeated-run isolation.
9. Identify expected failure modes, confounds, and useful trajectory descriptors.
10. Calibrate A/B difficulty and freeze scientific semantics before acquisition.

The evaluator must not make one route valid merely because it matches the author's preferred sequence.
If two routes produce the same authorized correct state while respecting every invariant, both are valid.

## ACMM philosophy

G/O/B/P/F/R opportunities arise from observable project work rather than quota engineering. Rich tool
availability is not itself a Boundary opportunity; a Boundary opportunity exists when the scenario
authorizes some actions and protects or forbids others. Procedure measures genuine dependency/order
requirements, not stylistic preferences about which GitHub tool should be called first.

Recovery arises primarily from genuine agent mistakes, stale assumptions, rejected mutations, or state
changes encountered during normal work. The study does not inject arbitrary MCP failures merely to create
Recovery counts.
