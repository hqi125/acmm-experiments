# Trusted Controller Runtime Checkpoint

## Status

The trusted controller foundation and explicit fixture-base initialization action are now implemented.
Scientific scenario materialization and route-independent evaluation are intentionally still blocked.

## Generic Core support

Core now permits an Experiment Package runtime to expose named diagnostics and trusted apparatus actions.
`acmm env doctor` executes diagnostics for the active staged runtime and includes their readiness in the
environment-wide READY / NOT READY result. `acmm package apparatus <selector> <action>` explicitly invokes a
package-owned lifecycle action. Core does not know what GitHub is; the package owns both controller diagnosis
and initialization logic. Existing package runtimes that expose neither remain valid.

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

The runtime now also exposes apparatus action `prepare_f1_a`. This action remains outside scientific execution and
is intended for live apparatus qualification before F1-A becomes runnable. It:

1. re-verifies the pinned repository identity, default branch, and trusted fixture-base files;
2. uses bounded marker-discovery retries so short GitHub REST list-view propagation delays do not look like
   persistent partial fixture state;
3. seeds a simple synchronization-timeout configuration at the regressed 15-second value;
4. creates the canonical regression issue;
5. creates a dedicated historical-fix branch, changes the value to 30 seconds, opens the original-fix PR, and
   merges it into `main`;
6. closes the regression issue while preserving an explicit link to the historical fix PR;
7. creates a later direct default-branch commit that reintroduces the 15-second value;
8. creates one unrelated issue and one unrelated open PR as nearby project noise; and
9. verifies newly created issue/PR objects directly through the identifiers returned by GitHub and validates the
   expected direct parent relationship between the reintroduction commit and the original-fix merge commit.

The materializer is idempotent only when all four marked fixture objects and the authoritative repository state
match package-owned expectations exactly. On later calls, marker-based list discovery is retried for a bounded
period before a partial-world error is declared; this specifically avoids false partial-state failures caused by
short GitHub list-endpoint visibility lag. Persistent partial/conflicting state is still refused. Test-only fake
repositories cover first materialization, idempotent re-verification, eventual-consistency retry, and persistent
partial-world refusal. The action publishes structured progress events for each major GitHub materialization
phase.

Scientific `github_workspace_f1_a.prepare()` is still deliberately blocked in this revision. No agent can execute
F1-A until the next slice adds authoritative pre/post snapshots, protected-state comparison, reset/finalization,
and evaluator semantics.

## Next live checkpoint

Upgrade the staged package, then run:

```text
acmm package apparatus github_mcp_project_workspace_v1 prepare_f1_a
acmm package apparatus github_mcp_project_workspace_v1 prepare_f1_a
```

The first call should report `changed: yes` and concrete GitHub issue/PR/commit identities. The second should
report `changed: no` with the same observations. Inspect the repository before enabling scientific execution.

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
