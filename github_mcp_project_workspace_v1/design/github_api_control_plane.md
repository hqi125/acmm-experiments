# GitHub API control plane

## Decision

The trusted GitHub controller now treats provider API behavior as one shared apparatus concern rather
than a collection of endpoint-local sleeps and retries.

The boundary remains deliberately package/integration-side:

- ACMM Core owns generic lifecycle, evidence, package, and execution contracts.
- The GitHub apparatus owns GitHub-specific request semantics, rate-limit interpretation, redirects,
  mergeability convergence, eventual-consistency handling, and provider request budgeting.
- Scenario evaluators consume authoritative state and normalized tool evidence; they do not implement
  provider transport policy.

This boundary may later be extracted into a reusable GitHub integration repository. It should not be
moved into Core merely because several scenarios use it.

## Shared request governor

One controller runtime now owns one provider-scoped governor shared by the controller and trusted
subject-visibility probe clients. The governor coordinates all scientific runs in an execution instead
of allowing each endpoint/run to rediscover the same provider block independently.

The default ACMM safety policy is intentionally below GitHub's documented generic secondary content
creation ceilings:

- at least 1 second between mutative REST requests;
- at most 60 locally reserved content-changing trusted-controller requests in a rolling minute;
- at most 360 locally reserved content-changing trusted-controller requests in a rolling hour;
- preserve at least 1,000 requests of the latest observed shared primary REST quota for subject MCP traffic;
- wait through the provider reset window plus a small grace period before the controller consumes that reserve;
- explicit secondary-limit responses create a shared provider cooldown;
- fallback secondary backoff is 60, 120, 240, 480, then 600 seconds;
- a request may retry a provider-declared secondary limit up to five times;
- ambiguous transport failures are still fail-closed and are not mutation-retried.

The minute/hour budgets are ACMM safety budgets, not assertions that GitHub's unpublished or mutable
provider thresholds are exactly those values. Capacity is reserved before a content-generating request
is sent, so failed responses and process interruption cannot make the local ledger under-count traffic.
The budgets deliberately reserve capacity for subject-originated GitHub MCP activity, which is outside
the trusted controller's direct request ledger.

## Cross-execution ledger

The governor persists only non-secret scheduling state under:

`~/.config/acmm/provider-state/github/`

The filename is derived from a hash of the GitHub API base + repository-owner scope. The state contains
only timestamps, cooldown/backoff state, and a scope hash. It never stores PATs, request payloads, or
response bodies.

This persistence matters because repeated smoke executions share the same GitHub account and therefore
the same provider-side rolling windows. A new `acmm run` should not behave as though the previous run's
content-generation traffic never happened.

The state root can be overridden for isolated testing with `ACMM_GITHUB_PROVIDER_STATE_ROOT`.

## Execution telemetry

Every disposable scientific session writes/refreshes:

`apparatus_api_usage.json`

inside the execution directory. The artifact contains:

- governor policy;
- controller/probe request counts;
- mutation/content-changing counts;
- response-status counts;
- accumulated pacing/cooldown wait time;
- coarse endpoint-family counts;
- rolling content-window state at the end of the observation;
- the latest primary-rate-limit headers observed from GitHub, when present.

This telemetry covers the trusted controller and trusted subject-visibility probe. Live subject MCP
traffic is not intercepted or counted by ACMM. Controller and subject credentials intentionally
authenticate as the same GitHub owner, so their user-authenticated REST traffic shares one primary
quota. The primary-rate reserve therefore protects subject execution as well as leaving ordinary
provider headroom.

The artifact is refreshed after each normal finalization and after archive-then-delete failure handling,
so useful request-volume evidence survives later interruption.

The package also exposes:

`acmm run apparatus exec api_status`

for a read-only view of the current local governor budget/cooldown state and latest observed primary
quota snapshot. GitHub does not expose a queryable secondary-limit status, so a secondary cooldown is
known only after GitHub reports one and is then shared persistently by the governor.

## Provider semantics already centralized

The GitHub controller currently owns these provider-specific rules:

1. bounded TLS-handshake retry only when the HTTP request could not yet have crossed the connection;
2. exact head-SHA PR merge requests plus mergeability convergence and transient base-race handling;
3. immutable-SHA content verification after branch-changing fixture operations;
4. convergence of GitHub-created default labels into package-owned definitions before subject exposure;
5. bounded eventual-consistency waits for package-owned list/discovery surfaces;
6. non-redirecting Actions-log/archive API hops followed by credential-free signed-URL downloads;
7. archive-then-delete invalid-run cleanup with exact repository-ID verification;
8. shared secondary-rate-limit cooldown and proactive local content budgets;
9. session-level provider request telemetry with route-family breakdowns;
10. a shared-primary-rate reserve that stops trusted controller traffic before it can starve the
    subject credential.

These should be treated as one control plane. New GitHub API behavior should be added here rather than
as scenario-local sleeps or string checks.

## Pre-acquisition request-volume reduction

The governor prevents avoidable provider abuse, but waiting efficiently is not enough for 288 runs.
The repository content/history plane is therefore separated from GitHub-native collaboration state.

Implemented controller behavior:

1. **Git transport owns repository file writes and ref-addressed file reads.** The private disposable
   repository is still created through REST at the start of its run, but package-owned file commits are
   created in a local authenticated Git workspace and pushed without using the Contents REST endpoint.
   Ref- or commit-addressed controller reads are fetched/read through Git as well. The existing
   `create_or_update_file()` controller contract is preserved, so scenario materializers do not encode
   transport choice. Fake/custom controller transports retain the REST path for deterministic tests.
