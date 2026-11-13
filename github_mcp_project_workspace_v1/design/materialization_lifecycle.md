# Scenario materialization lifecycle

## Purpose

Experiment 2 originally created and retired one private GitHub repository for every logical run. That gives a strong provider-enforced repository boundary, but it also creates a dense stream of repository lifecycle operations that can trigger opaque GitHub secondary rate limiting during long campaigns.

The campaign now declares `scenario_id` as its materialization grouping coordinate. Core freezes that grouping in the campaign manifest, executes one materialization slice at a time, and uses subject-major ordering inside each slice. The package remains responsible for what a materialization means and for every provider-specific resource action.

## Incremental qualification

This revision shares provider state for the complete **F1-F4 families**. F1-A covers repository branches, issues, pull requests, labels, comments, reviews, and relevant Git content. F1-B extends the same model to release labels, milestones, candidate history, and GitHub Actions history. F2-A adds a bounded-mutation case: the subject may legitimately close/relabel/comment on the incoming issue, after which the package restores the exact pristine triage state before another observation. F2-B adds the deliberate no-op case and proves that accidental issue metadata/comment drift is likewise restored. F3-A/F3-B add cross-artifact reconciliation where the authorized correction is confined to issue record state and comments; the controller restores that state while treating unauthorized Git/PR/provider-history mutation as taint. F4-A/F4-B add stable completed Actions evidence: authorized diagnosis/alert comments and issue-state changes are restored, while any new workflow execution is non-restorable taint. The package creates one disposable repository when a qualified scenario materialization slice begins, reuses it across the selected runs in that scenario, mints and revokes a fresh repository-scoped GitHub App installation token for every run, restores the trusted baseline after every persisted run, and retires the repository when the slice ends.

F5-A/F5-B and F6-A/F6-B intentionally retain disposable-per-run repositories. Their successful terminal states create new Git commits and/or pull-request history (and F6-B advances an existing PR head), so exact provider-history restoration is not available even if visible refs can be force-reset. Keeping these scenarios run-isolated preserves repetition independence rather than weakening the taint definition merely to increase sharing.

## Boundary and taint policy

Shared materialization does not pretend GitHub provides path- or object-level authorization inside a repository. The subject continues to receive the same 42-tool MCP surface and a repository-scoped installation token. Intra-repository scope is therefore an experimental boundary, not a provider-enforced access boundary.

For shared F1-F4 scenarios, every run begins with a trusted baseline snapshot. After evidence is persisted, the package compares current protected state with that baseline. Reversible differences are restored from the trusted baseline. If the fixture reports any non-restorable difference, restoration failure, or other integrity uncertainty, the materialization is marked tainted, a forensic archive is persisted, the shared repository is retired, and execution stops rather than allowing later observations to inherit contaminated state.

A run whose evidence is not durably persisted also taints and retires the materialization. A materialization interrupted outside a clean completed boundary is archived and retired during materialization finalization.

## Scheduling invariant

Materialization controls only the outer scheduling locality. Core always orders runs subject-major inside a materialization slice. The package does not expose an arbitrary nested scheduling language.

For this package revision:

- outer materialization key: `scenario_id`;
- inner ordering: Core-defined subject-major ordering;
- shared provider resource qualification: F1-A, F1-B, F2-A, F2-B, F3-A, F3-B, F4-A, and F4-B;
- run-isolated by design: F5-A, F5-B, F6-A, and F6-B because successful observations necessarily create durable provider history.

This is an incremental apparatus revision. Historical campaigns retain their original per-run repository semantics and must not be resumed into this revision.
