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

The package now has two complementary provider-governor boundaries. The trusted controller runtime owns a provider-scoped governor shared by controller REST, GitHub App lifecycle requests, and trusted remote Git operations. Separately, the maintained ACMM GitHub MCP v2.1.0 fork governs the server's outbound GitHub HTTP transports so subject-originated REST/GraphQL traffic is serialized and paced below the unchanged 42-tool MCP surface. No GitHub-specific behavior is added to ACMM Core.

GitHub request-level rate limiting remains provider-authoritative. Ordinary requests do not stop merely because a local estimate predicts exhaustion: provider `X-RateLimit-*`, `Retry-After`, and observed secondary-limit responses remain authoritative for request-level backoff. The persisted rolling content ledger and configured numeric caps now have one additional, explicitly conservative role at the *materialization admission* boundary: when GitHub exposes no queryable secondary-limit status, they are used as fallback headroom checks before starting another expensive scenario slice. The active policy is:

- serialize every trusted REST/App request and conservatively keep at least 250 ms between request starts;
- keep at least two seconds between trusted `POST`/`PATCH`/`PUT`/`DELETE` requests, deliberately stricter
  than GitHub's published one-second minimum;
- continuously record `X-RateLimit-*` headers separately for controller/App/installation credential domains;
- when GitHub reports primary exhaustion (`X-RateLimit-Remaining: 0`), wait until the provider's
  `X-RateLimit-Reset` time plus a small clock/propagation grace period;
- when GitHub reports a secondary limit, pause the entire trusted GitHub plane, honor `Retry-After` plus a
  small three-second boundary grace when present, and otherwise use GitHub's documented minimum one-minute
  wait with bounded exponential fallback delays of 1/2/4/8/16 minutes;
- persist the provider cooldown across executions so a new process cannot forget an active GitHub block;
- retry the same trusted operation after provider-directed waits up to the configured bounded recovery
  count; if GitHub is still limiting the operation, preserve the provider cooldown and fail preparation
  before subject exposure so Campaign can leave that logical run retryable rather than fabricating agent data;
- ambiguous transport failures and unrelated authorization/validation errors remain fail-closed and are
  never mutation-retried merely because the request was mutative.

The configured `60/minute` and `360/hour` content limits are therefore fallback admission bounds, not claims about a queryable provider quota. The `1,000` primary-headroom reserve is applied to a live provider-reported primary limit/remaining snapshot when one exists; if a credential domain has no current provider snapshot, admission records it as unobserved rather than inventing remaining capacity. Request-level behavior still waits on provider exhaustion/cooldown signals. The bounded secondary-retry count remains active because GitHub's best-practice guidance requires finite recovery, and GitHub notes that content-creation limits can change without notice or include undisclosed constraints.

## Subject MCP provider governor

The subject-side boundary is integration-owned and preserves the scientific MCP surface. The Experiment Package fetches the exact `local_service.source_commit` from the maintained `hqi125/acmm-github-mcp-server` fork, verifies the checkout, and builds `acmm/github-mcp-server:v2.1.0-acmm-governed-v2` using that source tree's committed Dockerfile. The fork is based on upstream v2.1.0 commit `4bcdcdf8d7beee98c9448e73e257308280924cc4`; package apply/doctor verifies image labels for the exact upstream version/commit, ACMM source commit, and governor revision.

The subject transport is the last infrastructure boundary before GitHub. Under an active ACMM Provider Gate it is fail-closed and policy-light:

- serialize outbound GitHub HTTP requests process-wide;
- ask Core for admission before every classified REST/GraphQL/raw request;
- skip the transport's ordinary 500 ms request spacing, two-second mutation spacing, and local cooldown sleeps while the Core gate is active, preventing double pacing;
- return 403/429 feedback to the same Core decision so provider-directed recovery is actuated once by Core;
- fail closed before GitHub if the active gate cannot be reached or authenticated;
- outside an active gate, retain the conservative local spacing plus `Retry-After`, reset, and bounded 1/2/4/8/16-minute recovery as fallback protection;
- persist only non-secret cooldown/backoff and aggregate traffic counters (request/mutation counts, method counts, and primary/secondary-limit event counts) to the integration resource volume so an MCP restart cannot forget an active provider block and later qualification can measure subject-plane load;
- reject the package's non-secret unadmitted sentinel locally before it can generate any GitHub network request; Agent Zero instead starts with no GitHub MCP server configured and uses provider revocation between live runs, eliminating startup/background discovery traffic from an unusable static server;
- allow request-context cancellation to end a waiting MCP call without issuing another GitHub request; and
- never persist the admitted installation token in governor state.

