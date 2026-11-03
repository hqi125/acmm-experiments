from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acmm.experiment_api import (
    experiment_runtime,
    experiment_runtime_context,
    harness_capabilities,
)

from .evaluator import minimal_baseline_evaluator


def build_runtime(
    context: experiment_runtime_context,
) -> experiment_runtime:
    scenario_root = context.resolve_resource("assets/scenarios")
    scenarios = _load_scenarios(scenario_root)

    return experiment_runtime(
        capabilities=harness_capabilities(
            evaluators=frozenset({"minimal_baseline"}),
            fixtures=frozenset(),
            tools=frozenset(),
            evidence_channels=frozenset(
                {
                    "conversation",
                    "tool_calls",
                    "tool_results",
                    "final_response",
                }
            ),
        ),
        evaluators={
            "minimal_baseline": minimal_baseline_evaluator(scenarios),
        },
    )


def _load_scenarios(root: Path) -> dict[str, dict[str, Any]]:
    scenarios: dict[str, dict[str, Any]] = {}

    for path in sorted(root.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Scenario asset must contain an object: {path.name}")

        scenario_id = data.get("id")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError(f"Scenario asset has no valid id: {path.name}")
        if scenario_id in scenarios:
            raise ValueError(f"Duplicate scenario asset id: {scenario_id}")

        scenarios[scenario_id] = data

    return scenarios
