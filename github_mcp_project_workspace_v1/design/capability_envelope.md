# Capability Envelope

## Status

**Working freeze candidate.** The toolset-level envelope is agreed in principle. Exact discovered
individual tools and the laboratory-protection denylist remain to be frozen against the pinned server
catalog before implementation.

## Fixed visible toolsets

Every subject in every scenario should receive the same GitHub MCP toolset envelope:

```text
context
repos
issues
pull_requests
users
actions
git
labels
```

The current official GitHub MCP Server defaults are `context`, `repos`, `issues`, `pull_requests`, and
`users`. This experiment adds `actions`, `git`, and `labels` to create a coherent software-project
workspace. The design intentionally does not enable the literal `all` toolset. As checked on 2026-11-06,
the official catalog places branch/file mutation such as `create_branch`, `create_or_update_file`, and
`push_files` under `repos`; the `git` toolset currently contributes repository-tree inspection through
`get_repository_tree`. The final pinned catalog remains authoritative if that surface changes before coding.

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

The boundary should therefore be **broad but coherent**, not maximally permissive.

## Three distinct boundaries

### 1. Capability envelope

What the agent can see through MCP. This is fixed across agents and scenarios.

### 2. Credential envelope

What the dedicated experimental credential can actually perform in the experimental repository. This
should also be fixed for the acquisition cohort and should be scoped as narrowly as GitHub permits to
the laboratory repository/resources.

### 3. Scenario boundary

What the user authorizes for this particular task. This varies by scenario.

A capability may be visible and credential-authorized while still being forbidden by the scenario.
For example, a review-preparation task may expose merge functionality while explicitly prohibiting a
merge. Such a boundary is scientifically meaningful. By contrast, repository-destruction operations
that escape or destroy the controlled laboratory are infrastructure hazards and should be excluded
before the agent ever sees them.

## Laboratory-protection rule

> Do not remove a tool because the scenario should not use it. Remove a tool only because it falls
> outside the controlled experimental world or can destroy the laboratory itself.

The exact denylist is intentionally **not frozen yet**. It must be derived from the individual tool
catalog discovered from the pinned GitHub MCP image. Candidate categories to review before coding:

- repository/account creation or deletion outside the fixture lifecycle;
- destructive administration that invalidates the laboratory repository;
- workflow-definition mutation if CI definitions are treated as experiment infrastructure;
- organization/user administration;
- any operation whose effects cannot be deterministically restored between repetitions.

The GitHub MCP Server supports composing toolsets with explicit excluded tools. The final package
should use that mechanism rather than narrowing every scenario to a handpicked allow-list.

## Actions and workflow definitions

Actions is included because CI/check state is valuable cross-artifact evidence. Scenario design has
now resolved the mutation boundary: the scientific scenarios require Actions inspection, not Actions
mutation. Workflow definitions remain protected experiment infrastructure, and the
pre-coding catalog review should exclude the Actions mutation surface while retaining Actions reads. A
scenario should never be solvable by rewriting the experiment's own tests or workflow logic.

## Provenance requirement

Toolset names alone are not sufficient provenance because the official server can add/remove tools
within a toolset over time. The final execution/package provenance should record at least:

- pinned GitHub MCP image tag and image digest;
- configured toolsets;
- configured excluded tools;
- discovered individual tool names;
- a deterministic digest of the normalized discovered-tool catalog;
- credential permission profile identifier (never the secret itself).

This makes the phrase "GitHub MCP environment" reproducible at the individual-capability level.

## Token checkpoint

The current qualification token is intentionally limited to issue operations and is sufficient only
for engineering qualification. No permission expansion is needed during design.

Scenario design now derives the following candidate fine-grained repository profile: Metadata read,
Contents read/write, Issues read/write, Pull requests read/write, Actions read, and Commit statuses
read. No frozen scenario requires Actions write, Workflows write, Administration, or Repository
creation. The exact profile must still be validated against the pinned individual-tool catalog before
the credential is changed. See [`pre_coding_checkpoint.md`](pre_coding_checkpoint.md).
