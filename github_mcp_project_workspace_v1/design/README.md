# GitHub MCP Project Workspace - Design Notes

This directory is the living design record for `github_mcp_project_workspace_v1` before executable
package implementation begins. The experiment is deliberately being designed in documentation first
because tool availability, fixture state, and route-independent evaluation determine the scientific
tone of the study.

## Documents

- [`capability_envelope.md`](capability_envelope.md) - fixed GitHub MCP toolset envelope, the
  capability/credential/scenario boundary distinction, laboratory protection, and provenance rules.
- [`pinned_mcp_catalog.md`](pinned_mcp_catalog.md) - frozen v2.0.3 image/digest, exact selected-toolset
  catalog expectation, laboratory exclusions, and effective-catalog digest.
- [`controller_runtime_checkpoint.md`](controller_runtime_checkpoint.md) - implemented trusted-controller
  runtime/doctor foundation and the repository-identity pinning gate before mutation;
- [`fixture_lifecycle.md`](fixture_lifecycle.md) - frozen single-repository fixture model, subject/controller
  credential separation, merge containment, CI seeding, and run isolation.
- [`scenario_architecture.md`](scenario_architecture.md) - common authoring philosophy, difficulty
  model, A/B independence requirements, and route-choice principles.
- [`scenario_matrix.md`](scenario_matrix.md) - current twelve-scenario working matrix and the
  cross-family progression from orientation to multi-stage project resolution.
- [`evaluation_model.md`](evaluation_model.md) - authoritative state, acceptable terminal-state
  predicates, protected invariants, partial-order procedure constraints, and trajectory analysis.
- [`f1_project_orientation.md`](f1_project_orientation.md) - frozen F1-A/F1-B orientation designs.
- [`f2_triage_bounded_action.md`](f2_triage_bounded_action.md) - frozen F2-A/F2-B triage and bounded-action designs.
- [`f3_cross_artifact_reconciliation.md`](f3_cross_artifact_reconciliation.md) - frozen F3-A/F3-B cross-artifact reconciliation designs.
- [`f4_ci_diagnosis.md`](f4_ci_diagnosis.md) - frozen F4-A/F4-B CI-diagnosis designs.
- [`f5_controlled_implementation.md`](f5_controlled_implementation.md) - frozen F5-A/F5-B controlled-implementation designs.
- [`f6_multi_stage_resolution.md`](f6_multi_stage_resolution.md) - frozen F6-A/F6-B multi-stage resolution designs.
- [`pre_coding_checkpoint.md`](pre_coding_checkpoint.md) - frozen scenario-set implications for credentials, fixture lifecycle, CI evidence, scale, and the explicit implementation gate.
- [`design_progress.md`](design_progress.md) - design ledger, open decisions, and the explicit
  pre-coding gate.

## Design-to-implementation convention

Each A/B pair should move through the same sequence:

1. State the real project-work construct being sampled.
2. Define two scenarios that share that construct without sharing one surface template or route.
3. Specify the dedicated GitHub fixture and authoritative pre-state.
4. Write the user-facing goal and authorization boundary without naming a preferred tool sequence.
5. Enumerate acceptable terminal-state predicates and protected invariants.
6. Add only procedure constraints that correspond to real task dependencies or explicit user intent.
7. Identify multiple plausible valid routes without attempting exhaustive path enumeration.
8. Establish deterministic reset/cleanup and repeated-run isolation.
9. Identify expected failure modes, confounds, and useful trajectory descriptors.
10. Calibrate A/B difficulty and freeze the design before creating runtime/scenario code.

The experiment should never make one route valid merely because it matches the evaluator author's
preferred sequence. If two routes produce the same authorized correct state while respecting every
invariant, both should be accepted.

## ACMM philosophy

G/O/B/P/F/R opportunities should arise from observable project work rather than be quota-engineered.
Rich tool availability is not itself a Boundary opportunity; a Boundary opportunity exists when the
scenario authorizes some actions and forbids or protects others. Likewise, Procedure should measure
true dependency/order requirements, not stylistic preferences about which GitHub tool should be
called first.

Recovery should primarily arise from genuine agent mistakes, stale assumptions, rejected mutations,
or state changes encountered during normal work. The design should not inject arbitrary MCP failures
merely to increase Recovery counts.
