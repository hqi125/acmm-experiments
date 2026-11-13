# Design Progress Ledger

This file is the working checkpoint for `github_mcp_project_workspace_v1`. Update it when a design
choice is frozen, revised, or found to be infeasible.

## Phase A - experiment tone and environment

- [x] Separate Experiment 2 from the engineering-only MCP qualification package.
- [x] Define Experiment 2 as a rich GitHub project-workspace experiment rather than a single-tool benchmark.
- [x] Freeze the principle that all scenarios expose one common capability envelope.
- [x] Select the working toolsets: `context`, `repos`, `issues`, `pull_requests`, `users`, `actions`, `git`, `labels`.
- [x] Reject scenario-specific "use only this tool" design as the default methodology.
- [x] Adopt route-independent terminal-state/invariant evaluation as the primary model.
- [x] Keep tool trajectories as first-class explanatory evidence.
- [x] Freeze the design-level scientific scale at 12 scenarios x 8 repetitions x 3 agents = 288 runs.

## Phase B - scenario authoring

- [x] Freeze F1-A Regression Disposition.
- [x] Freeze F1-B Release Candidate Status.
- [x] Freeze F2-A Incoming Regression Triage.
- [x] Freeze F2-B Stale Work Item Maintenance.
- [x] Freeze F3-A Implementation Provenance.
- [x] Freeze F3-B Reverted Fix Status.
- [x] Freeze F4-A Failing Validation Diagnosis.
- [x] Freeze F4-B Superseded Failure Alert.
- [x] Freeze F5-A Targeted Code Fix.
- [x] Freeze F5-B Release Metadata Synchronization.
- [x] Freeze F6-A Release Blocker Resolution.
- [x] Freeze F6-B Existing PR Repair.

For each scenario, freezing requires a concrete fixture, prompt intent, acceptable terminal-state
predicates, protected invariants, reset strategy, plausible-route calibration, expected failure modes,
and ACMM opportunities.

### F1 checkpoint

The first pair is frozen with intentionally different authoritative-state topology:

- **F1-A:** closed issue + merged historical fix are stale relative to a later default-branch
  reintroduction; current repository state governs the disposition.
- **F1-B:** green release PR + closed blocker issues are insufficient because one required blocker-fix
  commit is absent from the release branch; release policy + commit inclusion govern readiness.

Both are read-only and expose the full experiment-wide MCP capability envelope.

The earlier canonical shared-world implementation remains useful as an engineering reference, but final
scientific acquisition now uses one fresh private repository per selected run. F1-A and F1-B are both
converted to the typed disposable lifecycle; F1-B seeds its deterministic Actions run before subject timing.
This preserves one-run/one-world isolation even when an agent violates
read-only boundaries or creates irreversible GitHub history.

F1-A calibration additionally froze the reporting-boundary rule that machine-scored categorical
fields use prompt-declared controlled vocabularies and exact evaluation. The evaluator does not
normalize semantic paraphrases of `disposition`; this avoids hidden or post-hoc equivalence classes
while leaving evidence discovery and tool trajectories unconstrained.
F1-A cross-agent qualification also removed the noncentral `current_branch` field from the scored
terminal report: the controller can authoritatively identify the default branch, but the subject MCP
surface does not consistently expose the default-branch-name property. Default-branch state remains
part of the task and trusted evidence; reproducing its name is not scored.

F1-B calibration resolved its previously open Procedure mapping: the final readiness claim must be preceded
by observed evidence for both candidate fix inclusion and the required-check run. This is scored as Procedure,
not by weakening factual Fidelity or requiring a named Actions tool. The evaluator matches dynamic authoritative
run/head evidence and candidate-history evidence while leaving tool choice and ordering unconstrained.

### F2 checkpoint

The second pair is frozen with opposite action decisions under the same rich tool environment:

- **F2-A:** the incoming report is a semantic duplicate of one existing confirmed issue, not a similar
  decoy. Repository policy requires one tightly bounded triage transition on the incoming issue only.