The wrapper does not change tool names, schemas, prompts, or agent-visible tool-selection freedom. Inefficient agent tool choices remain observable behavior; the transport only prevents those choices from becoming uncontrolled provider traffic.

## Cross-execution ledger

The governor persists only non-secret scheduling state under:

`~/.config/acmm/provider-state/github/`

The filename is derived from a hash of the GitHub API base + repository-owner scope. The state contains
only timestamps, cooldown/backoff state, and a scope hash. It never stores PATs, request payloads, or
response bodies.

This persistence matters because repeated smoke/campaign executions target the same provider environment
and therefore must not behave as though the previous invocation's rolling content/cooldown state never
happened. Primary REST snapshots are stored separately by credential domain rather than being merged.

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
- the latest primary-rate-limit headers observed from GitHub, separated by credential domain when present.

This telemetry artifact covers the trusted controller plus App-token mint/revoke lifecycle calls. Subject MCP traffic keeps a separate `mcp_subject_api_usage.json` evidence plane and non-secret transport state in the integration resource directory; the controller and subject counters are intentionally not merged because they use different credential domains and transport stacks. During an active logical run both planes enter the same Core Provider Gate, so admission and provider-directed recovery have one actuator even though evidence remains plane-specific. The controller/MCP local governors retain conservative cooldown/spacing behavior only as fallback when no Core gate is active.

The artifact is refreshed after each normal finalization and after archive-then-delete failure handling,
so useful request-volume evidence survives later interruption.

The package also exposes:

`acmm run apparatus exec api_status`

for a read-only view of the current local governor budget/cooldown state and latest observed primary
quota snapshot. GitHub does not expose a queryable secondary-limit status, so a secondary cooldown is
known only after GitHub reports one and is then shared persistently by the governor.

## Materialization admission and canonical usage

Experiment 2 now attaches a package-owned execution resource governor to the generic Core execution service. It is not implemented in `acmm run` or `acmm campaign`; both entry points delegate to the same `execute_experiment()` materialization boundary and therefore receive identical admission behavior.

Each execution with this package writes Core's canonical:

`execution_resource_usage.yaml`

The artifact contains one admission record and one measured usage record per materialization slice. The package forecast is intentionally simple for the proof of concept: maximum observed historical usage per dimension multiplied by a 1.25 safety factor. Completed canonical resource-usage records are preferred. For migration, the package can also import prior sibling `apparatus_api_usage.json` artifacts as seed samples so already-collected F3/F4 executions remain useful.

Admission precedence is:

1. latest provider `X-RateLimit-*` observations for primary credential-domain capacity;
2. persisted provider cooldown/rate state carried by the existing governor;
3. configured rolling content caps only where GitHub exposes no queryable secondary-limit status.

The package never manufactures a secondary `remaining` value. A forecast larger than one configured content window is admitted only from a maximally clear local window and marked as requiring in-slice pacing. During an active logical run the Core Provider Gate is responsible for dynamic per-request progress; the controller/MCP governors provide fallback safety only when that gate is inactive.

Cold start requires no CLI flag. With no historical sample, the first slice is recorded as `cold_start` and is admitted using current provider/cooldown state plus existing request-level controls. Its measured delta is appended to the in-memory history immediately and becomes a forecast sample for the next materialization in the same execution.

`apparatus_api_usage.json` remains the detailed whole-session diagnostic artifact. The new YAML is the stable execution-facing interface for admission history and per-materialization measured deltas.

## Provider semantics already centralized

The GitHub controller currently owns these provider-specific rules:

1. bounded TLS-handshake retry only when the HTTP request could not yet have crossed the connection;
2. exact head-SHA PR merge requests plus mergeability convergence and transient base-race handling;
3. immutable-SHA content verification after branch-changing fixture operations;
4. convergence of GitHub-created default labels into package-owned definitions before subject exposure;
5. bounded eventual-consistency waits for package-owned list/discovery surfaces, routed through one poll
   scheduler with a two-second local floor and provider `X-Poll-Interval` support;
6. non-redirecting Actions-log/archive API hops followed by credential-free signed-URL downloads, with both hops admitted by the traffic-control plane (`rest` then `raw`);
7. archive-then-delete invalid-run cleanup with exact repository-ID verification;
8. provider-authoritative primary/secondary rate-limit interpretation with persistent cooldown state;
9. session-level provider request telemetry with route-family breakdowns;
10. credential-domain primary-rate snapshots, so controller/App primary state is never conflated;
11. App-token mint/revoke admission and provider recovery through the universal Core Provider Gate, with controller telemetry retained separately;
12. authenticated conditional GETs (`ETag`/`Last-Modified`) for repeated REST reads within one controller
   lifetime, so unchanged polling responses can use GitHub's conditional-request path;
