# Experiment Repository Tests

Development tests are intentionally outside Experiment Package directories. Package directories contain
only material that may be validated, hashed, installed, and copied into the Core-managed package store.

Tests are grouped by the exact Experiment Package ID that owns the behavior under test:

```text
tests/
  minimal_agent_baseline_v1/
  github_mcp_integration_qualification_v1/
  github_mcp_project_workspace_v1/
```

This boundary allows test-only maintenance to evolve without changing an installed package revision.
Repository-wide tests should still be run together with `pytest <experiments-repository>`.
