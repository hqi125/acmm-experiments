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

## Next live checkpoint

Upgrade the staged package, then run:

```text
acmm package apparatus github_mcp_project_workspace_v1 initialize
acmm env doctor --start-if-needed
```

The first command is the first controlled mutation performed by the trusted controller. Expected outcome: two
package-owned seed files initialize `main`. A second identical initialize command should be idempotent (`changed:
no`). Doctor should then report `repository_initialized`, `default_branch_read`, `repository_contents_read`, and
`fixture_base_integrity` as READY. Scientific fixtures remain hard-blocked until F1-A materialization is implemented.
