# Provider Pressure Heuristics (PPH)

## Purpose

Provider Pressure Heuristics (PPH) is an adaptive execution-support layer for external services whose practical congestion or secondary-limit behavior is only partially observable. PPH does not claim to reconstruct the provider's hidden policy and it does not replace provider-authoritative retry or rate-limit handling. Instead, it watches provider-relevant actions, learns from runtime pacing that reveals missed provider pressure, and uses the resulting feature profile to actuate future actions more conservatively.

The design principle is:

> A governor enforces a known policy. PPH learns a policy from observed provider pressure.

PPH is intentionally adaptive rather than preventive. Provider-pressure pacing is preserved as useful evidence rather than hidden as apparatus noise. Repeated exposure to the same risky traffic shape should become less likely because the learned feature profile becomes more conservative, while clean pressure-free actions slowly reward stability.

## Core and package responsibilities

ACMM Core owns the generic PPH engine:

- Provider Pressure Profile lifecycle;
- generic feature-only reward and punishment arithmetic;
- action-watchdog admission and PPH actuation;
- provider-recovery correlation and actuation;
- runtime pacing-event ingestion for compatibility/fallback evidence;
- immutable trajectory sequencing;
- hash-chained trajectory snapshots;
- atomic mutable profile persistence;
- replay de-duplication;
- execution-completion, interruption, and failure exports.

The Experiment Package injects the provider-specific metric model:

- provider and non-secret scope identity;
- model identity and model-definition hash;
- the feature vocabulary used to describe an action;
- translation of provider recovery and legacy runtime pacing into reward and punishment signals;
- historical replay of compatible prior executions;
- provider-specific policy parameters.

GitHub-specific concepts therefore remain outside Core. Core only sees generic named features, action identities, provider-recovery events, pacing events, and weighted signals.

## Event-driven vocabulary

PPH v0.13 keeps the v0.5 event-driven recovery concepts, the v0.6 Adaptive Pressure Pocket (APP), the v0.7 cold-start prior, and the v0.8 evidence-driven APP pocket geometry, then adds a separately preserved subject-MCP observation plane.

**Action** is a provider-relevant operation that is about to occur. The package supplies an action identifier and its declared feature set.

**Pacing event** is a suspension that actually happened. It records a source, reason, duration, action identifier, features, and optional metadata. Pacing is raw runtime causality, not automatically a PPH decision.

**PPH actuation** is pacing imposed by PPH before an action because the matching feature profile carries learned pressure. PPH-origin pacing is recorded for evidence but is not punishment evidence.

**Pressure feedback** is legacy/runtime-origin pacing whose provider-specific reason indicates pressure observed outside the first-class provider-recovery path. It remains supported for backward compatibility and interrupted/fallback paths.

**Provider recovery** is an explicit provider-directed wait discovered only after an action attempt is rejected by the provider. The package classifies the provider response and identifies the recovery source (`retry_after`, `rate_reset`, or `documented_fallback`); Core PPH correlates that recovery with the preceding action decision, actuates the wait, and learns only the amount by which the provider recovery exceeded the prior PPH admission wait.

The managed causal loop is therefore:

```text
action intent
    -> PPH watchdog
       -> APP may suspend independently for a learned burst pocket
       -> Event PPH may impose its per-action wait independently
    -> action attempt
    -> provider rate-limit response, if any
    -> package classifies provider recovery directive
    -> PPH correlates directive to the original action decision
    -> PPH learns admission underprediction
    -> PPH actuates the provider-directed recovery wait
    -> retry proceeds without a second ordinary PPH action admission
    -> watched action reports success/failure/interruption
    -> APP closes the probe if one was opened
```

The provider recovery wait and the learning penalty are deliberately different quantities. If PPH admitted an action after 30 seconds but the provider subsequently requires a 120-second recovery, PPH actuates the full 120-second recovery while the feature learner receives a 90-second underprediction signal. If the provider requires only 20 seconds after a 30-second PPH admission, the rejection is still preserved as recovery evidence, but the feature learner receives no wait-underprediction punishment.

## GitHub feature hierarchy

The initial GitHub model deliberately mixes common protocol/semantic features with narrow provider-specific operation features. A repository-creation request can therefore be represented at several levels:

- `protocol.http.POST`;
- `semantic.create`;
- `mutation`;
- `content_creation`;
- `resource.repository`;
- `operation.repository.create`.

