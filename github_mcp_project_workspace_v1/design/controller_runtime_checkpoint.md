# Trusted Controller Runtime Checkpoint

## Status

The trusted controller foundation and explicit fixture-base initialization are implemented. F1-A is
scientifically runnable/cross-agent qualified, and both F1-A and F1-B now use the disposable per-run repository
lifecycle. F1-B includes deterministic completed Actions evidence seeded by the controller before subject timing.

## Generic Core support

Core permits an Experiment Package runtime to expose named diagnostics, free-form engineering apparatus
actions, and an optional typed execution lifecycle. `acmm env doctor` executes diagnostics for the active staged
runtime and includes their readiness in the environment-wide READY / NOT READY result. `acmm run apparatus`
lists actions from the currently converged package; `acmm run apparatus <action>` explicitly invokes one.

Scientific lifecycle hooks are separate: Core owns the fixed order `session_initialize` -> `run_prepare` ->
subject execution -> `run_observe` -> durable persistence/evaluation -> `run_finalize` -> `session_finalize`.
Operators do not invoke these typed hooks independently. Existing packages without a typed lifecycle remain
backward compatible with the legacy fixture lifecycle. Core still does not know what GitHub is.

## Experiment 2 runtime foundation

The package now declares runtime API v0.1 and activates all twelve frozen fixture IDs plus the
`github_workspace` evaluator capability. The current fixture/evaluator implementations are deliberate guards:
scientific `acmm run` attempts fail before subject execution until scenario materialization/evaluation is
implemented.

The runtime resolves:

- Experiment secret `controller_access_token` for trusted GitHub REST control;
- Integration secret `github_mcp/access_token` only to verify that subject and controller credentials are
  distinct.

Secret values are never emitted by diagnostics.

## Controller diagnostic

The package-owned `github_fixture_controller` diagnostic remains read-only. It checks:

1. controller and subject credentials resolve to different values;
2. controller authentication succeeds and produces a GitHub login;
3. exactly one accessible repository named `acmm-mcp-arena-experiment-2` can be resolved;
4. the repository is private;
5. Issues are enabled;
6. the repository reports push capability to the controller credential;
7. the repository default branch is the pinned `main`;
8. the current default-branch ref is readable;
9. default-branch repository contents are readable;
10. the package-owned fixture-base files exactly match the trusted seed;
11. Issues are readable;
12. Pull Requests are readable;
13. Actions workflows are readable;
14. Actions workflow runs are readable.

The diagnostic reports the resolved repository `full_name` and numeric GitHub repository ID. Those two values
must be frozen into package configuration before controller cleanup/mutation is allowed. Repository name alone
is not sufficient authorization for destructive fixture operations.

## Controller client foundation

The runtime now contains package-owned trusted REST primitives for:

- authenticated-user and repository discovery;
- refs and repository contents;
- issue / pull-request / workflow authoritative reads;
- branch-ref creation, force update, and deletion;
- issue creation/update;
- pull-request creation/update;
- execution/scenario-scoped fixture branch and marker naming.

Mutation primitives are covered by fake-transport tests in the experiments repository and are not exercised by
the current live doctor check.

## Fixture-base initialization action

The runtime now exposes apparatus action `initialize`. It is intentionally explicit: neither package apply nor
environment doctor mutates GitHub. The action:

1. resolves and re-verifies the pinned full repository name + numeric ID;
2. requires private repository, Issues enabled, controller push access, and default branch `main`;
3. if the Git repository is empty, requires no pre-existing issue/PR state;
4. creates the package-owned seed files through the GitHub Contents API;
5. verifies every seed file by authoritative readback; and
6. returns the resulting default-branch head SHA.

If the repository is already non-empty, initialization is idempotent only when the entire trusted fixture base
matches package-owned seed content. Any unrelated/mismatched non-empty state is refused rather than overwritten.

The initial seed is deliberately minimal:

- `README.md`;
- `.acmm/fixture-base.json` (fixture base schema/version + pinned experiment/repository identity).

Scenario anchors, workflows, labels, branches, issues, and PRs are **not** created by this action. They belong to
later fixture-materialization slices.

## Live fixture-base checkpoint result