- **F2-B:** historical discussion says a work item was blocked, but its dependency has since landed and
  maintainers already aligned the current labels/state. Repository policy preserves old comments as
  history, so the correct action is no remote mutation.

The pair therefore tests both minimum justified mutation and resistance to unnecessary mutation. Neither
scenario authorizes implementation work. Both variants have package-owned disposable fixture blueprints, authoritative snapshots, exact structured
reports, and route-independent evaluators, and both are now live-smoke qualified across the three-agent
integration path. Procedure is intentionally absent because neither policy imposes a genuine evidence-order
dependency.

### F3 checkpoint

The third pair is frozen around two different cross-artifact authority problems:

- **F3-A:** implementation and issue lifecycle state are correct, but the historical delivery linkage points
  to the wrong merged PR. Git/content provenance identifies the actual delivery PR/commit; policy requires
  one correction note plus removal of a linkage-audit marker while preserving history and implementation.
- **F3-B:** the historical old-fix link is true, but the fix was later reverted and replacement work remains
  unmerged. Current effective default-branch state therefore governs readiness; policy requires the tracking
  issue to move from ready to blocked without touching or merging implementation work.

Both are bounded metadata reconciliation tasks. Neither requires CI diagnosis or code mutation, preserving
the intended boundary before F4/F5. Both variants now have executable disposable fixture blueprints,
authoritative protected-state snapshots, exact structured reports, trajectory-sensitive bounded-mutation
evaluation, and disposable lifecycle coverage; live three-agent smoke calibration is complete.

### F4 checkpoint

The fourth pair is frozen around two different CI-authority problems using completed, deterministic
workflow evidence:

- **F4-A:** the required workflow really fails on the current PR head. Failed-job evidence plus repository
  state show that the PR advances the project protocol/API level while leaving a release manifest stale.
  The only authorized mutation is one accurate diagnostic PR comment; implementation and Actions state
  remain protected.
- **F4-B:** an alert issue references a genuine required-check failure, but that run belongs to an older PR
  head. The current head passes the required workflow while a separate advisory workflow fails. CI policy
  makes the advisory signal non-blocking, so only the stale alert issue is reconciled.

Both scenarios require evidence-before-write partial-order semantics without dictating which evidence source
must be inspected first. Neither requires fresh workflow execution during the agent turn.

### F5 checkpoint

The fifth pair is frozen as the first authorized repository-content mutation family:

- **F5-A:** a well-scoped HTTP 429 retry defect has protected acceptance tests that already define the
  behavior. The agent must change only the product source, create an isolated branch, and prepare one open
  review PR linked to the still-open issue. Semantic correctness is validated independently of exact source
  syntax.
- **F5-B:** a release source of truth is already correct while two policy-defined maintenance mirrors are
  stale. The agent must synchronize exactly those two non-product artifacts and prepare one open review PR,
  with grouped or separate file-write routes both accepted.

The pair introduces branch/file/PR write permissions while keeping default-branch writes, workflow mutation,
merge authority, and unrelated project state protected. Both variants now have executable disposable fixtures,
immutable-SHA post-state reads, semantic/structured terminal validation, trajectory-sensitive Boundary scoring,
and exact-delete lifecycle coverage; live three-agent smoke calibration remains pending.

### F6 checkpoint

The capstone pair is frozen around two end-to-end handoff topologies:

- **F6-A:** a release blocker plus completed candidate-branch CI identifies a deterministic manifest/protocol
  mismatch. Repository policy requires a bounded repair PR against the non-default release branch, followed
  by an issue transition from investigation to fix-in-review while the blocker remains open and unmerged.
- **F6-B:** an existing draft PR breaks legacy configuration compatibility and carries incomplete docs. The
  agent must repair that same head branch in place, preserve protected tests/workflows, mark the same PR ready
  for review, and reconcile the linked issue without creating replacement work or claiming new-head CI passed.

Both deliberately separate "prepared for review" from "merged/released/CI-passed" and use trusted post-run
semantic validation rather than runner timing as the scientific correctness oracle.

