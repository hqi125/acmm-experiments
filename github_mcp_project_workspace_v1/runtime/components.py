from __future__ import annotations

import hashlib
import json

from acmm.experiment_api import (
    experiment_runtime,
    experiment_runtime_context,
    harness_capabilities,
)

from .apparatus import (
    github_disposable_repository_lifecycle_qualifier,
    github_fixture_base_initializer,
)
from .controller import (
    github_controller_client,
    github_controller_diagnostic,
    github_fixture_base_file,
)
from .evaluator import github_workspace_evaluator
from .disposable_lifecycle import github_workspace_disposable_lifecycle
from .f1_a import github_f1_a_materializer, load_f1_a_spec
from .f1_b import github_f1_b_materializer, load_f1_b_spec
from .f1_a_runtime import github_f1_a_fixture
from .f1_b_runtime import github_f1_b_fixture
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
    subject_probe_client = github_controller_client(
        subject_token,
        api_base=configuration["api_base"],
    )
    credentials_distinct = (
        _fingerprint(controller_token) != _fingerprint(subject_token)
    )
    diagnostic = github_controller_diagnostic(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        require_private=configuration["require_private"],
        credentials_distinct=credentials_distinct,
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

    lifecycle_qualifier = github_disposable_repository_lifecycle_qualifier(
        controller,
        subject_probe_client,
        credentials_distinct=credentials_distinct,
        experiment_id="github_mcp_project_workspace_v1",
        probe_name_prefix=configuration["disposable_probe_name_prefix"],
    )

    f1_a_spec = _load_f1_a_configuration(context)
    f1_b_spec = _load_f1_b_configuration(context)
    disposable_lifecycle = github_workspace_disposable_lifecycle(
        controller,
        subject_probe_client,
        experiment_id="github_mcp_project_workspace_v1",
        run_name_prefix=configuration["disposable_run_name_prefix"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_version=configuration["fixture_base_version"],
        fixture_base_files=configuration["fixture_base_files"],
        f1_a_spec=f1_a_spec,
        f1_b_spec=f1_b_spec,
    )
    f1_a_materializer = github_f1_a_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f1_a_spec,
    )

    f1_b_materializer = github_f1_b_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f1_b_spec,
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
    fixtures["github_workspace_f1_b"] = github_f1_b_fixture(
        controller,
        f1_b_materializer,
        f1_b_spec,
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
        lifecycle=disposable_lifecycle,
        fixtures=fixtures,
        evaluators={"github_workspace": github_workspace_evaluator()},
        diagnostics={"github_fixture_controller": diagnostic},
        apparatus_actions={
            "initialize": initializer,
            "qualify_disposable_repositories": lifecycle_qualifier,
            "prepare_f1_a": f1_a_materializer,
            "prepare_f1_b": f1_b_materializer,
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

    disposable = value.get("disposable_repositories")
    if not isinstance(disposable, dict):
        raise ValueError("Controller configuration disposable_repositories is invalid.")
    probe_name_prefix = disposable.get("probe_name_prefix")
    if not isinstance(probe_name_prefix, str) or not probe_name_prefix.strip():
        raise ValueError(
            "Controller disposable_repositories.probe_name_prefix is invalid."
        )
    run_name_prefix = disposable.get("run_name_prefix")
    if not isinstance(run_name_prefix, str) or not run_name_prefix.strip():
        raise ValueError(
            "Controller disposable_repositories.run_name_prefix is invalid."
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
    value["disposable_probe_name_prefix"] = probe_name_prefix.strip()
    value["disposable_run_name_prefix"] = run_name_prefix.strip()
    return value


def _load_f1_a_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f1_a.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F1-A fixture configuration must contain a JSON object.")
    return load_f1_a_spec(value)


def _load_f1_b_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f1_b.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F1-B fixture configuration must contain a JSON object.")
    workflow = value.get("required_workflow")
    if not isinstance(workflow, dict):
        raise ValueError("F1-B required_workflow configuration must contain an object.")
    resource = workflow.get("resource")
    if not isinstance(resource, str) or not resource.strip():
        raise ValueError("F1-B required_workflow.resource is invalid.")
    workflow_content = context.resolve_resource(resource).read_text(encoding="utf-8")
    return load_f1_b_spec(value, workflow_content=workflow_content)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