A provider-pressure observation raises only the feature scores explicitly attached to that observation, with the exact operation normally receiving the strongest weight. Future actions consider only features explicitly declared by that action. Pressure therefore transfers only through visible feature overlap: for example, `repository.create` and `issue.create` may share `semantic.create` and `content_creation`, while an unrelated read action receives no hidden provider-wide penalty.

## Learning semantics

PPH separates structural action description from learned pressure. The package describes what an action looks like; the profile records how risky that traffic shape has appeared through observed pressure feedback.

A punishment signal increases the scores of the signal's declared features sharply. A clean pressure-free success produces a much smaller reward that moves those same declared features back toward the baseline but never below it. Core does not maintain a global pressure scalar for admission. Global observation/reward/punishment totals are descriptive trajectory counters only and never delay unrelated actions.

For first-class provider recovery, **underprediction duration** is part of punishment magnitude. The Event PPH path in the GitHub v0.13 model retains the v0.5 rule and computes `max(0, provider_recovery_wait - prior_pph_admission_wait)` and scales punishment severity from that value. The provider-directed wait itself is still preserved and actuated in full; it is not duplicated as another learned delay. Legacy `provider_secondary_pressure` pacing events remain interpretable through the v0.4-compatible pacing path for fallback and historical evidence.

A request that succeeds only after provider-pressure pacing is a recovery, not a clean stability reward. Clean reward resumes only on subsequent pressure-free operations.

Provider availability errors are not automatically provider-pressure signals. For example, a generic HTTP 500 is an availability event unless the provider-specific model has stronger evidence that it represents congestion. GitHub explicit secondary-limit pacing, by contrast, is direct punishment evidence.

## F5-A historical bootstrap

Execution `9583d235-2d44-4c70-9ffe-fb9d11bb9ab2` is the motivating pre-PPH baseline. Its controller telemetry recorded 24 successful `repository.create` operations, 10 secondary-limit responses on that same route, and approximately 3719 seconds of secondary-cooldown wait.

The v0.13 historical importer preserves the legacy v0.4/v0.5 interpretation for pre-recovery-arbitration artifacts: it does not reconstruct a special ladder or collapse those observations into a guessed provider episode count. It preserves the ten historical pressure observations as ten punishment events and uses their aggregate runtime pacing duration as the punishment magnitude. Because aggregate legacy telemetry cannot identify the exact successful request that followed each recovery sequence, it conservatively excludes the corresponding recovered successes from clean rewards.

The old execution remains unchanged. When PPH first starts, it replays compatible historical artifacts in chronological order and exports those replays as explicit `historical_replay` trajectory snapshots. Replay de-duplication is by exact execution identity, so a later independent F5-A execution remains new learning evidence while the same historical execution cannot be applied twice.

## Event PPH and Adaptive Pressure Pocket (APP)

GitHub PPH v0.13 deliberately separates two learners inside one persisted Provider Pressure Profile.

**Event PPH** is the existing feature learner. Each provider-recovery observation is independent evidence for the declared action features. Event PPH correlates a recovery with its admission decision, computes underprediction, applies reward/punishment arithmetic, and then forgets the retry-chain structure. It has **no episode or probe concept**. In particular, a 1→2→4→8→16 minute recovery ladder is still five recovery observations to Event PPH if five provider rejections occurred.

**Adaptive Pressure Pocket (APP)** is the higher-order burst/density learner. APP alone owns the episode abstraction, represented as an APP probe. The first relevant provider rejection after an APP-marked admission opens one probe. Further provider rejections correlated with that same admission enrich the same probe rather than creating new probes. The watched action's eventual success, terminal failure, or interruption closes the probe.

An APP probe records:

- the triggering action and feature vector;
- the Event PPH admission wait and any independent APP suspension applied before the attempt;
- the pre-action run-local usage vector and accumulation interval;
- every provider-recovery observation in the retry chain;
- total provider-recovery and Event-PPH-underprediction duration;
- the final action outcome.

Closing a probe updates one APP pressure pocket. Pockets are clustered only when the action/features match and the local usage-vector/accumulation-interval similarity clears the configured threshold. One coherent probe is **exploratory**, two are **provisional**, and three or more are **established**. Confidence therefore progresses 1/3 → 2/3 → 1.0 in the initial model. The pocket stores its center usage vector, observed min/max boundary, mean accumulation interval, recovery span, resolution counts, confidence, and stage.

