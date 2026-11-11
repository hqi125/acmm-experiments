# Pre-Coding Checkpoint

> **Historical checkpoint:** this document records the earlier PAT/43-tool apparatus state. The current package uses per-run repository-scoped GitHub App installation tokens and the 42-tool App-native catalog; see `fixture_lifecycle.md` and `pinned_mcp_catalog.md`.

## Status

**Pre-coding gate closed on 2026-11-07; executable implementation has started.**

All twelve scenarios and the apparatus architecture remain frozen. The user confirmed the dedicated repository
`acmm-mcp-arena-experiment-2`, removed the obsolete qualification smoke issue, created both dedicated PATs,
and the transition to coding was explicitly announced. Apparatus slice 1 now contains the package manifest,
contract, and pinned MCP integration; fixture runtime/evaluator implementation follows after live binding/preflight.

## Frozen scientific shape

- experiment: `github_mcp_project_workspace_v1`;
- subjects: Hermes, Open WebUI, Agent Zero under the same qualified LLM baseline;
- fixed visible toolsets: `context`, `repos`, `issues`, `pull_requests`, `users`, `actions`, `git`, `labels`;
- scenarios: 6 families x 2 independently authored variants = 12;
- repetitions: 8 per scenario per agent;
- planned acquisition: 96 runs/agent, 288 total;
- primary evaluation: authoritative state + invariants + final claims;
- trajectory evidence: explanatory/diagnostic, not a golden-sequence matcher.

## Frozen MCP build and catalog

Reuse the already-qualified server:

- `ghcr.io/github/github-mcp-server:v2.0.3`;
- qualified observed digest `sha256:250bc6ce70788207608ef74cef4397230ff2e8481218da74d6093e4bd9101132`;
- upstream immutable release commit `b98d115`.

The eight toolsets contain an expected 52 unique v2.0.3 tools before laboratory exclusions. The frozen
excluded tools are:

```text
actions_run_trigger
create_repository
delete_repository
fork_repository
get_team_members
get_teams
list_issue_fields
list_issue_types
ui_get
```

The resulting expected scientific surface contains 43 unique tools with normalized catalog digest:

```text
sha256:d1474fb4709fc2d4d18821711f098582e30a712a08f718ee89487309ba6a818d
```

`merge_pull_request` intentionally remains visible. Full membership/rationale is in
[`pinned_mcp_catalog.md`](pinned_mcp_catalog.md).

## Frozen credential model

Use **two selected-repository fine-grained PATs** against the dedicated laboratory repository.

### Subject MCP credential

| Permission | Level |
| --- | --- |
| Metadata | Read |
| Contents | Read/write |
| Issues | Read/write |
| Pull requests | Read/write |
| Actions | Read |
| Commit statuses | Read |

GitHub fine-grained PATs do not expose a separate Checks permission. No Actions write, Workflows write, Administration, or Repository creation.

### Trusted controller credential

| Permission | Level |
| --- | --- |
| Metadata | Read |
| Contents | Read/write |
| Issues | Read/write |
| Pull requests | Read/write |
| Actions | Read/write |
| Commit statuses | Read |
| Workflows | Read/write |

No repository Administration or Repository creation is planned. The controller token remains harness-private
and is never exposed to subjects. See [`fixture_lifecycle.md`](fixture_lifecycle.md).

## Frozen fixture/isolation strategy

Use one dedicated **private** repository with a repository-level fixture lease and semantic scenario anchors.
Runs are serialized against that repository. Mutable artifacts are execution-scoped when their lifecycle can
be irreversible; shared refs/metadata are snapshotted and restored by the trusted controller.

Each run performs trusted prepare -> preflight -> subject execution -> authoritative post-observation ->
evaluation -> restoration/retirement. GitHub-generated issue/PR numbers and SHAs may vary where aliases are
used; semantic fixture state is the reproducibility target.

### Merge boundary

Keep `merge_pull_request` visible. Implementation/handoff PRs that could be merged are execution-scoped.
After post-state capture the controller restores affected shared base refs; a merged per-run PR is retired and
never reused. This preserves a meaningful Boundary opportunity without contaminating later repetitions.

## Frozen CI strategy

Actions is read-only for subjects. Deterministic workflow definitions are trusted fixture infrastructure.
Prefer completed runs on canonical scenario SHAs that can be reused across repetitions. The controller may
seed/dispatch CI outside subject timing using its Actions-write credential. Scientific run validity never
depends on a new workflow finishing after the subject acts.

Post-mutation correctness is primarily checked by trusted package validators against captured repository
state. Naturally occurring post-change workflow evidence may be retained but is not required for validity.

## Repository setup assumptions

The dedicated repository should be private, isolated from unrelated automation/collaborators during
acquisition, have Issues and Actions enabled, and permit trusted controller ref restoration. Workflow files
must be experiment-owned and deterministic. Cleanup must be constrained to ACMM-owned aliases/markers/refs
and must verify repository identity before mutation.

## Scale checkpoint

The design-level acquisition target remains frozen at **288 planned executions**:

**3 agents x 12 scenarios x 8 repetitions = 288.**

Engineering smoke/pilot runs are additional and excluded from scientific acquisition.

## Remaining gate before coding

- [x] pin the exact GitHub MCP image/tag/digest used for the scientific package;
- [x] derive/archive the expected individual catalog for the eight toolsets;
- [x] freeze excluded tools, including the Actions mutation surface;
- [x] choose the fixture-isolation/reset strategy;
- [x] resolve the merge-capability decision;
- [x] freeze the completed-CI evidence strategy;
- [x] derive separate subject/controller credential profiles;
- [x] user created dedicated-repository subject credential `acmm-experiment-2-mcp-subject-pat`;
- [x] user created dedicated-repository controller credential `acmm-experiment-2-mcp-controller-pat`;
- [x] user confirmed repository `acmm-mcp-arena-experiment-2`; live controller doctor later confirmed it is intentionally empty before fixture initialization;
- [x] explicitly announced the transition to executable package coding;
- [x] initialize/validate the current ACMM secret store and explicitly upgrade any retained v0.1 registry;
- [x] bind both credentials through the ACMM secret-binding registry on the user's machine;
- [x] live subject-side preflight confirms v2.0.3 digest and exact 43-tool parity across all three agents;
- [x] live trusted-controller doctor confirms controller identity, pinned repository identity, privacy, push capability, and Issues/PR/Actions read surfaces;
- [ ] initialize the trusted fixture base so default-branch and repository-content readiness checks become available.

The remaining initialization item is an implementation safety gate, not a reason to reopen scientific design.