13. a provider-clear gate shared with remote Git fetch/`ls-remote`/push operations so a REST secondary block
   stops all trusted GitHub traffic, not only REST;
14. package-config hard floors that reject mutation spacing weaker than one second, push pacing above six
   pushes/minute/repository, or remote Git-read pacing above fifteen operations/second/repository.

These should be treated as one control plane. New GitHub API behavior should be added here rather than
as scenario-local sleeps or string checks.

## Pre-acquisition request-volume reduction

The governor prevents avoidable provider abuse, but waiting efficiently is not enough for 288 runs.
The repository content/history plane is therefore separated from GitHub-native collaboration state.

Implemented controller behavior:

1. **Git transport owns repository file writes and ref-addressed file reads.** The private scenario-slice
   repository is created through REST once at materialization, while package-owned commit graphs are
   built locally in an authenticated Git workspace and pushed without using the Contents REST endpoint.
   Multiple package-owned commits are batched and published in one push whenever no intermediate remote
   state is scientifically meaningful; the individual commits and commit messages remain intact. The lifecycle
   defines an explicit **initial publication phase** for fresh disposable repositories: trusted fixture-base commits
   and scenario-owned commits that have no remote dependency enter the same outer Git batch and are flushed once.
   A materializer boundary is not a publication barrier. Additional pushes are permitted only after an explicit
   semantic dependency on already-published refs/history (for example, create a branch from the published main
   head and then populate that branch). Ref- or
   commit-addressed controller reads are fetched/read through Git as well. The existing
   `create_or_update_file()` controller contract is preserved, so scenario materializers do not encode
   transport choice. Fake/custom controller transports retain the REST path for deterministic tests.
2. **Credentials stay out of URLs and process arguments.** Git HTTPS authentication uses an ephemeral
   `GIT_ASKPASS` helper whose script contains no credential; the PAT is supplied only through the child
   process environment.
3. **REST remains the GitHub collaboration/control plane.** Repository create/delete, issues, labels,
   pull requests, comments, reviews, Actions metadata, and lifecycle transitions remain API-managed.
4. **Git transport is separately observable but participates in the active-run Provider Gate.** Execution telemetry
   carries Git command, fetch, push, commit, file-read/write, ref-fingerprint, and wait counters alongside REST
   telemetry. During an active logical run, Git push/fetch/ls-remote receives Core admission/result accounting and
   the same quiet 1-second request / 2-second mutation baseline used by the other gated planes. The historical
   twelve-second push and 100 ms remote-read spacing remains only as a conservative fallback when no Core gate
   owns the operation; it is never stacked on top of Core actuation.
5. **Keep remote prefetch forbidden.** Lower request volume must not reintroduce future-run repositories
   while an active subject can discover them.

Before the stable full acquisition, the apparatus completed the required live re-qualification and
whole-package Campaign checks. The frozen path retains the post-batching Git content plane, stricter provider
pacing, canonical Git `ref -> SHA` fingerprint, and conditional-request fast paths. Additional transport
optimization is outside the frozen Experiment 2 lineage unless introduced as a new package revision.

The target is not merely fewer API calls. It is a reproducible provider control plane whose traffic,
waiting, retries, and failure semantics are all explicit evidence rather than hidden timing behavior.

## Deliberate transport exceptions and external boundary

Two network behaviors are intentionally not treated as ordinary authenticated REST requests:

- Actions job logs and repository archives first use the fully governed, non-redirecting REST endpoint. The
  returned signed redirect target is then downloaded without the controller credential. This second hop remains
  inside the same traffic-control plane as a `raw` provider request: Core/governor admission, serialization, and
  telemetry still apply even though no GitHub REST credential is forwarded to the signed download host.
- Live subject MCP traffic is generated inside the pinned ACMM GitHub MCP Server fork. Governor v2 now provides
  a synchronous fail-closed bridge to the Core Provider Gate: during an active logical run each REST/GraphQL/raw
  request is admitted by Core and provider feedback/recovery returns on the same decision. The MCP governor skips
  its own proactive spacing/cooldown sleeps while the gate is active and retains its conservative 1s/2s fallback
  only when no ACMM gate is active.

