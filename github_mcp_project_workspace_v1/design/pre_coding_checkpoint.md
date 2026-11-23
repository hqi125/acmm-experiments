# Historical Pre-Coding Checkpoint

> **Historical record.** This document captures the Experiment 2 design immediately before runtime
> implementation. Some apparatus assumptions described here were later superseded by the GitHub App,
> exact 42-tool catalog, scenario-slice materialization, and Core Provider Gate used by the frozen
> scientific package. Current behavior is documented in the package manifest and the current design
> references linked from [`README.md`](README.md).

## Scientific shape that survived implementation

The pre-coding design had already fixed the core scientific structure that remained in the final package:

- three qualified agent subjects using the shared model baseline;
- six project-work families with two independently authored variants each;
- eight repetitions per scenario;
- **96 runs per agent and 288 scientific runs total**;
- one rich GitHub workspace capability environment shared across every scenario;
- route-independent terminal-state evaluation rather than a required golden tool sequence;
- authoritative trusted pre/post observation and explicit protected invariants;
- engineering qualification kept separate from scientific acquisition.

Those scientific decisions survived later apparatus refactoring.

## Early apparatus assumptions that were superseded

The earliest checkpoint assumed a PAT-oriented GitHub MCP setup and a 43-tool surface. That arrangement was
useful for integration qualification but was not the final scientific credential model.

The frozen package instead uses:

- a trusted controller secret (`controller_access_token`) for apparatus lifecycle/observation;
- a GitHub App private key (`github_app_private_key`) for minting short-lived installation tokens;
- one-repository subject authority during the active run;
- an exact 42-tool App-native catalog, excluding the user-identity-dependent `context/get_me` path;
- package-defined scenario-slice materialization rather than one long-lived shared laboratory repository;
- a Core-owned active-run Provider Gate plus package-defined GitHub action classification.

See [`capability_envelope.md`](capability_envelope.md),
[`pinned_mcp_catalog.md`](pinned_mcp_catalog.md), and
[`fixture_lifecycle.md`](fixture_lifecycle.md).

## Credential boundary

Even at the pre-coding stage, the design required a strict separation between trusted apparatus authority and
subject authority. The final implementation strengthened that rule: controller credentials and the App private
key remain harness-private; the subject receives only a fresh repository-scoped App installation token for the
active experiment repository.

Repository creation/deletion, fixture materialization, authoritative observation, App-installation assignment,
and cleanup are trusted apparatus work. They are not subject tools and are not counted as an agent's project-work
route.

## Fixture and isolation requirements

The design required deterministic fixtures and exact restoration/cleanup so one repetition could not silently
change another repetition's starting world. The final scenario-slice lifecycle implements that requirement with
trusted post-state capture followed by restoration/retirement:

- reversible run-owned state is normalized after evidence capture;
- explicitly allowed closed/unmerged history can become protected slice-owned evidence;
- non-restorable or ambiguous durable effects taint and retire the slice;
- exact repository identity is used for cleanup rather than broad name-based deletion.

CI-dependent scenarios use deterministic trusted setup so required Actions evidence exists before subject timing.

## Evaluation boundary

The scenario author controls goals, authority, acceptable terminal state, and genuine dependency constraints,
not the agent's route. Evaluators therefore test authoritative outcome/preservation predicates and observable
claims rather than matching one tool sequence.

The G/O/B/P/F/R mapping remains diagnostic: opportunities are nested within a run and do not inflate the number
of independent scientific samples.

## Transition out of the checkpoint

Implementation proceeded family-by-family, then through cross-agent smoke qualification, provider-control
hardening, scenario-slice lifecycle qualification, and the final pre-acquisition audit. The resulting frozen
package acquired the intended 288 scientific runs.

For the final state, use:

- [`../README.md`](../README.md) for the package overview;
- [`scenario_matrix.md`](scenario_matrix.md) for the frozen scenario set;
- [`fixture_lifecycle.md`](fixture_lifecycle.md) for current repository/credential lifecycle;
- [`github_api_control_plane.md`](github_api_control_plane.md) for provider-facing transport;
- [`design_progress.md`](design_progress.md) for the condensed chronology;
- [`../REPRODUCTION.md`](../REPRODUCTION.md) for public reproduction safety.
