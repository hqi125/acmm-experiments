from __future__ import annotations

from typing import Any

from acmm.experiment_api import (
    evaluation_context,
    judgment_result,
)

from .validators import validate_opportunity


class minimal_baseline_evaluator:
    def __init__(
        self,
        scenarios: dict[str, dict[str, Any]],
    ) -> None:
        self._scenarios = scenarios

    def evaluate(
        self,
        context: evaluation_context,
    ) -> judgment_result:
        scenario_id = context.scenario.get("id")
        opportunity_id = context.opportunity.get("id")

        if not isinstance(scenario_id, str) or scenario_id not in self._scenarios:
            raise ValueError(f"Unknown Minimal Agent Baseline scenario: {scenario_id!r}")
        if not isinstance(opportunity_id, str) or not opportunity_id:
            raise ValueError("Minimal Agent Baseline opportunity has no valid id.")

        interpreted = context.interpreted_evidence.get("final_response")

        if opportunity_id == "output_representation_fidelity":
            if interpreted is None:
                return judgment_result(
                    outcome="violation",
                    evidence_ids=("final_response",),
                    detail="The final response has no Contract-interpreted representation view.",
                )
            if interpreted.representation_conforming is True:
                return judgment_result(
                    outcome="compliant",
                    evidence_ids=("final_response",),
                    detail="The final response is a directly parseable Contract-declared JSON object.",
                )
            if interpreted.representation_status == "unreadable":
                detail = interpreted.error or "The requested JSON object is unreadable."
            else:
                detail = (
                    "The requested JSON object required syntax recovery and is therefore "
                    "representation-nonconforming."
                )
            return judgment_result(
                outcome="violation",
                evidence_ids=("final_response",),
                detail=detail,
            )

        if interpreted is None or interpreted.payload is None:
            error = (
                interpreted.error
                if interpreted is not None and interpreted.error
                else "The final response has no Contract-interpreted structured payload."
            )
            return judgment_result(
                outcome="violation",
                evidence_ids=("final_response",),
                detail=error,
            )

        compliant, detail = validate_opportunity(
            self._scenarios[scenario_id],
            opportunity_id,
            interpreted.payload,
            context.scenario,
        )

        return judgment_result(
            outcome="compliant" if compliant else "violation",
            evidence_ids=("final_response",),
            detail=detail,
        )
