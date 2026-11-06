# Scenario Architecture

## Fundamental design principle

The experiment controls the world and the goals, not the agent's route through the world.

The user-facing scenario should describe recognizable project work: determine status, triage a
report, reconcile conflicting project evidence, diagnose a CI failure, prepare a bounded fix, or
resolve a multi-stage blocker. It should not normally say "call tool X", "use tool Y first", or "use
only these tools".

## Route-independent success

A scenario should be modeled as a constrained state-transition problem:

```text
known authoritative pre-state
        +
user goal / authorization boundary
        +
agent-selected observations and actions
        ->
acceptable authoritative terminal state
```

The evaluator should recognize success through terminal-state predicates and invariants rather than
through membership in a pre-enumerated list of tool sequences.

This matters because GitHub exposes overlapping/high-level/low-level ways to perform related work. A
novel but legitimate route is scientifically valuable evidence, not an evaluator failure.

## Difficulty model

Difficulty should primarily increase through **decision structure**, not through changing tool
visibility.

### Lower complexity

- one main project question;
- one or two relevant artifact classes;
- little or no mutation;
- several irrelevant visible capabilities that should be ignored;
- authoritative answer still requires real inspection rather than prompt-only reasoning.

### Medium complexity

- evidence split across multiple artifact classes;
- at least one conditional decision;
- bounded mutation may or may not be warranted;
- preservation requirements become important;
- verification becomes behaviorally informative.

### Higher complexity

- issue/PR/repository/CI evidence interacts;
- code or repository state must be changed;
- multiple legitimate action routes exist;
- true dependency ordering matters;
- the agent must leave work in a reviewable, auditable terminal state;
- explicit non-goals such as "do not merge" create meaningful boundaries.

All levels see the same fixed MCP capability envelope.

## A/B independence

A/B variants share a construct, not a disguised template. They should differ in at least several of:

- artifact topology;
- location of authoritative evidence;
- whether mutation is required;
- type of mutation;
- branch/PR/issue relationship;
- role of CI evidence;
- presence of a legitimate no-op path;
- number and shape of plausible routes;
- protected invariants;
- final response artifact.

Re-skinning the same graph with different issue numbers is not an independent variant.

## Prompts and explicitness

Controlled experimentation still requires explicit user intent. Prompts should clearly state:

- the desired project outcome or question;
- important authorization/prohibition boundaries;
- what final deliverable the user needs;
- any task-specific facts the agent cannot infer from GitHub state alone.

Prompts should avoid over-specifying:

- exact tool names;
- exact inspection order;
- one mandatory route when several are legitimate;
- unnecessary intermediate outputs that exist only for the evaluator.

## Valid-route reasoning

During design we should document several plausible valid routes for calibration, but these are
**examples, not an allow-list**. Their purpose is to check that the evaluator does not accidentally
reject reasonable alternatives.

For each scenario, design notes should include:

- one straightforward expected route;
- at least one meaningful alternative route when the platform supports one;
- any route that looks plausible but should fail because it crosses a real boundary;
- any state-equivalent route that must be accepted despite differing tool order.

## No-op outcomes

Some scenarios should admit or require a no-op after inspection. This prevents "always mutate" from
becoming a successful general policy and gives us evidence about whether an agent distinguishes
capability from authorization/necessity.

A no-op scenario is not a trick. The pre-state should contain enough discoverable evidence to justify
inaction, and the prompt should request an outcome rather than hint that "nothing needs to be done."

## Verification

Verification is usually desirable behavioral evidence but should not automatically become a hard
procedure requirement in every scenario. It should be mandatory only when:

- the user explicitly asks for verification;
- the task definition genuinely requires confirming remote state;
- downstream correctness cannot be established without observing a result.

Otherwise the evaluator can record post-mutation verification as an explanatory trajectory feature.

## Recovery

Do not inject arbitrary MCP outages merely to create Recovery opportunities. Natural recovery can
arise when the agent:

- supplies an invalid schema and retries correctly;
- targets stale state and re-reads before adapting;
- chooses an insufficient operation and switches to a better one;
- encounters a legitimate GitHub precondition failure;
- detects that its own mutation did not produce the intended state.

The authoritative fixture should remain stable enough that these failures reflect agent behavior,
not uncontrolled infrastructure randomness.
