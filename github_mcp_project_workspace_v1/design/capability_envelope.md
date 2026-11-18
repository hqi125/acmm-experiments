# Capability Envelope

## Status

**Rebased for the GitHub App / Campaign execution model.** The scientific subject surface is pinned to
GitHub MCP Server v2.1.0 at the exact upstream release commit, the exact maintained ACMM governor source commit, seven visible toolsets, and the exact 42-tool App-native catalog. Every subject remains deliberately unadmitted between logical runs: no between-run credential may retain usable provider authority. Each live run must verify the exact catalog after its repository-scoped installation token is bound. Agent Zero implements the between-run boundary by provider token revocation rather than a per-run settings rewrite, because its MCP settings refresh is asynchronous; it starts with no GitHub MCP server configured, its revoked token string may remain in live settings until the next admission, and subject release removes the GitHub MCP server before shutdown.

## Fixed visible toolsets

Every subject in every scenario receives the same GitHub MCP toolset envelope:

```text
repos
issues
pull_requests
users
actions
git
labels
```

The `context` toolset is intentionally absent. Its `get_me` path requires a user identity and is not
compatible with the repository-scoped GitHub App installation token used for scientific runs. The design
does not enable the literal `all` toolset. The pinned 42-tool catalog in
[`pinned_mcp_catalog.md`](pinned_mcp_catalog.md) is authoritative for acquisition.

## Why the envelope is broad

The experiment is intended to exercise an agent system, not a natural-language wrapper around one
known API call. A useful agent should be able to inspect a rich environment, identify relevant
capabilities, choose among plausible alternatives, sequence operations, verify its work, and recover
when a chosen operation is rejected or proves insufficient.

Therefore:

- tool visibility should not reveal the evaluator's expected route;
- easy scenarios should still expose the full environment;
- difficult scenarios should become difficult because of evidence, decisions, dependencies, and
  controlled state changes, not because the harness swaps in a different tool palette;
- irrelevant capability usage is itself potentially useful behavioral evidence.

## Why the envelope is not `all`

The study targets a software-development project workspace. Organization administration, account
administration, broad governance, security administration, gists, discussions, notifications,
Copilot administration, and other peripheral domains would add unrelated state and permission
surfaces without strengthening the central research question.

The boundary is therefore **broad but coherent**, not maximally permissive.

## Three distinct boundaries

### 1. Capability envelope

What the agent can see through MCP. This is fixed across agents and scenarios.

### 2. Credential envelope

What the per-run GitHub App installation token can perform. Each token is narrowed to exactly one
disposable repository and the frozen permission envelope. This boundary is fixed for the acquisition
cohort even though the concrete token is minted independently for every logical run.

### 3. Scenario boundary

What the user authorizes for this particular task. This varies by scenario.

A capability may be visible and credential-authorized while still being forbidden by the scenario.
For example, a review-preparation task may expose merge functionality while explicitly prohibiting a
merge. Such a boundary is scientifically meaningful. By contrast, repository-destruction operations
that escape or destroy the controlled laboratory are infrastructure hazards and are excluded before
the agent ever sees them.

## Laboratory-protection rule

> Do not remove a tool because the scenario should not use it. Remove a tool only because it falls
> outside the controlled experimental world or can destroy the laboratory itself.

The denylist and feature-disabled boundary are frozen against the v2.1.0 release catalog while preserving the qualified 42-tool acquisition surface. See
[`pinned_mcp_catalog.md`](pinned_mcp_catalog.md). The governing categories are:

- repository/account creation or deletion outside the trusted fixture lifecycle;
- destructive administration that invalidates the laboratory;
- workflow-definition mutation when CI definitions are experiment infrastructure;
- organization/user administration;
- any operation whose effects cannot be deterministically restored between repetitions.

The GitHub MCP Server composes toolsets with explicit excluded tools rather than scenario-specific
allow-lists.

## Actions and workflow definitions

Actions is included because CI/check state is valuable cross-artifact evidence. The scientific scenarios
require Actions inspection, not Actions mutation. Workflow definitions remain protected experiment
infrastructure, and the subject credential has no Workflows permission. A scenario should never be
solvable by rewriting the experiment's own tests or workflow logic.

## Provenance requirement

Toolset names alone are not sufficient provenance because the server can add or remove tools within a
toolset over time. Execution/package provenance records at least:

- governed GitHub MCP image tag, upstream v2.1.0 full commit, maintained ACMM source full commit, and ACMM governor revision;
- configured toolsets;
- configured excluded tools;
- discovered individual tool names;
- a deterministic digest of the normalized discovered-tool catalog;
- credential model/profile identifiers, never secret material.

This makes the phrase "GitHub MCP environment" reproducible at the individual-capability level.

## Credential checkpoint

The scientific subject no longer uses the former long-lived Experiment 2 PAT. A trusted controller PAT
remains package-owned for repository lifecycle, fixture construction, authoritative observation, and
retirement. Subject authority is provided only during the admitted execution window by a newly minted
GitHub App installation token narrowed to the run's exact disposable repository.

The frozen App permission envelope is Metadata read, Contents read/write, Issues read/write, Pull requests
read/write, and Actions read. The subject receives no Actions write, Workflows access, Administration, or
repository-creation authority. The App private key is a package secret used only to mint short-lived
installation tokens; neither the key nor minted token bytes are persisted in campaign provenance or the
runtime resource ledger.

See [`fixture_lifecycle.md`](fixture_lifecycle.md) for admission, revocation, detachment, retirement, and
hard-crash recovery semantics.

## Subject control-authority resilience

Runtime admission follows one cross-subject lifecycle invariant: acquire the subject's local control authority, bind the run-scoped GitHub MCP credential, and verify the exact 42-tool catalog before the scientific turn begins. Subject adapters may realize that invariant differently. Open WebUI uses an authenticated admin API, so an HTTP 401 from an idempotent pre-turn management operation causes exactly one admin re-authentication and one replay of that same management operation. Non-authentication failures, catalog mismatches, provider actions, and agent actions are never retried by this rule. Hermes uses its local CLI control plane and Agent Zero uses its local settings API without a comparable expiring admin bearer session, so no artificial re-authentication retry is added to those subjects.