### APP cold-start prior

Before a matching pocket has its second coherent probe, APP v0.13 retains the conservative documented-limit prior introduced in v0.7 as a fallback APP suspension prior. This prior is APP-owned; it is not an Event PPH episode, does not create a probe, and does not change Event PPH reward or punishment arithmetic. Once the matching empirical pocket reaches the provisional two-probe stage, the prior is disabled for that neighborhood and APP relies on empirical pocket evidence.

The reference envelope records the currently documented GitHub secondary-limit figures of 100 concurrent requests, 900 REST secondary points per minute, 80 content-generating requests per minute, 500 content-generating requests per hour, and 90 seconds of CPU time per 60 seconds. These are reference ceilings rather than claims about GitHub's hidden enforcement boundary; GitHub documents that secondary limits can change without notice and may also be triggered for undisclosed reasons.

Only dimensions that ACMM measures directly are allowed to actuate the prior. In v0.13 those are the one-minute and one-hour content-generation windows. The operational thresholds come from the controller fallback policy and are capped by the published reference ceilings. The current controller policy is 60 content requests/minute and 360/hour, so it remains more conservative than the published 80/500 figures. Concurrency is already serialized by the controller, exact REST secondary-point costs are not public for every endpoint, and provider CPU time is not directly measured; those dimensions are retained as reference metadata only and do not invent pressure.

When an actuated content window reaches its operational threshold, the governor snapshot exposes the exact time until capacity returns. APP uses that duration as its cold-start prior suspension. If an exploratory empirical pocket also matches, APP takes the stronger of those two APP-internal signals to choose one APP suspension duration. This comparison is entirely inside APP; it is not compared with Event PPH pressure.

### APP pocket geometry and safe frontier

APP v0.8 introduced the evidence-driven pressure-pocket boundary retained by v0.13 instead of treating the running center as the whole geometry. Each closed pressure probe contributes a compact pressure-support sample containing its trigger usage vector and accumulation interval. A pocket retains a bounded rolling support set and rebuilds its center and observed min/max envelope from those samples. A new coherent pressure probe that matches the pocket expands that support geometry; when old support samples eventually age out of the bounded set, the retained geometry can contract without rewriting historical probe evidence.

Pressure probes are positive pressure evidence, so APP also needs counterevidence to learn where a pressure region should stop. A watched action that succeeds with **zero total PPH admission wait** and no provider rejection is recorded as an APP safe observation. This is not a probe, opens no episode, and never changes Event PPH reward or punishment arithmetic. A success after any Event-PPH or APP admission wait is deliberately not treated as safe counterevidence, because the wait itself may have made the request safe.

Safe observations form a conservative exclusion frontier only after repeated evidence. The initial policy requires at least two nearby zero-wait successes, a pocket that has already reached the two-probe provisional stage, and more nearby safe observations than retained pressure-support samples at the candidate point. APP then compares the strongest similarity to retained pressure-support samples with the strongest nearby safe-observation similarity. If the safe evidence is numerically dominant and within the configured similarity margin, the existing pocket is blocked from claiming that point for proactive admission. Admission falls back to any remaining APP evidence, including the cold-start prior where still applicable.

The safe frontier is an admission boundary, not a rule that prevents APP from learning contradictory pressure evidence. If the provider later rejects an action at a safe-blocked point, the normal APP probe is still assigned to the best pressure-supported pocket without the safe exclusion applied; the new positive sample can therefore reclaim that region if pressure evidence becomes dominant. A new linked pocket is created only when a closed pressure probe is too geometrically dissimilar to every existing same-action/same-feature pocket to clear the configured support threshold. That pocket records `split_from_pocket_id` pointing to the nearest prior pressure region. This is the v0.8 split rule: distinct pressure support creates a split, while safe/pressure contradictions remain auditable competing evidence instead of causing repeated pocket fragmentation.

APP is a separate suspension gate inside the same Core actuation surface, not another Event-PPH pressure score. The package returns an APP suspension duration when the current density/interval geometry falls inside a learned red-line pocket. Core actuates that suspension independently, then applies the ordinary Event-PPH per-action wait, if any. The two controls are never collapsed through `max(Event PPH, APP)`, and APP never changes Event-PPH score arithmetic.

