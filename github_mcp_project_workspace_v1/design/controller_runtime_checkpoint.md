# Trusted Controller Runtime Checkpoint

## Status

The trusted controller foundation is now implemented as the second executable apparatus slice.
Scientific fixture materialization and route-independent evaluation are intentionally still blocked.

## Generic Core support

Core now permits an Experiment Package runtime to expose named diagnostics. `acmm env doctor` executes
those diagnostics for the active staged runtime and includes their readiness in the environment-wide READY /
NOT READY result. Core does not know what GitHub is; the package owns the controller diagnostic logic.

Existing package runtimes that expose no diagnostics remain valid.

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

The package-owned `github_fixture_controller` diagnostic is read-only in this revision. It checks:

1. controller and subject credentials resolve to different values;
2. controller authentication succeeds and produces a GitHub login;
3. exactly one accessible repository named `acmm-mcp-arena-experiment-2` can be resolved;
4. the repository is private;
5. Issues are enabled;
6. the repository reports push capability to the controller credential;
7. the current default-branch ref is readable;
8. default-branch repository contents are readable;
9. Issues are readable;
10. Pull Requests are readable;
11. Actions workflows are readable;
12. Actions workflow runs are readable.

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

## Next live checkpoint

Upgrade the staged package to this revision and run:

```text
acmm env doctor --start-if-needed
```

Do not create fixture state manually. Capture the `github_fixture_controller` diagnostic output, especially:

- authenticated controller login;
- resolved repository full name;
- numeric repository ID;
- all read-surface checks.

After those identifiers are reviewed and pinned, the next implementation slice may safely add fixture
materialization/reset and exercise controlled mutation against the dedicated repository.
