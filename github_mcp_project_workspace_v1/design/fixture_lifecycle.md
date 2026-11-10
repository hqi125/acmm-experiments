# Fixture Lifecycle and Isolation Strategy

## Current strategy: disposable repository per scientific run

Experiment 2 now targets **one private disposable GitHub repository per selected scientific run**. This
supersedes the earlier canonical-shared-world plan for final acquisition. The existing repository
`Dufferin125/acmm-mcp-arena-experiment-2` remains an engineering reference used to qualify F1-A/F1-B and the
controller primitives, but final scientific repetitions should not share its permanent issue/PR/history state.

The pivot is motivated by GitHub's object model: issues, pull requests, merge history, workflow runs, and many
other artifacts cannot be reset to a truly pristine state. A fresh repository gives each scenario/subject/
repetition cell an independent state container and removes the need to teach every later fixture how to ignore
an ever-growing archive of previous scenarios.

Two credentials remain strictly separated:

1. the **subject credential**, exposed only through the qualified GitHub MCP service during scientific runs;
2. the **controller credential**, used only by trusted package code for repository lifecycle, fixture
   materialization, authoritative observation, evidence capture, and deletion.

Repository creation/deletion remains excluded from the subject MCP catalog. The agent never provisions or
removes its own laboratory container.

## Package-owned scenario blueprints

Scenario source of truth should live inside the Experiment Package rather than in persistent GitHub template
repositories. A blueprint describes the semantic state to materialize, including as needed:

- repository settings and seed files;
- commit ancestry and branches;
- labels and milestones;
- issue bodies, state, comments, and relationships;
- pull requests, merge state, and review metadata;
- workflow definitions and deterministic completed Actions evidence;
- scenario aliases and authoritative invariants.

The existing F1-A and F1-B materializers already implement most of the required GitHub primitives. The next
implementation stage converts their fixed-repository assumptions into parameterized blueprint materialization
against a newly created run repository.

A remote GitHub template repository is not the scientific source of truth: generating from a template does not
reproduce issue/PR/workflow-run state, and a subject token with all-repository access could discover such a
remote golden repository. Package-local blueprints avoid that leakage and remain versioned with experiment
provenance.

## Run lifecycle

For every selected run, trusted package code should perform the following lifecycle:

1. allocate a unique repository name from the execution/scenario/subject context;
2. create a new private repository with the controller credential;
3. record the returned full name and numeric GitHub repository ID;
4. verify that both controller and subject credentials resolve the exact new repository identity;
5. materialize the selected scenario blueprint;
6. seed/await deterministic Actions evidence when the scenario requires it, outside subject timing;
7. independently capture and verify the complete authoritative pre-state;
8. bind only the new repository owner/name and scenario task data into the subject prompt;
9. execute the subject through the unchanged qualified 43-tool GitHub MCP surface;
10. capture authoritative post-state immediately after subject termination;
11. archive raw agent/MCP evidence plus repository/issue/PR/ref/file/Actions evidence required for adjudication;
12. evaluate GOBPFR opportunities from the archived evidence and trusted observations;
13. verify the evidence manifest/hashes are complete;
14. delete the exact repository identity created for that run with the controller credential;
15. verify the repository is no longer visible to either controller or subject credentials.

Deletion is **evidence-last**. If authoritative post-state/evidence capture fails, the controller must not delete
first and hope to reconstruct the state later. Instead, the repository is quarantined for operator inspection
and the run is invalidated/reconciled explicitly.

The repository full name and numeric repository ID are archived before deletion. Repository name alone is never
sufficient authorization for destructive cleanup.

## Disposable-repository lifecycle qualification

For engineering qualification and operator debugging, the package exposes the free-form apparatus action:

```text
acmm run apparatus exec qualify_disposable_repositories
```

`acmm run apparatus exec` resolves the currently converged Experiment 2 deployment, so the experiment selector
is not repeated. `acmm run apparatus list` enumerates the available engineering operations, while the bare
`acmm run apparatus` family is intentionally invalid. These free-form actions are distinct from the typed
scientific runtime lifecycle and are never automatically substituted for its fixed phases.

The action performs one complete non-scientific lifecycle probe:

1. authenticate distinct controller/subject credentials;
2. create a uniquely named private repository with the controller credential;
3. re-read and verify the exact returned numeric repository ID from both credentials;
4. create the first marker commit with the **subject** credential, proving dynamic repository write access;
5. read the marker back with the controller credential;
6. re-check the numeric repository ID and delete that exact repository with the controller credential;
7. verify subsequent repository reads return not-found for both credentials.

The probe uses a unique repository name and deletion is guarded by the numeric repository ID returned from the
same creation call. If identity changes, deletion is refused. The action is engineering qualification only and
produces no scientific data.

One clean live probe has now passed against the real experiment account: controller create/delete authority,
subject dynamic write access, exact repository-ID guards, and deletion visibility all behaved as designed.
Repeated lifecycle stress remains a later qualification step before full 288-run acquisition.


