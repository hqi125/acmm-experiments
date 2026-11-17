# Scenario materialization lifecycle

## Purpose

Experiment 2 no longer treats a logical scientific run as a GitHub repository lifetime. The original one-repository-per-run starter design was too provider-heavy and created avoidable repository lifecycle pressure. The current milestone instead lets the Experiment Package define an outer **materialization slice** and lets many logical runs execute inside that materialized workspace.

This package declares `scenario_id` as the materialization grouping coordinate. Core freezes those slices in the campaign plan, executes one slice at a time, and enforces **subject-major ordering inside every slice**. The package remains responsible for the provider-specific meaning of the slice and for trusted restoration/taint decisions.

## Scenario-slice repository contract

Every F1-F6 scenario materialization creates exactly one private disposable GitHub repository for the selected runs in that scenario slice. The repository is attached to the selected-repository GitHub App installation once for the slice. Every logical run still receives a fresh repository-scoped App installation token, and that token is revoked at the run boundary before trusted post-run observation. Agent Zero deliberately avoids a second per-run MCP settings rewrite after revocation; provider revocation is its authoritative between-run boundary, and the next admission replaces the dead credential before exact-catalog verification.

A run therefore has an isolated credential/admission window without requiring a new repository. `run_prepare()` fails closed if Core has not supplied the scenario materialization handle; there is intentionally no hidden one-repository-per-run fallback.

The package distinguishes **active fixture state** from **slice-owned historical residue**. In this design, `restored=true` means the declared shared-run invariant was re-established; it does **not** mean the provider-visible repository is byte-for-byte or history-for-history identical to its first materialized state:

- reversible branches, issue state, labels, comments, and other active fixture state are restored to the trusted baseline after each persisted run;
- a run-owned review PR may remain only as closed, unmerged provider history after its active branch has been retired;
- prior closed residue is included in the next run's authoritative pre-state and must remain unchanged;
- mutation of historical residue, unexpected durable provider objects, merge history, or any other non-restorable cross-run contamination taints the whole slice, triggers forensic archival, and retires the repository.

F5 and F6 restoration records therefore expose `restoration_semantics`, `pristine_equivalent`, and the explicit `slice_owned_pull_residue`. `pristine_equivalent=false` with `restored=true` is expected when a new closed/unmerged PR has become allowed append-only slice history. A truly pristine provider world is impossible on one reused GitHub repository once provider objects with non-erasable history have been created; obtaining that stronger invariant would require a fresh repository/world rather than restoration inside the shared slice.

F6-B has an additional run-local namespace because its task begins from an existing draft PR. The static scenario base is materialized once, while each logical run creates uniquely marked repair/unrelated branches, issue, PRs, and failed validation evidence **inside the same scenario repository**. Those run-owned active objects are retired after post-state capture; their closed history becomes slice-owned residue.

For F6, trusted restoration is deliberately **post-observation normalization**, not a substitute for Boundary measurement. A subject may, for example, create an F6-A PR against the wrong base or directly mutate a protected ref; the authoritative post-state must preserve that breach first. Trusted restoration then repairs provider-mutable metadata (PR base/title/body/state, issue/label/comment state, refs) before the next run. Submitted review history, merges, unexpected durable provider objects, new Actions history, or another effect that cannot be deterministically reversed remain hard-taint conditions. Historical slice-owned PRs are also protected: reversible comments/review comments/pending reviews are removed, while irreversible submitted reviews or later draft/ready drift taint the slice rather than leaking into a future pre-state.

## Publication phases

Materializer boundaries do not imply Git publication barriers. A newly created scenario repository opens one initial publication phase containing the trusted fixture base and every scenario-owned commit that does not depend on remote-visible history. Dirty refs are flushed once. Later pushes exist only when the fixture topology genuinely requires an already-published ref/history state.

Current semantic publication shape:

- F5-A: one initial push;
- F5-B: one initial push;
- F6-A: one initial-main push plus the required release-branch topology publication;
- F6-B: one static initial-main push; run-scoped repair/unrelated branch publication occurs only when that run's in-repository fixture is created.

## Boundary and taint policy

Scenario sharing does not pretend GitHub offers path-level authorization. The subject still receives the full qualified 42-tool repository-scoped MCP surface. Isolation is established by trusted pre/post evidence, run-local namespaces, fresh per-run credentials, restoration, and hard taint on contamination.

For engineering validation, Core may pass `--capture-environment-snapshots`. Experiment 2 then writes full GitHub repository diagnostic archives immediately after trusted run preparation and again after trusted restoration. These archives include repository metadata, branches, labels, issues/comments, pull requests/reviews/comments, default-branch commits, workflows/runs, and source archives for each branch. Snapshot collection is fully inside the trusted provider-traffic control plane: REST discovery requests, the initial archive endpoint, and credential-free redirect downloads are all serialized/admitted by the same governor/Core Provider Gate, with `traffic_purpose=diagnostic_snapshot` metadata so the injected validation workload remains distinguishable in gate telemetry. This switch is **off by default** because snapshot collection itself adds trusted GitHub API/archive traffic and can perturb the provider-pressure profile; it is intended for restoration validation/debugging, not final scientific acquisition. The ordinary `final_environment_state` evidence remains the authoritative pre-restoration scientific post-state.

A run whose evidence is not durably persisted taints and retires the slice. A materialization interrupted outside a clean boundary is archived and retired. A completed clean slice is detached from the App installation and deleted exactly once during materialization finalization.

## Scheduling invariant

Materialization controls the outer locality only:

- package-defined outer key: `scenario_id` for this experiment;
- one materialized repository may span many selected runs;
- Core-defined inner order: subject-major within the slice;
- the package does not define arbitrary nested scheduling;
- no repository shard/pool is part of the current scientific lifecycle.

This slice-first lifecycle is the scalability milestone. Historical one-repository-per-run and prepared-isolated/shard implementations are superseded and must not be reintroduced as fallback execution paths.
