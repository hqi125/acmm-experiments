# Fixture Lifecycle and Isolation Strategy

## Current strategy: one disposable repository and one App token per scientific run

Experiment 2 uses **one private disposable GitHub repository per selected scientific run**. The engineering
reference repository `Dufferin125/acmm-mcp-arena-experiment-2` remains useful for controller diagnostics and
apparatus actions, but scientific repetitions do not share its permanent issue/PR/history state.

The subject no longer uses an all-repositories PAT. The current credential separation is:

1. a trusted **controller PAT**, used only by package-owned apparatus code for repository lifecycle, fixture
   materialization, authoritative observation, evidence capture, App-installation repository assignment, and
   retirement; and
2. a **per-run GitHub App installation token**, minted only after the disposable repository is fully prepared,
   narrowed by GitHub to that exact repository, admitted to the subject-facing GitHub MCP integration only for
   the subject execution window, and explicitly revoked afterward.

The App installation itself uses selected-repository access. A newly created disposable repository is attached
to the installation immediately before token minting and detached again before repository retirement.
Repository creation/deletion remains absent from the subject MCP catalog.

## Package-owned scenario blueprints

Scenario source of truth lives inside the Experiment Package rather than in persistent GitHub template
repositories. A blueprint describes the semantic state to materialize, including as needed:

- repository settings and seed files;
- commit ancestry and branches;
- labels and milestones;
- issue bodies, state, comments, and relationships;
- pull requests, merge state, and review metadata;
- workflow definitions and deterministic completed Actions evidence;
- scenario aliases and authoritative invariants.

A remote template repository is not the scientific source of truth. Package-local blueprints avoid leakage and
remain versioned with experiment provenance.

## Run lifecycle

For every selected run, trusted package/Core code performs the following lifecycle:

1. derive a unique repository name containing an execution-specific recovery tag;
2. create a new private repository with the controller credential;
3. durably record the returned full name and numeric repository ID in the execution-local resource ledger;
4. verify the controller resolves the exact new repository identity;
5. materialize the selected scenario blueprint and deterministic Actions evidence when required;
6. independently capture and verify authoritative pre-state;
7. attach the exact repository ID to the selected-repository GitHub App installation;
8. mint an installation token narrowed to exactly that repository and the qualified permission envelope;
9. hand the token to Core as an opaque runtime-admission request; the token is never written to campaign or
   experiment provenance;
10. bind the token to the selected agent's GitHub MCP configuration and verify the exact 42-tool App-native
    catalog;
11. expose the task and execute the subject;
12. explicitly revoke the installation token and restore the subject integration to its non-secret unadmitted
    sentinel before trusted post-state observation;
13. capture authoritative post-state and persist run evidence;
14. detach the repository from the GitHub App installation;
15. delete the exact repository ID with the controller credential and verify disappearance.

Ordinary preparation/finalization failures preserve an immutable forensic ZIP under the execution's
`apparatus_quarantine/` directory before exact-ID deletion whenever the repository remains readable.

## Durable resource ledger and hard-crash recovery

Every disposable repository is recorded in `github_runtime_resources.json` under the runtime session directory.
The ledger contains only non-secret resource state: repository identity, App-installation attachment state,
a SHA-256 fingerprint of a minted token, admission/unbinding markers, detachment state, and retirement state.
The token itself is never persisted.

Repository names also contain a short hash of the execution ID. If the process dies after GitHub creates the
repository but before the ledger write becomes durable, recovery can discover only repositories belonging to
that interrupted execution.

After an unclean Campaign execution, the package's generic `runtime_execution_recovery` hook reconciles any
recorded or execution-tagged disposable repositories before Core admits new work. Because a hard crash can lose
the token bytes, recovery may be unable to call token revocation directly. The token was minted for exactly one
repository, so recovery first detaches that repository from the App installation and then deletes it. The orphaned
token therefore has no authority over any future run repository and subsequently expires provider-side.

A stale agent configuration containing such a token is likewise non-authoritative: the token cannot reach future
repositories, and the next successful runtime admission overwrites the binding with the new run-scoped token.

## Credential envelope

### Subject GitHub App installation token

Each token is minted for one repository only with the qualified envelope:

| Permission | Level |
| --- | --- |
| Metadata | Read |
| Contents | Read/write |
| Issues | Read/write |
| Pull requests | Read/write |
| Actions | Read |

`Workflows` is intentionally absent. The App has no Repository creation, Administration, organization, or
account-level authority. The `context/get_me` MCP path is intentionally excluded because an installation token
has no user identity.

### Controller credential

The controller remains a fine-grained PAT under the dedicated experiment account with the trusted lifecycle
permissions required to create/delete repositories, materialize fixtures, operate deterministic CI fixtures, and
add/remove repositories from the selected-repository App installation. These powers are never exposed through
the subject MCP surface.

### App private key

The GitHub App private key is an Experiment Package secret (`github_app_private_key`). It is used only to sign
short-lived App JWTs for installation-token minting. It is never copied into the repository, campaign artifacts,
resource ledger, subject profiles, or MCP environment.

## Sequential remote provisioning

The current v1 lifecycle remains sequential within one execution session: `session_initialize()` refuses to
start a second run while another disposable repository is active. Per-repository App scoping now removes the old
all-repositories-PAT leakage mechanism, but concurrency is intentionally not introduced as part of this credential
rebase. Parallel/distributed Campaign execution can be evaluated separately after its scheduling and rate-limit
semantics are designed explicitly.

## CI strategy under disposable repositories

Scenarios that scientifically depend on completed CI evidence materialize or dispatch deterministic repository-
local Actions evidence during trusted preparation, outside subject timing. The subject receives Actions read only.
This provisioning cost is apparatus/runtime cost, not agent performance, and remains independently measurable.
