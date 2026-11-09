from __future__ import annotations

import hashlib
import json

from acmm.experiment_api import (
    experiment_runtime,
    experiment_runtime_context,
    harness_capabilities,
)

from .apparatus import github_fixture_base_initializer
from .controller import (
    github_controller_client,
    github_controller_diagnostic,
    github_fixture_base_file,
)
from .evaluator import github_workspace_evaluator
from .f1_a import github_f1_a_materializer, load_f1_a_spec
from .f1_a_runtime import github_f1_a_fixture
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
        expected_default_branch=configuration["expected_default_branch"],
        require_private=configuration["require_private"],
        credentials_distinct=(
            _fingerprint(controller_token) != _fingerprint(subject_token)
        ),
        fixture_base_version=configuration["fixture_base_version"],
        fixture_base_files=configuration["fixture_base_files"],
    )
    initializer = github_fixture_base_initializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        require_private=configuration["require_private"],
        fixture_base_version=configuration["fixture_base_version"],
        fixture_base_files=configuration["fixture_base_files"],
    )

    f1_a_spec = _load_f1_a_configuration(context)
    f1_a_materializer = github_f1_a_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f1_a_spec,
    )

    fixtures = {
        fixture_id: github_workspace_fixture(fixture_id)
        for fixture_id in _FIXTURE_IDS
    }
    fixtures["github_workspace_f1_a"] = github_f1_a_fixture(
        controller,
        f1_a_materializer,
        f1_a_spec,
    )
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
        apparatus_actions={
            "initialize": initializer,
            "prepare_f1_a": f1_a_materializer,
        },
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
        "expected_default_branch": str,
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

    fixture_base = value.get("fixture_base")
    if not isinstance(fixture_base, dict):
        raise ValueError("Controller configuration fixture_base is invalid.")
    version = fixture_base.get("version")
    files = fixture_base.get("files")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Controller fixture_base.version is invalid.")
    if not isinstance(files, list) or not files:
        raise ValueError("Controller fixture_base.files must be a non-empty list.")

    resolved_files: list[github_fixture_base_file] = []
    seen_paths: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise ValueError(
                f"Controller fixture_base.files[{index}] must be an object."
            )
        repository_path = item.get("path")
        resource = item.get("resource")
        if (
            not isinstance(repository_path, str)
            or not repository_path.strip()
            or repository_path.startswith("/")
            or ".." in repository_path.split("/")
        ):
            raise ValueError(
                f"Controller fixture_base.files[{index}].path is invalid."
            )
        if repository_path in seen_paths:
            raise ValueError(
                f"Controller fixture base path '{repository_path}' is duplicated."
            )
        if not isinstance(resource, str) or not resource.strip():
            raise ValueError(
                f"Controller fixture_base.files[{index}].resource is invalid."
            )
        content = context.resolve_resource(resource).read_text(encoding="utf-8")
        resolved_files.append(
            github_fixture_base_file(path=repository_path, content=content)
        )
        seen_paths.add(repository_path)

    value["fixture_base_version"] = version
    value["fixture_base_files"] = tuple(resolved_files)
    return value


def _load_f1_a_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f1_a.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F1-A fixture configuration must contain a JSON object.")
    return load_f1_a_spec(value)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
