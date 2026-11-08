from __future__ import annotations

from acmm.experiment_api import evaluation_context, judgment_result


class github_workspace_evaluator:
    def evaluate(self, context: evaluation_context) -> judgment_result:
        del context
        raise RuntimeError(
            "GitHub workspace evaluator is not implemented in this package revision."
        )
