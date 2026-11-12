# Scenario materialization lifecycle

## Purpose

Experiment 2 originally created and retired one private GitHub repository for every logical run. That gives a strong provider-enforced repository boundary, but it also creates a dense stream of repository lifecycle operations that can trigger opaque GitHub secondary rate limiting during long campaigns.

The campaign now declares `scenario_id` as its materialization grouping coordinate. Core freezes that grouping in the campaign manifest, executes one materialization slice at a time, and uses subject-major ordering inside each slice. The package remains responsible for what a materialization means and for every provider-specific resource action.

## Incremental qualification

This revision shares provider state for the complete **F1 family (F1-A and F1-B)**. F1-A covers repository branches, issues, pull requests, labels, comments, reviews, and relevant Git content. F1-B extends the same model to release labels, milestones, candidate history, and GitHub Actions history. The package creates one disposable repository when an F1 scenario materialization slice begins, reuses it across the selected runs in that scenario, mints and revokes a fresh repository-scoped GitHub App installation token for every run, restores the trusted baseline after every persisted run, and retires the repository when the slice ends.

All F2-F6 scenarios keep their existing disposable-per-run repository behavior in this revision. They are still scheduled inside scenario materialization slices, but the materialization hook returns a non-shared handle and their run lifecycle remains unchanged. This preserves the incremental qualification strategy while moving one complete fixture family at a time.

## Boundary and taint policy

Shared materialization does not pretend GitHub provides path- or object-level authorization inside a repository. The subject continues to receive the same 42-tool MCP surface and a repository-scoped installation token. Intra-repository scope is therefore an experimental boundary, not a provider-enforced access boundary.

For shared F1 scenarios, every run begins with a trusted baseline snapshot. After evidence is persisted, the package compares current protected state with that baseline. Reversible differences are restored from the trusted baseline. If the fixture reports any non-restorable difference, restoration failure, or other integrity uncertainty, the materialization is marked tainted, a forensic archive is persisted, the shared repository is retired, and execution stops rather than allowing later observations to inherit contaminated state.

A run whose evidence is not durably persisted also taints and retires the materialization. A materialization interrupted outside a clean completed boundary is archived and retired during materialization finalization.

## Scheduling invariant

Materialization controls only the outer scheduling locality. Core always orders runs subject-major inside a materialization slice. The package does not expose an arbitrary nested scheduling language.

For this package revision:

- outer materialization key: `scenario_id`;
- inner ordering: Core-defined subject-major ordering;
- shared provider resource qualification: F1-A and F1-B;
- F2-F6 repository lifecycle: unchanged disposable-per-run behavior.

This is an incremental apparatus revision. Historical campaigns retain their original per-run repository semantics and must not be resumed into this revision.
