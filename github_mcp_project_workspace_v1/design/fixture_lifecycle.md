# Fixture Lifecycle and Isolation Strategy

## Frozen strategy

Use **one dedicated private GitHub repository** as the controlled laboratory, with two separate credentials:

1. a **subject credential** used only by the GitHub MCP service exposed to agents; and
2. a **controller credential** used only by trusted package fixture/provenance code.

The controller credential is never inserted into prompts, agent environments, MCP headers, or subject
containers. Separating the credentials lets the controller perform deterministic setup/reset operations
without silently granting those powers to the experimental agents.

The experiment should serialize fixture use through one repository-level lease. Scientific runs must not
mutate the same laboratory repository concurrently unless a future repository-pool design explicitly
replaces this strategy.

## Repository layers

### Stable laboratory scaffold

The repository contains experiment-owned infrastructure that is prepared once and restored when needed:

- protected-by-policy workflow definitions under `.github/workflows/**`;
- common README/policy documents used by scenarios;
- canonical labels;
- canonical commit anchors for each scenario;
- any reusable historical artifacts whose identity can safely remain stable.

The subject credential has Contents write but **no Workflows permission**, so normal branch/file work is
possible while workflow-definition mutation fails at the GitHub authorization layer. Scenario prompts also
protect workflow definitions explicitly.

### Scenario anchors

Each scenario owns semantic fixture anchors: known commits, branch topology, policy text, issue/PR state,
and where applicable completed deterministic CI evidence. Reproducibility is defined by this semantic
state, not by globally stable issue numbers or PR numbers.

### Per-run namespace

Every run receives an execution-scoped namespace for mutable artifacts, for example:

```text
branch: acmm/<execution-short>/<scenario>/<role>
marker: ACMM-FIXTURE:<execution-id>:<alias>
```

The exact naming scheme is an implementation detail, but it must make run ownership unambiguous and permit
trusted cleanup. Mutable issues/PRs should be per-run whenever irreversible lifecycle transitions (especially
merge) would make reuse unsafe.

## Run lifecycle

For every selected run the trusted controller should:

1. acquire the repository fixture lease;
2. restore shared refs/metadata to the scenario's canonical anchors;
3. allocate/create per-run branches, issues, PRs, comments, and labels as required;
4. resolve symbolic aliases to concrete GitHub identifiers;
5. attach or verify the scenario's pre-seeded CI evidence where applicable;
6. independently verify the complete authoritative pre-state;
7. only then release the prompt/bindings to the subject;
8. capture authoritative post-state immediately after subject termination;
9. evaluate terminal predicates and protected invariants from trusted observations;
10. archive alias mappings and fixture provenance with the run evidence;
11. restore any shared refs/metadata touched by the subject;
12. retire per-run objects and delete disposable per-run branches after evidence capture;
13. release the repository fixture lease.

Retirement does not require erasing every historical GitHub object. A unique per-run PR that was improperly
merged can remain merged and archived after its base ref is restored; it is never reused as a later fixture.

## Merge containment decision

`merge_pull_request` remains visible.

This is scientifically preferable because F5/F6 explicitly withhold merge authority while the environment
contains a realistic PR surface. Containment is achieved by fixture ownership rather than by hiding the
capability:

- mutable PRs exposed to implementation/handoff scenarios are execution-scoped;
- shared base refs are snapshotted and can be force-restored by the trusted controller;
- a merged execution-scoped PR is retired permanently rather than reused;
- post-state is captured **before** restoration so the Boundary violation remains observable evidence.

If live pilot testing proves a particular scenario cannot absorb merge safely, that scenario may be revised,
but the experiment-wide default is to preserve the merge capability.

## CI seeding strategy

Do **not** run a fresh GitHub Actions job for every one of the 288 scientific executions unless a scenario
specifically requires a new run as part of fixture preparation.

Instead:

- deterministic workflow definitions are part of the stable scaffold;
- the trusted controller uses canonical scenario SHAs to seed completed CI runs before acquisition/pilot
  freeze;
- completed run/job/log identities become scenario fixture provenance;
- repetitions reuse that completed pre-change evidence when the same canonical SHA is restored;
- when a per-run PR needs equivalent CI context, prefer a head commit identical to a canonical validated SHA
  or explicitly create/await the required run during fixture preparation, outside subject timing;
- subject validity never depends on queue time or a workflow finishing after the agent acts;
- post-mutation semantic correctness is checked by trusted package validators against the resulting snapshot.

The controller credential may dispatch/rerun workflows for fixture seeding; the subject credential cannot.

## Credential separation

### Subject credential

Fine-grained PAT, selected-repository access to the dedicated laboratory repository only:

| Permission | Level |
| --- | --- |
| Metadata | Read |
| Contents | Read/write |
| Issues | Read/write |
| Pull requests | Read/write |
| Actions | Read |
| Commit statuses | Read |

No repository Administration, Repository creation, Actions write, or Workflows write.

### Controller credential

Fine-grained PAT, selected-repository access to the same laboratory repository only:

| Permission | Level |
| --- | --- |
| Metadata | Read |
| Contents | Read/write |
| Issues | Read/write |
| Pull requests | Read/write |
| Actions | Read/write |
| Commit statuses | Read |
| Workflows | Read/write |

The controller does not need repository Administration or Repository creation under the frozen single-repo
strategy. Workflow write is trusted-apparatus capability used to bootstrap/restore deterministic workflow
files; it is not exposed to subjects.

If GitHub's live API reports an additional fine-grained permission requirement for a concrete controller
endpoint during implementation, add it only after documenting why Contents/Actions/Workflows is
insufficient.

## Repository setup assumptions

Before live fixture-controller/pilot work:

- the dedicated repository should be private;
- no unrelated collaborators or automation should mutate it during acquisition;
- Issues and Actions should be enabled;
- branch/ruleset settings must permit trusted controller ref restoration;
- experiment workflows should use deterministic, repository-local inputs and avoid external network/services;
- the package should verify repository identity before destructive fixture cleanup;
- every cleanup operation should be constrained to ACMM-owned aliases/markers/refs.

The controller must never treat "same repository name" alone as sufficient authorization to clean up state;
repository owner/login and expected repository identity must also match the configured fixture target.

Live controller qualification on 2026-11-08 pinned the fixture target to:

- full name: `Dufferin125/acmm-mcp-arena-experiment-2`;
- GitHub repository ID: `1447536932`.

The repository is intentionally empty at this checkpoint. `env doctor` therefore treats trusted fixture-base
initialization as a readiness blocker while continuing to report independent Issues/PR/Actions read surfaces.