2. **Credentials stay out of URLs and process arguments.** Git HTTPS authentication uses an ephemeral
   `GIT_ASKPASS` helper whose script contains no credential; the PAT is supplied only through the child
   process environment.
3. **REST remains the GitHub collaboration/control plane.** Repository create/delete, issues, labels,
   pull requests, comments, reviews, Actions metadata, and lifecycle transitions remain API-managed.
4. **Git transport is separately observable.** Execution telemetry now carries Git command, fetch, push,
   commit, file-read/write, and ref-fingerprint counters alongside REST route-family telemetry.
5. **Keep remote prefetch forbidden.** Lower request volume must not reintroduce future-run repositories
   while an active subject can discover them.

Still pending before stable full acquisition:

- live re-profile the implemented Git content plane and compare it with the F4/F6 REST-heavy baselines;
- use the canonical Git `ref -> SHA` fingerprint as the content/history change sentinel;
- add conditional ETag sentinels for scenario-relevant GitHub-native REST surfaces where this materially
  reduces post-run reads without weakening authoritative evidence;
- review workflow dispatches only if the measured remaining content budget makes that optimization useful;
- run one whole-package one-repetition qualification across all 12 scenarios and all three subjects.

The target is not merely fewer API calls. It is a reproducible provider control plane whose traffic,
waiting, retries, and failure semantics are all explicit evidence rather than hidden timing behavior.

## Measured F4 qualification profile

The first governor-qualified six-cell F4 smoke completed with all six runs valid and all six disposable
repositories deleted by exact identity. Trusted controller/probe traffic for that execution was:

- 695 REST requests total;
- 90 mutative REST requests;
- 84 locally reserved content-generating requests;
- 45 Contents-API writes;
- 6 Git-ref creations;
- 12 workflow dispatches;
- 48 Actions job-log API redirects;
- 557 reads in the original coarse telemetry bucket.

This is about 14 content-generating trusted requests and 116 trusted REST requests per scientific run
before subject MCP traffic. Naively projecting that profile to 288 runs yields roughly 4,032 content
mutations and 33,360 trusted REST requests. The projection is intentionally only a sizing signal because
other scenario families have different fixtures and agents generate additional shared-user REST traffic.
It is nevertheless sufficient to make two pre-acquisition requirements explicit:

1. do not relax the 360/hour content safety budget merely to increase throughput; reduce demand;
2. complete the repository content/history transport migration and then re-profile before launching the
   stable 288-run acquisition.

The F4 profile also motivated finer read-route telemetry in the next control-plane revision so future
smokes can distinguish repository, content, PR, issue, Actions-run, job, and log reads rather than
collapsing them into one generic `read` counter.

## Measured F6 capstone profile before Git transport

The final six-cell F6 family smoke completed with all six runs valid, all six repositories deleted by
exact identity, and no secondary-limit event. Its trusted controller/probe traffic was:

- 714 REST requests total;
- 105 mutative REST requests;
- 99 locally reserved content-generating requests;
- 51 Contents-API writes;
- 211 Contents-API reads;
- 9 Git-ref REST creations;
- 6 workflow dispatches;
- 12 Actions job-log redirects.

Those measurements are the direct reason the transparent Git content plane now replaces controller
Contents writes and ref-addressed Contents reads. The next live re-profile must demonstrate the reduction
before the stable full acquisition is allowed to start.

## Repository mutation fingerprint fast-path

GitHub does not expose one authoritative repository-wide "unchanged" bit. The apparatus therefore treats
change detection as a composition of authoritative surfaces rather than one timestamp or repository field.
The planned pre-acquisition fast-path is:

1. **Git content/history sentinel:** record a canonical sorted mapping of repository refs to immutable commit
   SHAs. If the ref set and every ref SHA are unchanged, reachable branch/tag history has not moved. This can
   later be implemented with Git transport (`ls-remote`) so it does not consume the REST primary budget.
2. **GitHub-native conditional sentinels:** retain ETags for stable, scenario-relevant REST collections and
   records (issues/comments, pull requests/reviews, labels, workflow/run state, and other protected native
   objects). Post-run checks send `If-None-Match`; a 304 is treated as an unchanged representation and avoids
   a primary-rate-limit charge under GitHub's documented conditional-request semantics.
3. **Trajectory ledger:** normalized successful subject mutations remain independent evidence. An attempted
   and later-restored forbidden mutation is still a Boundary signal even when every final sentinel matches.
4. **Escalation only on dirtiness:** if a ref SHA changes or a conditional request returns a changed
   representation, fetch the full authoritative surface and compute the existing normalized post-state digest.
   Headline scoring continues to use authoritative state, never a heuristic repository timestamp.

Repository-level `updated_at`/`pushed_at` values and webhooks may be retained as diagnostic hints, but they are
not sufficient proof that the complete experiment-defined surface is unchanged. Webhooks are asynchronous;
repository timestamps do not cover every GitHub-native object with the precision ACMM needs.

This fast-path must not be used to justify ahead-of-time remote run repositories. Even a repository that later
proves byte-for-byte untouched was still discoverable to another subject while it existed. The fingerprint is
for cheaper verification of the **active run world**, not for relaxing cross-run visibility isolation.