## Core-owned typed execution lifecycle

Scientific repository creation/deletion is no longer modeled as a sequence of free-form apparatus action names.
Experiment 2 opts into Core's typed execution lifecycle:

1. `session_initialize` authenticates the controller/subject context for the execution session;
2. `run_prepare` creates one fresh **private** repository, verifies the exact numeric identity from both
   credentials, initializes its trusted base, materializes the selected scenario blueprint, captures
   authoritative pre-state, and returns the dynamic owner/repository bindings;
3. Core executes the subject through the unchanged qualified MCP surface;
4. `run_observe` captures authoritative post-state for evaluation;
5. Core persists the run record, raw/normalized evidence, authoritative snapshots, and judgments;
6. only then does `run_finalize` re-verify the exact private repository identity and delete it;
7. `session_finalize` closes the execution-session lifecycle.

These typed hooks are not independently callable through `acmm run apparatus`; Core owns their ordering. If a
run does not reach durable persistence, Experiment 2 deliberately leaves the repository quarantined for
operator inspection rather than deleting the only remaining external evidence.

Repository creation is private-only in trusted controller code: callers cannot request a public repository, and
the returned GitHub repository must independently report `private=true` before materialization proceeds.

### Current migration status

F1-A, F1-B, F2-A, and F2-B now use this disposable typed lifecycle. Each materializes package-owned semantics
against a fresh run repository and writes a dynamic trusted-base marker containing that repository's full name
and numeric ID. F1-B additionally dispatches and waits for its deterministic required-check workflow before
subject execution begins. F2-A captures an explicitly bounded mutable issue surface; F2-B protects the entire
remote state and additionally distinguishes true no-op trajectories from successful mutation followed by restore.

## Credential separation

### Subject credential

Fine-grained PAT with **All repositories** access under the dedicated experiment account so repositories
created after token issuance are reachable dynamically.

| Permission | Level |
| --- | --- |
| Metadata | Read |
| Contents | Read/write |
| Issues | Read/write |
| Pull requests | Read/write |
| Actions | Read |
| Commit statuses | Read |

The subject credential has no Repository creation or Administration permission. Repository lifecycle tools
remain excluded from the MCP server surface.

### Controller credential

Fine-grained PAT with **All repositories** access under the same experiment account.

| Permission | Level |
| --- | --- |
| Metadata | Read |
| Contents | Read/write |
| Issues | Read/write |
| Pull requests | Read/write |
| Actions | Read/write |
| Commit statuses | Read |
| Workflows | Read/write |
| Repository creation | Read/write |
| Administration | Read/write |

`Repository creation` covers creation/generation operations; `Administration: write` is required for repository
deletion. These lifecycle powers remain trusted-controller-only.

## No ahead-of-time remote repository buffering

Scientific repository provisioning remains strictly sequential: while a subject is operating on run N, trusted
code must not create the remote repository for run N+1. Both fine-grained PATs currently have **All repositories**
visibility under the same dedicated account, so any pre-created future repository would become discoverable to
the current subject through repository search/list operations. That is cross-run environmental leakage even if
the future repository is never mutated.

A post-hoc "repository N+1 was unchanged" checksum is therefore insufficient: read-only discovery of future-run
state can still alter the current agent's search path, interpretation, or tool choices. Likewise, buffering an
empty repository still exposes an extra account-level artifact not belonging to the current run.

Accordingly, safe optimization may reduce work *inside* one run's trusted preparation, but it must preserve this
visibility invariant. Concurrent remote pre-creation should be reconsidered only if the credential/repository
model can make future-run repositories inaccessible to the current subject (for example, per-repository scoped
credentials or an equivalent independently verified isolation mechanism). Wall-clock savings alone do not justify
weakening one-run/one-visible-world isolation.

## CI strategy under disposable repositories

A disposable repository removes cross-run contamination but also removes the possibility of reusing one remote
workflow run forever. Scenarios that scientifically depend on completed CI evidence must therefore materialize
or import equivalent deterministic evidence during trusted preparation.

The controller should keep this outside subject timing and use the minimum workflow execution needed for the
scenario. Most scenarios do not require Actions. For F1-B/F4/F6 cases that do, preparation may dispatch and
wait for a deterministic repository-local workflow before authoritative pre-state is released to the subject.

This provisioning cost is an apparatus/runtime cost, not agent performance. It should be measured separately
and may motivate later safe optimizations, but repository reuse should not be introduced merely to reduce wall
clock if doing so weakens isolation.

## Engineering reference repository

The existing pinned repository remains valuable during the transition:

- F1-A materialization and scientific lifecycle are qualified there;
- F1-B materialization and deterministic Actions topology are qualified there;
- it provides known-good identities/topologies for comparing the first disposable F1-A/F1-B worlds.

Do not delete it until the disposable lifecycle can reproduce equivalent authoritative scenario semantics and
survive repeated create/materialize/evidence/delete stress qualification.
