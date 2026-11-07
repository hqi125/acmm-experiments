# Pre-Coding Checkpoint

## Status

**Scenario design complete; implementation not started.**

All twelve scenarios are frozen at the design level. This document consolidates the setup decisions
that must be reviewed before any `experiment-package.yaml`, `experiment.yaml`, runtime, fixture,
evaluator, or executable scenario code is created.

The transition to coding must be explicitly announced after this checkpoint is resolved.

## Frozen scientific shape

- experiment: `github_mcp_project_workspace_v1`;
- subjects: Hermes, Open WebUI, Agent Zero under the same qualified LLM baseline;
- fixed visible toolsets: `context`, `repos`, `issues`, `pull_requests`, `users`, `actions`, `git`, `labels`;
- scenarios: 6 families x 2 independently authored variants = 12;
- repetitions: 8 per scenario per agent;
- planned acquisition: 96 runs/agent, 288 total;
- primary evaluation: authoritative state + invariants + final claims;
- trajectory evidence: explanatory/diagnostic, not a golden-sequence matcher.

## Credential profile derived from the frozen scenarios

The current issue-only qualification credential is insufficient for scientific acquisition.

For a **fine-grained PAT scoped only to the dedicated experimental repository**, the frozen scenarios
currently imply the following repository permissions:

| Permission | Intended level | Why the experiment needs it |
| --- | --- | --- |
| Metadata | Read | repository/context discovery; normally implicit for fine-grained repository access |
| Contents | Read and write | inspect files/commits/refs, create branches, write scenario-owned branch content |
| Issues | Read and write | read/update issue state, labels, and comments |
| Pull requests | Read and write | inspect/create/update PRs and preserve/transition review handoffs |
| Actions | Read | inspect workflows, runs, jobs, and diagnostic logs |
| Commit statuses | Read | inspect status evidence where the pinned MCP catalog routes through commit-status APIs |

The scenario set does **not** require:

- Actions write;
- Workflows write;
- Administration;
- Repository creation;
- security/governance/organization permissions.

Workflow definitions remain protected experiment infrastructure. Contents write is intended for normal
repository files and refs; it does not authorize scenario-level mutation of `.github/workflows/**`.

This profile must still be validated against the exact pinned MCP image and its discovered individual
catalog before the user changes credentials.

## Actions surface conclusion

The frozen scenarios require Actions **inspection**, not Actions mutation. Completed pre-change runs are
fixture evidence; subject correctness never depends on triggering/rerunning/cancelling a workflow.

At the pinned-catalog checkpoint, prefer excluding the Actions mutation entry point(s) from the visible
catalog rather than granting Actions write merely to create forbidden temptations. The current upstream
server exposes Actions inspection separately from `actions_run_trigger`, which makes this boundary
practical, but exact names must be taken from the pinned image rather than copied blindly from upstream.

## Merge boundary

`merge_pull_request` is scientifically interesting because every implementation/handoff scenario
explicitly withholds merge authority while PR write permission may technically permit it. However, an
unauthorized merge creates harder-to-reverse GitHub history.

Before coding, choose one of two defensible fixture strategies:

1. **Visible merge capability + isolation strong enough to absorb violations.** This preserves a real
   Boundary opportunity and records unauthorized merges as agent behavior.
2. **Exclude merge as laboratory protection.** Use this only if fixture/reset design cannot isolate an
   accidental merge without contaminating later repetitions.

Do not decide this solely from convenience; decide it together with the fixture lifecycle.

## Fixture lifecycle requirements derived from the scenarios

The trusted controller must be able to materialize and independently observe at least:

- repository files and deterministic commit history;
- default, release, and scenario-owned branches;
- issues, comments, labels, and lifecycle state;
- pull requests, draft/open/merged state, base/head topology, comments/reviews where used;
- completed Actions runs/jobs/log evidence tied to known SHAs;
- semantic source/test fixtures used by trusted validators.

For every run the controller must:

1. prepare or allocate a clean scenario instance;
2. verify the authoritative pre-state before releasing it to the subject;
3. resolve symbolic fixture aliases to actual GitHub identifiers;
4. execute the subject only after the fixture passes preflight;
5. capture authoritative post-state independently of the agent;
6. evaluate terminal predicates and protected invariants;
7. retain enough evidence to explain tool/state transitions;
8. clean, retire, or isolate the instance so later runs cannot inherit subject mutations.

GitHub-generated issue/PR numbers and SHAs do not need to repeat across runs. Reproducibility is defined
by the semantic fixture and alias mapping, not by identical global identifiers.

## CI fixture requirements

CI-heavy scenarios use completed, package-owned pre-change runs as evidence. The fixture must record at
least workflow identity, run ID, head SHA, job IDs, conclusions, and deterministic log facts.

Post-mutation correctness should be validated by trusted package logic against the resulting repository
snapshot. A naturally triggered GitHub run may be recorded when present, but acquisition validity must
not depend on runner timing.

## Laboratory-protection denylist checkpoint

The exact excluded-tool list is **not frozen from upstream names yet**. It must be generated after the
experiment pins its GitHub MCP image and captures the discovered catalog.

Rules for that review:

- exclude operations outside the dedicated project-workspace world;
- exclude operations requiring credentials deliberately absent from the experiment when leaving them
  visible would create permanently dead/misleading capabilities;
- exclude Actions mutation because no frozen scenario requires it;
- protect workflow-definition mutation;
- review repository/account creation, deletion, administration, and other non-restorable operations;
- decide `merge_pull_request` together with the fixture-isolation strategy rather than automatically
  excluding it.

Scenario-specific forbidden actions should otherwise remain visible when safe enough to observe.

## Scale checkpoint

The design-level acquisition target is now **frozen at 288 planned executions**:

**3 agents x 12 scenarios x 8 repetitions = 288.**

Engineering smoke/pilot runs are additional and should not be counted as scientific acquisition.
The scale may be reopened only if implementation/pilot evidence shows a scenario is infeasible,
non-independent, or materially miscalibrated.

## Remaining pre-coding decisions

Before coding begins:

- [ ] pin the exact GitHub MCP image/tag/digest used for the scientific package;
- [ ] discover and archive the exact individual tool catalog for the eight toolsets;
- [ ] validate the fine-grained permission profile against those exact tools;
- [ ] freeze excluded tools, including the Actions mutation surface;
- [ ] choose the fixture-isolation/reset strategy and resolve the merge-capability decision;
- [ ] confirm how completed CI evidence is seeded reproducibly;
- [ ] confirm the dedicated GitHub repository/account setup;
- [ ] only then announce the transition to executable package coding.

Until those boxes are resolved, repository changes remain documentation/design work only.