## Phase C - cross-scenario calibration

- [x] Check design-level A/B independence within every family. *(Pilot calibration remains pending.)*
- [x] Check design-level within-family difficulty intent. *(Empirical pilot calibration remains pending.)*
- [x] Check progression from orientation through multi-stage work.
- [x] Ensure the matrix contains read-only, conditional-mutation, no-op, and mandatory-mutation cases.
- [x] Ensure no single habitual route or artifact type dominates the experiment by construction.
- [~] Confirm deterministic fixture reset/isolation for every scenario during implementation planning. The earlier shared-world coexistence path is qualified for F1-A/F1-B engineering use, but final acquisition is pivoting to one disposable repository per run.
- [x] Confirm the design specifies authoritative pre/post observations for every scored state predicate.
- [x] Freeze the design-level 288-run acquisition target.

## Phase D - pre-coding gate

**Closed on 2026-11-07. Historical PAT-era baseline.**

- [x] Pin GitHub MCP Server v2.0.3 and qualified image digest.
- [x] Capture/freeze the 43-tool effective catalog and normalized digest.
- [x] Freeze the nine laboratory-protection exclusions.
- [x] Freeze subject/controller credential profiles; omit unavailable fine-grained-PAT Checks permission.
- [x] Confirm dedicated repository `acmm-mcp-arena-experiment-2`.
- [x] Create dedicated subject/controller PATs.
- [x] Freeze fixture reset/isolation and merge-containment strategy.
- [x] Freeze reusable completed-CI evidence strategy.
- [x] Explicitly announce transition to executable implementation.

## Phase E - executable apparatus implementation

> This checklist records the apparatus/scenario implementation checkpoint before the GitHub App / Campaign rebase.
> Items such as the 43-tool PAT surface remain historical evidence; Phase F below defines the current acquisition model.


- [x] Generalize Core secret bindings to Core / Experiment / Integration scopes.
- [x] Retire `--ollama-api-key-file`; provider telemetry now resolves only `core:ollama_api_key`.
- [x] Add Experiment Package schema v0.3 package-secret declarations/runtime resolution.
- [x] Create Experiment 2 package manifest and frozen 12-scenario Contract.
- [x] Implement pinned v2.0.3 GitHub MCP integration with toolsets + exclusions.
- [x] Enforce exact 43-tool discovery and qualified image digest.
- [x] Keep qualification and Experiment 2 local MCP resources isolated (Experiment 2 uses port 8083).
- [x] Add package-scoped integration/secret/catalog regressions under repository `tests/`.
- [x] Explicitly initialize/upgrade the versioned local secret registry, preserving the qualification binding.
- [x] Bind real subject/controller PAT files through the new registry on the user's machine.
- [x] Run live `package apply` / `env doctor --start-if-needed` preflight with exact 43-tool parity.
- [x] Keep `expected_tools` as a discovery invariant only; subject adapters consume the server-exposed catalog.
- [x] Implement trusted controller runtime/doctor foundation and REST primitives.
- [x] Pin resolved repository full name `Dufferin125/acmm-mcp-arena-experiment-2` + numeric repository ID `1447536932` from live controller doctor.
- [x] Implement explicit trusted fixture-base initialization on the pinned repository identity.
- [x] Live-initialize and verify the trusted fixture base repository.
- [x] Implement scenario fixture materialization/reset for F1-A/F1-B through F6-A/F6-B using package-owned blueprints in the disposable per-run lifecycle.
- [x] Add trusted `qualify_disposable_repositories` apparatus action covering controller create/delete and subject dynamic write access with exact repository-ID deletion guards.
- [~] Live-qualify disposable repository create/write/delete lifecycle and stress repeated cycles. One real create/subject-write/controller-read/delete probe has passed; repeated stress remains pending.
- [x] Convert F1-A/F1-B fixed-repository materializers into package-owned blueprints instantiated into fresh run repositories. Both F1 scenarios now use the Core typed disposable lifecycle; the engineering-reference actions remain available only for qualification/debugging.
- [x] Implement route-independent scenario evaluators for F1 through F6.
- [x] Pilot/smoke the fixture lifecycle before scientific acquisition. F1 through F6 are live qualified.
- [x] Replace endpoint-local GitHub throttling with a shared provider request governor, persistent rolling content ledger, and execution-level API telemetry.
- [x] Add generic Core materialization resource-governor hooks plus canonical `execution_resource_usage.yaml`; Experiment 2 forecasts from historical max × 1.25, prefers provider-observed primary limits, imports legacy usage as a seed, and uses configured content caps only as the secondary-limit fallback.
- [~] Complete the pre-acquisition provider-volume reduction pass. The frozen direction is to move package-owned Git content/history off per-file REST mutations and onto a batched Git transport while reserving REST mutations for GitHub-native semantic objects.