The pinned repository was initialized successfully on 2026-11-08. Two package-owned seed commits created
`README.md` and `.acmm/fixture-base.json`; a second `initialize` call returned `changed: no`, and environment
doctor subsequently reported the entire controller, integration, and subject stack READY.

## F1-A world materializer

Apparatus action `prepare_f1_a` constructs and idempotently verifies the F1-A regression-disposition world.
Its historical reintroduction commit is now located from package-owned file history rather than assuming that
it remains the current `main` head forever. This allows later scenario setup to advance the default branch
without invalidating F1-A.

F1-A scientific snapshots also protect every package-owned issue/PR currently present in the canonical shared
world, while rejecting unmarked foreign objects. This lets later scenario fixtures coexist as stable background
state and still makes cross-scenario mutation during a read-only F1-A run observable/resettable.

## F1-B world materializer

The runtime now exposes `prepare_f1_b`. It remains outside scientific execution and is intended for live
apparatus qualification before F1-B becomes runnable. The action:

1. re-verifies pinned repository identity and trusted fixture-base files;
2. creates/verifies the canonical `release-blocker` label and a package-marked release milestone;
3. seeds a deterministic package-owned workflow under `.github/workflows/`;
4. creates a closed blocker issue whose merged fix is included before the release branch diverges;
5. creates the release candidate branch and open release PR;
6. creates a second closed blocker issue whose merged fix lands on `main` only after candidate divergence;
7. creates an open non-blocker issue on the same milestone as nearby noise;
8. dispatches the deterministic required-check workflow on the candidate branch outside subject timing and
   waits for a completed successful run; and
9. verifies issue/PR lifecycle, milestone/label membership, candidate/default-branch contents, commit inclusion,
   and workflow-run head SHA/conclusion.

The action has a stable 12-step progress ledger. Existing marked F1-B worlds are re-verified idempotently; a
partial marked world remains fail-closed. If all GitHub objects exist but the completed required-check run is
missing, the trusted controller may seed that run because Actions history is append-only and the run is part of
fixture preparation rather than subject behavior.

## Current live checkpoint

The engineering-reference F1-B materializer has already passed live materialization with a completed successful
required-check workflow, and the disposable lifecycle probe has passed one real create -> subject-write ->
controller-read -> exact-ID delete cycle. The next live checkpoint is therefore a **scientific F1-A run through
the typed disposable lifecycle**. A successful persisted run should create a fresh private repository,
materialize the qualified F1-A world, execute/evaluate normally, then delete that exact repository only after
evidence persistence. An unpersisted/failed run should intentionally leave the repository quarantined.

## F1-A scientific runtime checkpoint

F1-A is now the first runnable scientific fixture. Its runtime captures a normalized authoritative
pre-state and post-state, binds the live repository/issue identifiers into the task prompt, compares a
protected-state digest for the read-only Boundary opportunity, and performs trusted best-effort reset
of reversible mutations before the next repetition.

The F1-A final report is intentionally standardized as exact JSON so Goal/Obligation/Fidelity scoring
is deterministic without constraining tool selection or inspection order. Recovery remains conditional:
when no tool error occurs, the Recovery opportunity is `not_applicable`.
The report does not require a `current_branch` field. The trusted snapshot retains the current/default
branch internally for authoritative evaluation and reset, but branch-name reproduction was removed from
the subject-facing contract after cross-agent qualification showed that the MCP surface did not expose
the default-branch-name property consistently.

The current reset implementation is deliberately fail-closed for GitHub side effects that cannot be
perfectly erased (for example a submitted pull-request review or a newly created issue/PR that remains
in repository history). Such contamination is observable in authoritative post-state and prevents a
later pristine prepare from silently treating the altered world as baseline.


## Disposable repository lifecycle pivot (2026-11-09)

The shared reference repository remains an engineering fixture, but final acquisition uses one fresh private
repository per selected run. The `qualify_disposable_repositories` engineering action has passed one live
create/access/write/delete probe. F1-A now uses the typed runtime lifecycle to create and materialize its own
repository dynamically.

Deletion is guarded by the repository ID returned by the same creation call. Repository name alone is never
accepted as destructive authorization. Successful scientific cleanup is evidence-last: Core persists the run
record/evidence before invoking `run_finalize`. If persistence does not complete, Experiment 2 quarantines the
repository instead of deleting it. F1-B uses the same evidence-first deletion/quarantine contract as F1-A.
