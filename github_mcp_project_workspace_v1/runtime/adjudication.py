from __future__ import annotations

from acmm.adjudication_api import (
    experiment_adjudication_context,
    experiment_adjudicator,
)

from .evaluator import github_workspace_evaluator


def build_adjudicator(
    context: experiment_adjudication_context,
) -> experiment_adjudicator:
    if context.experiment_id != "github_mcp_project_workspace_v1":
        raise ValueError(
            f"Unexpected experiment id for adjudicator: '{context.experiment_id}'."
        )
    return experiment_adjudicator(
        evaluators={"github_workspace": github_workspace_evaluator()},
    )


__all__ = ["build_adjudicator"]