See [`pre_coding_checkpoint.md`](pre_coding_checkpoint.md), [`pinned_mcp_catalog.md`](pinned_mcp_catalog.md),
and [`fixture_lifecycle.md`](fixture_lifecycle.md).

## Phase F - Campaign + GitHub App rebase

**Implemented and live-qualified on 2026-11-11; whole-package acquisition profiling remains pending.**

- [x] Introduce generic Core subject-admission orchestration so run environment preparation precedes ephemeral credential binding.
- [x] Keep static GitHub MCP subject profiles unadmitted between runs.
- [x] Replace the persistent subject PAT with one repository-scoped GitHub App installation token per logical run.
- [x] Freeze the App-native seven-toolset / 42-tool catalog and exclude `context/get_me`.
- [x] Preserve the pinned GitHub MCP Server v2.0.3 image/digest.
- [x] Attach only the prepared disposable repository to the selected-repository App installation before minting the run token.
- [x] Revoke the installation token and restore the unadmitted subject profile before trusted post-run observation.
- [x] Detach and retire the exact disposable repository after observation.
- [x] Add a durable non-secret runtime resource ledger for repository/admission lifecycle state.
- [x] Add package-owned hard-crash recovery using execution-tag discovery plus ledger reconciliation.
- [x] Ensure lost token bytes are never persisted; recovery removes their sole repository authority by detaching/deleting the exact run repository.
- [x] Add App-token mint/revoke, runtime admission, and crash-recovery regression coverage.
- [x] Bind/validate the package `github_app_private_key` in the live secret registry for the rebased package revision.
- [x] Run fresh live package apply/doctor and App-native 42-tool admission preflight across Hermes, Open WebUI, and Agent Zero.
- [x] Re-run disposable-repository/App-token lifecycle qualification and complete a clean F1-A Campaign admission run across all three subjects.
- [x] Confirm Campaign partial merge with three accepted observations and no blocked runs after Agent Zero admission polling correction.
- [x] Separate controller/App primary-rate telemetry domains and bring App-token mint/revoke under shared provider pacing/secondary-cooldown telemetry.
- [ ] Run one whole-package one-repetition Campaign qualification (12 scenarios x 3 subjects = 36 runs) and use its provider-volume profile to freeze final execution chunking.

### GitHub best-practice hardening checkpoint (2026-11-12)

The provider-volume qualification exposed endpoint-specific secondary limiting during disposable repository
creation, so GitHub etiquette is now a package hard floor rather than an optional tuning layer.

