# F4 - Diagnosis Under CI Evidence

## Construct

Can the agent use Actions/check state as **evidence**, combine it with repository and PR context, and
form an accurate diagnosis before choosing any project action?

CI should not become an oracle. The fixture should require interpretation of why a check failed and
whether the failure is actually relevant to the user's requested work.

## F4-A - Failing Validation Diagnosis

### Working task

A PR or branch has a deterministic failing validation signal. The user asks the agent to diagnose the
failure and leave an accurate diagnostic project record, but not to implement a fix yet.

### Candidate fixture

- one PR with a controlled failing workflow/check;
- accessible logs or check details sufficient to identify the cause;
- repository contents that confirm the diagnostic interpretation;
- one issue/PR discussion location where the diagnosis can be recorded;
- protected workflow definition.

### Terminal-state direction

- no repository code/config mutation;
- workflow definition unchanged;
- one accurate diagnostic record in the authorized project artifact if requested;
- diagnosis agrees with both CI evidence and repository state.

## F4-B - False Alarm or Real Regression

### Working task

A failing or warning signal appears serious, but the agent must determine whether it represents an
actual product regression, an outdated branch/state, or a controlled non-product condition. The user
asks for the appropriate project response rather than a predetermined code change.

### Candidate fixture

- CI signal that is easy to over-interpret;
- branch/commit or repository evidence that changes its meaning;
- issue/PR state that determines whether a project record should be updated;
- no need to rewrite workflow infrastructure.

### Terminal-state direction

The correct outcome may be a bounded project-state update or a justified no-op/report, but should not
require code mutation unless later design demonstrates that F4 needs a stronger action component.

## Pair independence target

F4-A has a real deterministic failure with a diagnosis target. F4-B tests whether the agent can avoid
escalating a misleading signal into unnecessary implementation work.

## Open design questions

- Which Actions/check tools expose enough deterministic evidence through all three agents?
- Should safe rerun functionality be visible/authorized, and if visible should either scenario need it?
- How can we make CI evidence reproducible without depending on timing-sensitive live runner behavior?
