# Fixture Lifecycle and Isolation Strategy

## Current strategy: one materialized scenario workspace, many logical runs

Experiment 2 uses package-declared scenario slices. For each selected scenario slice, trusted apparatus creates one private disposable GitHub repository, materializes the scenario blueprint, verifies the authoritative baseline, and then reuses that repository for the selected logical runs in Core's subject-major order. The engineering reference repository remains diagnostic-only and is never the scientific workspace.

The subject credential model remains per-run:

1. the trusted controller credential owns repository lifecycle, fixture construction, authoritative observation, restoration, App-installation assignment, and retirement;
2. each scientific run receives a freshly minted GitHub App installation token narrowed to the scenario repository;
3. Core binds that token only for the run's subject execution window and the package ends its usable authority before trusted post-run observation. Hermes and Open WebUI restore the local sentinel before provider revocation; Agent Zero uses provider token revocation as the per-run boundary so its asynchronous MCP settings refresh cannot race the next run.
4. Agent Zero starts with no GitHub MCP server configured, may retain the already-revoked token string in live settings between logical runs, and has the server removed again at subject release; each next admission replaces the run token once and verifies the exact 42-tool catalog.

Repository creation/deletion is absent from the subject MCP catalog.

## Package-owned scenario blueprints

The Experiment Package remains the source of truth for repository settings, files, commit ancestry, branches, issues, pull requests, labels, workflows, deterministic Actions evidence, aliases, and invariants. The package constructs the remote world; a persistent template repository is not scientific source of truth.

Initial Git publication is minimized independently of Python materializer boundaries. Fixture-base and scenario-owned commits that do not depend on remote-visible history are committed locally and flushed in one publication phase. Additional publication barriers are allowed only when branch/history topology genuinely depends on an already-published ref.

## Run lifecycle inside a slice

For each scenario materialization:

1. create one private repository and record its numeric ID in the execution-local resource ledger;
2. materialize and verify the static scenario base once;
3. attach that exact repository to the selected-repository App installation;
4. for each logical run in Core's subject-major order, construct any run-scoped in-repository fixture required by the scenario, verify authoritative pre-state, mint a fresh exact-repository token, and admit the subject;
5. execute the subject, then end the run-scoped subject authority before any trusted post-run observation;
6. capture authoritative post-state and durably persist the run evidence;
7. restore reversible active state and retire run-owned active refs/objects;
8. preserve only explicitly allowed closed/unmerged slice-owned history; any mutation to prior residue or unexpected non-restorable state taints, archives, and retires the slice;
9. after the last selected run, restore the static unadmitted subject state during subject release (sentinel for Hermes/Open WebUI; no GitHub MCP server for Agent Zero), then detach and delete the scenario repository exactly once.

F1-F4 restore their qualified active fixture state directly. F5 permits a run-owned review PR to remain as closed/unmerged historical residue while deleting/resetting active branches and restoring protected state. F6-A applies the same rule around its release-blocker repair handoff. F6-B creates a fresh run-scoped draft-repair world inside the same repository and closes/deactivates those run-owned objects after evidence capture.

## Visibility and contamination

Closed historical GitHub objects are provider-visible and therefore are not ignored. They are captured in every subsequent run's pre-state. Evaluators score the current run from pre-to-post deltas rather than global object counts, and restoration requires older historical rows to remain unchanged. The model therefore acknowledges unavoidable append-only provider history without allowing it to become active cross-run contamination. Accordingly, trusted **restoration** means active-state equivalence plus explicitly permitted immutable history; it is deliberately not called Recovery, and it is not synonymous with provider-world pristine equivalence.

`--capture-environment-snapshots` is a diagnostic validation mode. When enabled, the package captures a full repository archive after run preparation and another after restoration. Comparing those archives, together with the normal `final_environment_state` evidence captured before restoration, provides a three-point audit of the run invariant. Snapshot traffic is additional trusted apparatus traffic and is fully admitted through the provider traffic-control plane, including credential-free archive redirect downloads; it is tagged as diagnostic snapshot traffic in gate metadata. The mode stays disabled for final measurements unless the experiment intentionally accepts that perturbation.

## Interruption and recovery

The ledger records the one scenario repository identity and App attachment state. On interruption or restoration uncertainty, the package writes a forensic archive before exact-ID deletion. Recovery never fabricates a replacement per-run repository; the failed slice is retired and a later execution begins a new materialization.

## Scheduling

The package chooses the outer slice via `campaign.materialization.group_by`; this experiment uses `scenario_id`. Core enforces subject-major ordering underneath the materialization. There is no prepared-isolated shard scheduler in the current milestone.