This distinction also governs recovery learning: if the provider rejects the action, Event PPH compares the provider-directed recovery against the **Event-PPH wait only**. A prior APP suspension cannot hide an Event-PPH underprediction. APP instead learns from the burst probe and enclosed recovery interval as its own higher-order evidence.

The current APP usage vector is deliberately local and observable, but v0.13 preserves two observation planes instead of pretending they are one GitHub quota domain. The **controller plane** uses run-local deltas for request/mutation/content/PPH-managed counts together with the trusted governor's current one-minute and one-hour content windows. The **subject MCP plane** is checkpointed at the recurring run-admission action: the previous run's successful `app.installation_token.mint` action result becomes the starting MCP checkpoint for the next run's mint admission. Because a scenario slice reuses one repository, this per-run credential action replaces the regression-era repeated `repository.create` boundary without reintroducing repository churn. The next run admission can therefore see subject traffic accumulated after the preceding admission action. Time is not itself a pacing rule: the accumulation interval is only another observed dimension used to compare traffic density.

### MCP subject observation plane

The maintained MCP governor v2 is now a gated transport, not a second PPH/APP implementation. During an active ACMM logical run it asks the Core Provider Gate for admission before each GitHub request, skips its ordinary local request/mutation spacing and cooldown sleeps, and returns provider feedback to the same Core decision for recovery. If the active gate is unavailable or malformed, the transport fails closed before contacting GitHub. Outside an active ACMM gate, the conservative local governor remains the fallback. Provider recovery never authorizes ambiguous mutation replay: Core may request transport replay only for retry-safe reads (GET/HEAD/OPTIONS and classified GraphQL queries). A rejected REST or GraphQL mutation still teaches/actuates provider recovery, but the original rejection is returned to the caller for explicit agent-level recovery.

The subject-plane evidence includes cumulative request/mutation counts, semantic REST/GraphQL/raw request-kind counts, gate admission/recovery/error counters, gate wait seconds, provider rate-limit events, and current fallback backoff/cooldown state. Controller and subject counters remain separately named; ACMM does not assert that they combine into one documented provider quota.

APP v0.13 no longer advances a per-action MCP checkpoint. Instead, every logical run opens one **run-local burst window** from the controller and MCP snapshots captured at `run_measurement_start()`. Individual gated actions observe the cumulative controller+MCP delta since that window began. A zero-wait success does not reset the window. The window resets only after an actual APP suspension or after a pressure probe closes following provider recovery, so dense MCP traffic can accumulate into a meaningful burst shape instead of being zeroed at every request. The burst-window bookkeeping is non-episode state; only Core-owned APP probes carry episode semantics.

An observed increase in MCP secondary-limit events is translated into an independent Event-PPH punishment on the shared GitHub-pressure feature `provider.github.shared_pressure`; it does not synthesize an APP episode. Conversely, ordinary MCP successes are not converted into Event-PPH rewards merely because the transport returned success. APP eligibility includes the classified MCP request kinds themselves because individual MCP requests have a first-class synchronous Core admission bridge. The MCP transport remains policy-free: Core owns Event PPH and generic APP probe lifecycle, while the package owns GitHub action classification, run-local usage-vector construction, pocket geometry, and provider-specific recovery interpretation.

Each scientific session preserves a separate `mcp_subject_api_usage.json` artifact containing start, end, and delta snapshots for the subject plane. Historical replay can import secondary-limit deltas from that sibling artifact while keeping the controller `apparatus_api_usage.json` evidence distinct. Governor v2 supplies the richer telemetry needed for the F5-A/F5-B candidate: REST/GraphQL/raw classification plus gate admission/recovery/error and wait accounting. Further telemetry changes, if any, must be justified by the definitive F5 pair before the F6 validation freeze.

Core remains provider-agnostic. Profile schema v0.5 keeps opaque package model state while Core owns the generic APP policy, independent suspension hook, probe lifecycle, recovery grouping, and action-result closure. Provider-specific pocket geometry and usage semantics remain package-owned. Event PPH remains episode-free.

## Static PQE and universal active-run Provider Gate

