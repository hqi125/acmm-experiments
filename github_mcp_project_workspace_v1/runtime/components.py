from __future__ import annotations

import hashlib
import json

from acmm.experiment_api import (
    experiment_runtime,
    experiment_runtime_context,
    harness_capabilities,
)

from .controller import github_controller_client, github_controller_diagnostic
from .evaluator import github_workspace_evaluator
from .fixture import github_workspace_fixture


_FIXTURE_IDS = (
    "github_workspace_f1_a",
    "github_workspace_f1_b",
    "github_workspace_f2_a",
    "github_workspace_f2_b",
    "github_workspace_f3_a",
    "github_workspace_f3_b",
    "github_workspace_f4_a",
    "github_workspace_f4_b",
    "github_workspace_f5_a",
    "github_workspace_f5_b",
    "github_workspace_f6_a",
    "github_workspace_f6_b",
)


def build_runtime(context: experiment_runtime_context) -> experiment_runtime:
    configuration = _load_controller_configuration(context)
    controller_token = context.resolve_package_secret("controller_access_token")
    subject_token = context.resolve_integration_secret("github_mcp", "access_token")

    controller = github_controller_client(
        controller_token,
        api_base=configuration["api_base"],
    )
    diagnostic = github_controller_diagnostic(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        require_private=configuration["require_private"],
        credentials_distinct=(
            _fingerprint(controller_token) != _fingerprint(subject_token)
        ),
    )

    fixtures = {
        fixture_id: github_workspace_fixture(fixture_id)
        for fixture_id in _FIXTURE_IDS
    }
    return experiment_runtime(
        capabilities=harness_capabilities(
            evaluators=frozenset({"github_workspace"}),
            fixtures=frozenset(_FIXTURE_IDS),
            evidence_channels=frozenset(
                {
                    "conversation",
                    "tool_calls",
                    "tool_results",
                    "final_response",
                    "initial_environment_state",
                    "final_environment_state",
                }
            ),
        ),
        fixtures=fixtures,
        evaluators={"github_workspace": github_workspace_evaluator()},
        diagnostics={"github_fixture_controller": diagnostic},
    )


def _load_controller_configuration(
    context: experiment_runtime_context,
) -> dict[str, object]:
    path = context.resolve_resource("assets/controller.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Controller configuration must contain a JSON object.")

    required = {
        "api_base": str,
        "repository_name": str,
        "repository_full_name": str,
        "repository_id": int,
        "require_private": bool,
        "fixture_branch_prefix": str,
        "fixture_marker": str,
    }
    for key, expected_type in required.items():
        item = value.get(key)
        if (
            not isinstance(item, expected_type)
            or (expected_type is str and not item.strip())
            or (expected_type is int and item <= 0)
        ):
            raise ValueError(
                f"Controller configuration field '{key}' is invalid."
            )
    return value


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