The package test suite contains a static best-practice audit that rejects new direct `urllib`/HTTP clients in
scenario modules, direct remote Git commands outside the Git content plane, and scenario-local polling sleeps.
New provider interactions must therefore enter through the shared transport layers or fail regression tests.

## Measured F4 qualification profile

The first governor-qualified six-cell F4 smoke was recorded under the **historical per-run disposable-repository
topology**. It completed with all six runs valid and all six repositories deleted by exact identity. Trusted
controller/probe traffic for that execution was:

- 695 REST requests total;
- 90 mutative REST requests;
- 84 locally reserved content-generating requests;
- 45 Contents-API writes;
- 6 Git-ref creations;
- 12 workflow dispatches;
- 48 Actions job-log API redirects;
- 557 reads in the original coarse telemetry bucket.

That historical topology produced about 14 content-generating trusted requests and 116 trusted REST requests per
scientific run before subject MCP traffic. Its naive 288-run projection (roughly 4,032 content mutations and
33,360 trusted REST requests) is retained only as historical sizing evidence; it is **not** the current scenario-slice
traffic model. The profile remains useful because
other scenario families have different fixtures and agents generate additional shared-user REST traffic.
That profile established two requirements that were carried into the acquisition apparatus:

1. do not respond to provider pressure by raising locally guessed quotas; reduce demand and follow GitHub's
   provider-directed cooldown/reset signals;
2. migrate repository content/history traffic away from the provider-heavy path and re-qualify before
   the stable 288-run acquisition.

The F4 profile also motivated the finer read-route telemetry retained by the later control-plane
revision so repository, content, PR, issue, Actions-run, job, and log reads are not collapsed into one
generic `read` counter.

## Measured F6 capstone profile before Git transport

The historical six-cell F6 family smoke likewise used the older per-run repository topology. It completed with
all six runs valid, all six repositories deleted by exact identity, and no secondary-limit event. Its trusted
controller/probe traffic was:

- 714 REST requests total;
- 105 mutative REST requests;
- 99 locally reserved content-generating requests;
- 51 Contents-API writes;
- 211 Contents-API reads;
- 9 Git-ref REST creations;
- 6 workflow dispatches;
- 12 Actions job-log redirects.

Those measurements are the direct reason the transparent Git content plane replaced controller
Contents writes and ref-addressed Contents reads before the stable full acquisition.

## Repository mutation fingerprint fast-path

GitHub does not expose one authoritative repository-wide "unchanged" bit. The apparatus therefore treats
change detection as a composition of authoritative surfaces rather than one timestamp or repository field.
The frozen mutation-detection fast-path is:

1. **Git content/history sentinel:** record a canonical sorted mapping of repository refs to immutable commit
   SHAs. If the ref set and every ref SHA are unchanged, reachable branch/tag history has not moved. The frozen implementation can obtain this mapping through Git transport (`ls-remote`) without
   consuming the REST primary budget.
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


## Provider Pressure Heuristics

The materialization/subject-slice resource forecast remains factual quota accounting, while Provider Pressure Heuristics (PPH) adds adaptive learned admission below provider-facing request paths. Core owns profile persistence, Event-PPH updates, generic APP probe lifecycle/suspension, active-run Provider Gate actuation, provider-recovery correlation, and immutable trajectory export. This package injects the GitHub feature model in `assets/provider_pressure.json`; see `design/provider_pressure_heuristics.md` for the complete model and F5-A/F5-B bootstrap rationale. During an active logical run the Core Provider Gate replaces local proactive governor pacing for participating requests; local governors remain fallback-only. PPH/APP still do not claim to reconstruct GitHub's hidden secondary-limit policy.

### Scenario-slice provider lifecycle

Provider-costly fixture construction follows the package-defined scenario materialization instead of a logical-run repository lifecycle. F1-F6 create one repository per scenario slice, publish the static scenario base at semantic Git-history barriers, and then execute many logical runs in Core's subject-major order. Repository creation therefore occurs once per slice rather than once per observation.

The active-run Provider Gate now covers classified subject-MCP REST/GraphQL/raw requests, trusted controller/App REST requests, and Git smart-protocol admission/result accounting. APP observes a run-local controller+MCP burst window instead of using one special token-mint checkpoint, so burst-density evidence accumulates across the provider traffic that actually occurs between meaningful APP boundaries. Controller and subject-MCP usage remain separate evidence planes. Run-owned active GitHub objects are restored/retired after post-state capture; allowed closed/unmerged history remains slice-owned evidence, while unexpected durable mutation taints and retires the slice.