Provider Quota Estimation (PQE) is deliberately separate from the dynamic PPH/APP learner. PQE uses provider-visible primary/content remainder plus historical execution usage to answer a static question: **does the known quota remainder safely cover the upcoming materialization or subject slice?** Experiment 2 reports PQE sparsely at scenario-materialization admission and once when each subject block begins. If known headroom is insufficient, PQE waits before admitting that slice; its forecast/remainder decision is recorded in `execution_resource_usage.yaml`. PQE does not open APP probes and does not teach Event PPH.

During an active logical run, the Core Provider Gate is the single dynamic admission/recovery surface for participating provider traffic:

- subject MCP REST, GraphQL, and raw-content requests;
- trusted controller REST/App requests;
- Git smart-protocol operations such as push/fetch/ls-remote for admission/result accounting.

The package classifies each request into an action kind and features. Core then applies APP suspension independently, Event-PPH pacing independently, and a quiet static provider-safety spacing floor. The current package floor is **at least 1 second between provider requests and 2 seconds between mutations**. This baseline is operational safety, not learned pressure: it is recorded separately as `provider_baseline_spacing`, does not alter Event-PPH scores, and does not create an APP probe.

While the active gate owns a request, the Experiment 2 REST/App governor and MCP governor bypass their ordinary proactive spacing/cooldown sleeps so the same action is not paced twice. They remain conservative fallback governors when no ACMM gate is active. Git operations likewise bypass their legacy push/read pacing while the gate is active; because Git smart protocol does not expose GitHub REST rate-limit headers, it contributes admission/result density evidence but only transports provider-directed recovery when the transport can actually supply an actionable recommendation.

The ordering for a managed provider-pressure retry is deliberately causal:

```text
action intent
    -> Core Provider Gate
       -> APP suspension, if a learned burst pocket is red-lining
       -> Event PPH per-action pacing, if learned feature pressure warrants it
       -> static provider baseline spacing
    -> request attempt
    -> explicit provider primary/secondary rate-limit response, if any
    -> package classifies provider recovery directive
    -> Core correlates directive to the original decision
    -> Event PPH learns only provider_wait - Event_PPH_wait
    -> Core actuates provider recovery once
    -> if the request is retry-safe, replay proceeds under the same decision without another ordinary admission
    -> if the request is mutative, return the original rejection without automatic replay
```

Normal Event-PPH pacing is intentionally quiet in the console because it can occur frequently and remains fully preserved in trajectory evidence. APP suspensions are always printed because they can be long. Provider recovery is also always printed, including recommendation source; whenever the provider wait exceeds Event PPH's predicted wait, the console explicitly reports the Event-PPH miss.

## PPH actuation

When an action passes through the Provider Gate, Core computes Event-PPH pressure only from features declared by that action. If the pressure is above the model's free baseline, PPH may impose pacing before allowing the action to continue. The delay remains a heuristic actuation derived from the learned feature score; it is not a reconstructed GitHub quota.

PPH-origin pacing is recorded separately by reason:

```text
learned_provider_pressure
    = proactive wait PPH predicted before the action

provider_directed_recovery
    = provider-authoritative recovery wait PPH actuated after rejection

runtime provider-pressure pacing
    = legacy/fallback pressure wait observed outside first-class recovery
```

The independent APP suspension and static baseline spacing are recorded separately from these Event-PPH/recovery reasons. This separation gives the trajectory a directly testable convergence signal: over repeated compatible work, runtime-unexpected provider-pressure pacing should fall as PPH learns, without pretending that the hidden provider policy itself has been discovered.

## Pressure trajectory

The mutable operational profile and immutable research trajectory are separated. Under the resolved generated artifact root Core creates:

```text
provider_pressure/
  <provider>/
    <scope-sha256>/
      <model-id>/
        <model-version>-<definition-sha-prefix>/
          profile-state.yaml
          trajectory-index.yaml
          trajectory/
            000000_<timestamp>_bootstrap_bootstrap.yaml
            000001_<timestamp>_historical_replay_<execution>.yaml
            000002_<timestamp>_live_execution_<execution>.yaml
            ...
```

`profile-state.yaml` is mutable operational memory. Every trajectory snapshot is immutable after creation and contains:

- sequence number and UTC timestamp;
- source kind and execution identity;
- parent snapshot SHA-256;
- snapshot SHA-256;
- model/provider identity;
- profile state before the observation, including opaque package-owned model state;
- reward/punishment signals applied;
- PPH actuation decisions;
- raw pacing events observed by PPH;
- profile state after the observation.