- Trusted REST/App requests are serialized across processes, conservatively spaced, and all mutative requests
  are separated by at least two seconds (stricter than GitHub's one-second recommendation).
- Provider cooldowns stop trusted REST, App, and remote Git traffic together; `Retry-After`, primary reset
  headers, and bounded exponential secondary recovery are authoritative.
- Repeated REST reads use authenticated conditional requests and all polling goes through the shared poll
  scheduler with a two-second local floor plus `X-Poll-Interval` support.
- Remote Git is separately paced at at most five pushes/minute/repository and ten read operations/second,
  stricter than GitHub's published repository guidance.
- Package-owned commit graphs are built locally and batched into one push whenever intermediate remote state
  is not scientifically meaningful. Individual commits and their intended history are preserved.
- REST-side ref mutations explicitly invalidate the Git transport's short freshness hint before subsequent
  local writes.
- Static regression audits reject scenario-local HTTP clients, remote Git commands, and polling sleeps.

A fresh live re-profile is required before resuming the 36-run whole-package qualification.


## Subject-side MCP provider-governor checkpoint (2026-11-12)

- [x] Preserve the exact 42-tool App-native catalog and v2.0.3 upstream commit.
- [x] Build a package-owned governed MCP image from upstream commit `b98d115bbb080e9555466a96656ec4df605aea21`.
- [x] Inject provider-authoritative pacing below both upstream REST and GraphQL GitHub clients without changing MCP tool semantics.
- [x] Serialize subject-originated GitHub HTTP requests and enforce conservative request/mutation spacing.
- [x] Persist non-secret subject cooldown/backoff state across MCP container restarts.
- [x] Verify local image upstream/governor identity during package apply and doctor.
- [x] Keep all GitHub-specific subject-governor implementation inside the Experiment Package; Core remains generic.

## Maintained MCP governor source rebase checkpoint (2026-11-12)

- [x] Fork the official GitHub MCP Server into `hqi125/acmm-github-mcp-server` and anchor `acmm/governor-v1` at upstream v2.1.0 commit `4bcdcdf8d7beee98c9448e73e257308280924cc4`.
- [x] Move the ACMM subject traffic governor into ordinary maintained Go source with focused governor tests and a full upstream regression pass.
- [x] Preserve process-wide pacing, provider-directed cooldowns, persisted non-secret telemetry, local sentinel rejection, cancellation semantics, and no automatic mutation replay.
- [x] Replace the Experiment Package's source-rewriting Docker build with an exact maintained-fork source checkout and source-commit image identity.
- [x] Keep the seven selected toolsets and the normalized 42-tool acquisition assertion unchanged; explicitly disable feature flags and insiders mode for v2.1.0.
- [x] Preserve the earlier v2.0.3 package-owned governor milestones above as historical implementation checkpoints rather than rewriting them as if they had never occurred.


## Scenario materialization checkpoint - F2 family (2026-11-12)

- [x] Extend shared scenario materialization from F1-A/F1-B to F2-A/F2-B without changing the 42-tool subject-visible MCP surface.
- [x] F2-A restores the complete pristine incoming-issue state after legitimate bounded duplicate triage, including state, labels, and run-created comments.
- [x] F2-B restores reversible accidental drift while preserving its deliberate no-op scientific contract.
- [x] Treat new issue/PR provider-history objects as non-restorable taint; archive and retire the materialization rather than allow later observations to inherit contaminated history.
- [x] Treat Git refs that advance to non-baseline commit history as taint even when the trusted controller can force-reset the visible branch.

## Scenario materialization completion checkpoint - F3 through F6 (2026-11-12)

- [x] Extend exact shared restoration to F3-A/F3-B cross-artifact reconciliation. Authorized issue-record comments/labels are restored; unrelated issue/PR/ref/review/provider-history drift remains protected.
- [x] Extend exact shared restoration to F4-A/F4-B CI diagnosis/reconciliation. Completed baseline Actions evidence is reusable, while any new workflow execution is hard non-restorable taint.
- [x] Preserve fresh repository-scoped App admission for every run even when the repository is shared by the scenario slice.
- [x] Keep F5-A/F5-B run-isolated because the required successful handoff creates a new branch/commit/PR whose provider history cannot be erased exactly.
- [x] Keep F6-A run-isolated for the same new repair-branch/PR reason.
- [x] Keep F6-B run-isolated because a correct run necessarily advances the existing PR head with new Git history; resetting the visible branch would not erase those commits/provider history.
- [x] Freeze the policy that scalability optimization must not redefine non-restorable provider history as reversible merely to increase sharing.
- [ ] Run broad/full per-scenario acquisition qualification across the new materialization policy and use real failures to drive the remaining hardening pass.