The profile tracks descriptive totals such as runtime-pressure event count/seconds and PPH-actuation event count/seconds. These counters support convergence analysis but are not hidden global admission scores.

This creates a directly analyzable trajectory without mixing PPH state with GOBPFR judgments.

## Initial-model simplicity

PPH v0.13 remains event-driven at the Event PPH layer and retains APP without creating a global provider-pressure scalar. Event PPH still has no timestamp spacing floor, no `next_allowed_at` schedule, and no episode/probe state. APP is the only layer allowed to retain a provider-pressure episode abstraction.

The evaluation questions are therefore separately falsifiable:

> When a provider rejects a PPH-admitted action, does Event PPH increase pressure only for that action's declared features according to measured underprediction?

> When repeated provider rejections occur inside one retry ladder, does APP treat them as one probe, learn the surrounding local usage/density shape, and later suspend immediately and independently when a sufficiently similar red-line pocket is observed?

More advanced nonlinear retry penalties or elastic cross-feature propagation may be studied later as separate model revisions if evidence justifies their added complexity.

## F5 proof of concept and F6 validation freeze

The integrated controller + subject-MCP observation design is validated in two stages. **F5-A and F5-B are the complete proof-of-concept pair.** Their purpose is to exercise the dual observation planes, inspect `mcp_subject_api_usage.json` and PPH/APP trajectory evidence, and validate the universal controller+MCP gate, the v2 semantic request-kind/gate telemetry, the run-local APP burst window, PQE boundaries, and shared-repository restoration under realistic agent traffic. Instrumentation or model defects found during this POC may still justify changes before the F6 freeze.

After the F5-A/F5-B POC is accepted, the PPH/APP algorithm, feature vocabulary, pocket geometry, thresholds, and evidence schema are frozen for validation. The exact pre-F6 Provider Pressure Profile is archived as a checkpoint. APP and Event PPH may continue their normal online learning during validation because adaptive learning is part of the system under test, but the model design itself is not tuned in response to F6 outcomes.

**F6-A and F6-B are the final validation pair.** A model-design or instrumentation change motivated by F6 invalidates that validation pass; the corrected design must be frozen again and F6 rerun. This keeps F6 from becoming another tuning set while still allowing the operational learner to carry forward provider-pressure knowledge accumulated during F5.


## External-practice validation after v0.13 stabilization

The v0.13 control surface was compared against current GitHub and Octokit guidance only after the architecture was stable. The comparison is confirmatory rather than normative: ACMM keeps its evidence-driven Event-PPH/APP model and does not import another library's hidden policy assumptions.

- GitHub's published guidance supports serialized requests, at least one second between mutative requests, provider-authoritative `Retry-After`/reset handling, at least a one-minute fallback for secondary pressure without a directive, exponential retry spacing on repeated failures, and bounded retries. The ACMM package's quiet 1-second all-request / 2-second mutation baseline is intentionally more conservative than the published mutative minimum.
- GitHub currently documents separate REST and GraphQL secondary point envelopes, shared concurrency limits, CPU-time limits, and approximate content-generation limits while warning that secondary limits can change or be undisclosed. These figures remain reference/cold-start metadata unless ACMM can actually observe the corresponding dimension. GraphQL HTTP-200 rate-limit errors are treated as provider-pressure feedback just like 403/429 responses.
- Octokit's throttling plugin follows provider-directed rate/secondary-limit callbacks and uses a 60-second secondary fallback when no `Retry-After` is supplied. That is conceptually aligned with ACMM's provider-feedback/recovery path. Generic retry behavior remains a separate concern; it is not treated as a replacement for secondary-limit classification.
- Consolidated GraphQL queries remain a pressure-generation optimization, not a waiting/recovery mechanism. They are deliberately deferred until the definitive F5 telemetry shows whether reducing request count/shape is justified; adopting them must not change the frozen F6 validation candidate without restarting validation.

## Epistemic boundary

PPH values are ACMM heuristic beliefs, not GitHub policy reconstruction. A learned pressure score must never be reported as a provider quota. The defensible claim is narrower:

> ACMM observed provider-pressure pacing associated with a traffic shape and adapted later action admission in response to those observations.

The trajectory is intended to make that adaptation auditable and testable across F5-A, repeated F5-B qualifications, F6-A, F6-B, and future experiments.
