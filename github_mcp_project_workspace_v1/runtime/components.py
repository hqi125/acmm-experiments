from __future__ import annotations

import hashlib
import json

from acmm.experiment_api import (
    experiment_runtime,
    experiment_runtime_context,
    harness_capabilities,
)

from .apparatus import (
    github_api_governor_inspector,
    github_disposable_repository_lifecycle_qualifier,
    github_fixture_base_initializer,
    github_quarantined_repository_cleanup,
)
from .api_governor import (
    default_github_api_governor_state_path,
    github_api_governor,
    github_api_governor_policy,
)
from .github_app import github_app_client
from .git_content_plane import github_git_content_plane
from .recovery import github_workspace_runtime_recovery
from .controller import (
    github_controller_client,
    github_controller_diagnostic,
    github_fixture_base_file,
)
from .evaluator import github_workspace_evaluator
from .disposable_lifecycle import github_workspace_disposable_lifecycle
from .f1_a import github_f1_a_materializer, load_f1_a_spec
from .f1_b import github_f1_b_materializer, load_f1_b_spec
from .f2 import (
    github_f2_a_materializer,
    github_f2_b_materializer,
    load_f2_a_spec,
    load_f2_b_spec,
)
from .f1_a_runtime import github_f1_a_fixture
from .f1_b_runtime import github_f1_b_fixture
from .f2_runtime import github_f2_a_fixture, github_f2_b_fixture
from .f3 import (
    github_f3_a_materializer,
    github_f3_b_materializer,
    load_f3_a_spec,
    load_f3_b_spec,
)
from .f3_runtime import github_f3_a_fixture, github_f3_b_fixture
from .f4 import (
    github_f4_a_materializer,
    github_f4_b_materializer,
    load_f4_a_spec,
    load_f4_b_spec,
)
from .f4_runtime import github_f4_a_fixture, github_f4_b_fixture
from .f5 import (
    github_f5_a_materializer,
    github_f5_b_materializer,
    load_f5_a_spec,
    load_f5_b_spec,
)
from .f5_runtime import github_f5_a_fixture, github_f5_b_fixture
from .f6 import (
    github_f6_a_materializer,
    github_f6_b_materializer,
    load_f6_a_spec,
    load_f6_b_spec,
)
from .f6_runtime import github_f6_a_fixture, github_f6_b_fixture
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
    github_app_private_key = context.resolve_package_secret("github_app_private_key")
    github_app_configuration = configuration["github_app"]
    repository_owner = str(configuration["repository_full_name"]).split("/", 1)[0]
    governor_scope = f"{configuration['api_base']}|{repository_owner.casefold()}"
    api_policy = configuration["api_policy"]
    governor = github_api_governor(
        scope=governor_scope,
        policy=github_api_governor_policy(
            request_interval_seconds=api_policy.get("request_interval_seconds", 0.25),
            mutation_interval_seconds=api_policy["mutation_interval_seconds"],
            content_requests_per_minute=api_policy["content_requests_per_minute"],
            content_requests_per_hour=api_policy["content_requests_per_hour"],
            primary_remaining_floor=api_policy["primary_remaining_floor"],
            primary_reset_grace_seconds=api_policy["primary_reset_grace_seconds"],
            retry_after_grace_seconds=api_policy.get("retry_after_grace_seconds", 3.0),
            max_secondary_retries=api_policy["max_secondary_retries"],
            provider_authoritative_rate_limits=api_policy.get(
                "provider_authoritative_rate_limits", True
            ),
            secondary_backoff_seconds=tuple(api_policy["secondary_backoff_seconds"]),
        ),
        state_path=default_github_api_governor_state_path(governor_scope),
    )
    app_client = github_app_client(
        app_id=github_app_configuration["app_id"],
        installation_id=github_app_configuration["installation_id"],
        private_key_pem=github_app_private_key,
        api_base=configuration["api_base"],
        governor=governor,
    )
    api_governor_inspector = github_api_governor_inspector(governor)
    git_policy = configuration.get("git_policy", {})
    git_content_plane = github_git_content_plane(
        controller_token,
        push_interval_seconds=float(git_policy.get("push_interval_seconds", 12.0)),
        remote_read_interval_seconds=float(
            git_policy.get("remote_read_interval_seconds", 0.1)
        ),
        provider_context=lambda content_generating: governor.serialized_git_operation(
            content_generating=content_generating
        ),
    )
    controller = github_controller_client(
        controller_token,
        api_base=configuration["api_base"],
        governor=governor,
        git_content_plane=git_content_plane,
    )
    credentials_distinct = True
    diagnostic = github_controller_diagnostic(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        require_private=configuration["require_private"],
        credentials_distinct=credentials_distinct,
        credential_separation_detail=(
            "controller PAT and per-run GitHub App installation token use separate "
            "credential domains"
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

    lifecycle_qualifier = github_disposable_repository_lifecycle_qualifier(
        controller,
        app_client,
        api_base=configuration["api_base"],
        experiment_id="github_mcp_project_workspace_v1",
        probe_name_prefix=configuration["disposable_probe_name_prefix"],
    )

    quarantine_cleanup = github_quarantined_repository_cleanup(
        controller,
        experiment_id="github_mcp_project_workspace_v1",
        run_name_prefix=configuration["disposable_run_name_prefix"],
    )

    f1_a_spec = _load_f1_a_configuration(context)
    f1_b_spec = _load_f1_b_configuration(context)
    f2_a_spec = _load_f2_a_configuration(context)
    f2_b_spec = _load_f2_b_configuration(context)
    f3_a_spec = _load_f3_a_configuration(context)
    f3_b_spec = _load_f3_b_configuration(context)
    f4_a_spec = _load_f4_a_configuration(context)
    f4_b_spec = _load_f4_b_configuration(context)
    f5_a_spec = _load_f5_a_configuration(context)
    f5_b_spec = _load_f5_b_configuration(context)
    f6_a_spec = _load_f6_a_configuration(context)
    f6_b_spec = _load_f6_b_configuration(context)
    disposable_lifecycle = github_workspace_disposable_lifecycle(
        controller,
        app_client,
        experiment_id="github_mcp_project_workspace_v1",
        run_name_prefix=configuration["disposable_run_name_prefix"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_version=configuration["fixture_base_version"],
        fixture_base_files=configuration["fixture_base_files"],
        f1_a_spec=f1_a_spec,
        f1_b_spec=f1_b_spec,
        f2_a_spec=f2_a_spec,
        f2_b_spec=f2_b_spec,
        f3_a_spec=f3_a_spec,
        f3_b_spec=f3_b_spec,
        f4_a_spec=f4_a_spec,
        f4_b_spec=f4_b_spec,
        f5_a_spec=f5_a_spec,
        f5_b_spec=f5_b_spec,
        f6_a_spec=f6_a_spec,
        f6_b_spec=f6_b_spec,
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

    f2_a_materializer = github_f2_a_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f2_a_spec,
    )

    f2_b_materializer = github_f2_b_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f2_b_spec,
    )

    f3_a_materializer = github_f3_a_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f3_a_spec,
    )

    f3_b_materializer = github_f3_b_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f3_b_spec,
    )

    f4_a_materializer = github_f4_a_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f4_a_spec,
    )

    f4_b_materializer = github_f4_b_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f4_b_spec,
    )

    f5_a_materializer = github_f5_a_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f5_a_spec,
    )

    f5_b_materializer = github_f5_b_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f5_b_spec,
    )

    f6_a_materializer = github_f6_a_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f6_a_spec,
    )

    f6_b_materializer = github_f6_b_materializer(
        controller,
        repository_name=configuration["repository_name"],
        expected_repository_full_name=configuration["repository_full_name"],
        expected_repository_id=configuration["repository_id"],
        expected_default_branch=configuration["expected_default_branch"],
        fixture_base_files=configuration["fixture_base_files"],
        spec=f6_b_spec,
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
    fixtures["github_workspace_f2_a"] = github_f2_a_fixture(
        controller,
        f2_a_materializer,
        f2_a_spec,
    )
    fixtures["github_workspace_f2_b"] = github_f2_b_fixture(
        controller,
        f2_b_materializer,
        f2_b_spec,
    )
    fixtures["github_workspace_f3_a"] = github_f3_a_fixture(
        controller,
        f3_a_materializer,
        f3_a_spec,
    )
    fixtures["github_workspace_f3_b"] = github_f3_b_fixture(
        controller,
        f3_b_materializer,
        f3_b_spec,
    )
    fixtures["github_workspace_f4_a"] = github_f4_a_fixture(
        controller,
        f4_a_materializer,
        f4_a_spec,
    )
    fixtures["github_workspace_f4_b"] = github_f4_b_fixture(
        controller,
        f4_b_materializer,
        f4_b_spec,
    )
    fixtures["github_workspace_f5_a"] = github_f5_a_fixture(
        controller,
        f5_a_materializer,
        f5_a_spec,
    )
    fixtures["github_workspace_f5_b"] = github_f5_b_fixture(
        controller,
        f5_b_materializer,
        f5_b_spec,
    )
    fixtures["github_workspace_f6_a"] = github_f6_a_fixture(
        controller,
        f6_a_materializer,
        f6_a_spec,
    )
    fixtures["github_workspace_f6_b"] = github_f6_b_fixture(
        controller,
        f6_b_materializer,
        f6_b_spec,
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
        apparatus_cleanup=quarantine_cleanup,
        recovery=github_workspace_runtime_recovery(
            controller,
            app_client,
            run_name_prefix=configuration["disposable_run_name_prefix"],
        ),
        fixtures=fixtures,
        evaluators={"github_workspace": github_workspace_evaluator()},
        diagnostics={"github_fixture_controller": diagnostic},
        apparatus_actions={
            "api_status": api_governor_inspector,
            "initialize": initializer,
            "qualify_disposable_repositories": lifecycle_qualifier,
            "prepare_f1_a": f1_a_materializer,
            "prepare_f1_b": f1_b_materializer,
            "prepare_f2_a": f2_a_materializer,
            "prepare_f2_b": f2_b_materializer,
            "prepare_f3_a": f3_a_materializer,
            "prepare_f3_b": f3_b_materializer,
            "prepare_f4_a": f4_a_materializer,
            "prepare_f4_b": f4_b_materializer,
            "prepare_f5_a": f5_a_materializer,
            "prepare_f5_b": f5_b_materializer,
            "prepare_f6_a": f6_a_materializer,
            "prepare_f6_b": f6_b_materializer,
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

    github_app = value.get("github_app")
    if not isinstance(github_app, dict):
        raise ValueError("Controller configuration github_app is invalid.")
    app_id = github_app.get("app_id")
    installation_id = github_app.get("installation_id")
    app_slug = github_app.get("slug")
    if (
        not isinstance(app_id, int)
        or isinstance(app_id, bool)
        or app_id <= 0
        or not isinstance(installation_id, int)
        or isinstance(installation_id, bool)
        or installation_id <= 0
        or not isinstance(app_slug, str)
        or not app_slug.strip()
    ):
        raise ValueError("Controller configuration github_app identity is invalid.")

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

    api_policy = value.get("api_policy")
    if not isinstance(api_policy, dict):
        raise ValueError("Controller configuration api_policy is invalid.")
    policy_fields = {
        "request_interval_seconds": (int, float),
        "mutation_interval_seconds": (int, float),
        "content_requests_per_minute": int,
        "content_requests_per_hour": int,
        "primary_remaining_floor": int,
        "primary_reset_grace_seconds": (int, float),
        "retry_after_grace_seconds": (int, float),
        "max_secondary_retries": int,
        "provider_authoritative_rate_limits": bool,
        "secondary_backoff_seconds": list,
    }
    for key, expected_type in policy_fields.items():
        item = api_policy.get(key)
        if isinstance(item, bool) and expected_type is not bool:
            raise ValueError(f"Controller api_policy.{key} is invalid.")
        if not isinstance(item, expected_type):
            raise ValueError(f"Controller api_policy.{key} is invalid.")
    if float(api_policy["request_interval_seconds"]) < 0:
        raise ValueError("Controller api_policy.request_interval_seconds is invalid.")
    if float(api_policy["mutation_interval_seconds"]) < 1.0:
        raise ValueError(
            "Controller api_policy.mutation_interval_seconds must be at least 1 second "
            "for GitHub REST best-practice compliance."
        )
    for key in ("content_requests_per_minute", "content_requests_per_hour"):
        if int(api_policy[key]) < 1:
            raise ValueError(f"Controller api_policy.{key} must be positive.")
    if int(api_policy["primary_remaining_floor"]) < 0:
        raise ValueError("Controller api_policy.primary_remaining_floor is invalid.")
    if float(api_policy["primary_reset_grace_seconds"]) < 0:
        raise ValueError("Controller api_policy.primary_reset_grace_seconds is invalid.")
    if float(api_policy["retry_after_grace_seconds"]) < 0:
        raise ValueError("Controller api_policy.retry_after_grace_seconds is invalid.")
    if int(api_policy["max_secondary_retries"]) < 0:
        raise ValueError("Controller api_policy.max_secondary_retries is invalid.")
    if (
        not api_policy["secondary_backoff_seconds"]
        or any(
            not isinstance(item, (int, float)) or float(item) <= 0
            for item in api_policy["secondary_backoff_seconds"]
        )
    ):
        raise ValueError("Controller api_policy.secondary_backoff_seconds is invalid.")

    git_policy = value.get("git_policy")
    if not isinstance(git_policy, dict):
        raise ValueError("Controller configuration git_policy is invalid.")
    for key in ("push_interval_seconds", "remote_read_interval_seconds"):
        item = git_policy.get(key)
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"Controller git_policy.{key} is invalid.")
    # GitHub recommends no more than six pushes/minute/repository and no more
    # than fifteen Git read operations/second/repository. Package configuration
    # may be stricter, never weaker, than those provider floors.
    if float(git_policy["push_interval_seconds"]) < 10.0:
        raise ValueError(
            "Controller git_policy.push_interval_seconds must be at least 10 seconds."
        )
    if float(git_policy["remote_read_interval_seconds"]) < (1.0 / 15.0):
        raise ValueError(
            "Controller git_policy.remote_read_interval_seconds must be at least 1/15 second."
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


def _load_f2_a_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f2_a.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F2-A fixture configuration must contain a JSON object.")
    return load_f2_a_spec(value)


def _load_f2_b_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f2_b.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F2-B fixture configuration must contain a JSON object.")
    return load_f2_b_spec(value)


def _load_f3_a_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f3_a.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F3-A fixture configuration must contain a JSON object.")
    return load_f3_a_spec(value)


def _load_f3_b_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f3_b.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F3-B fixture configuration must contain a JSON object.")
    return load_f3_b_spec(value)


def _load_f4_a_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f4_a.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F4-A fixture configuration must contain a JSON object.")
    workflow = value.get("required_workflow")
    if not isinstance(workflow, dict) or not isinstance(workflow.get("resource"), str):
        raise ValueError("F4-A required_workflow.resource is invalid.")
    content = context.resolve_resource(workflow["resource"]).read_text(encoding="utf-8")
    return load_f4_a_spec(value, workflow_content=content)


def _load_f4_b_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f4_b.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F4-B fixture configuration must contain a JSON object.")
    required = value.get("required_workflow")
    advisory = value.get("advisory_workflow")
    if not isinstance(required, dict) or not isinstance(required.get("resource"), str):
        raise ValueError("F4-B required_workflow.resource is invalid.")
    if not isinstance(advisory, dict) or not isinstance(advisory.get("resource"), str):
        raise ValueError("F4-B advisory_workflow.resource is invalid.")
    required_content = context.resolve_resource(required["resource"]).read_text(encoding="utf-8")
    advisory_content = context.resolve_resource(advisory["resource"]).read_text(encoding="utf-8")
    return load_f4_b_spec(
        value,
        required_workflow_content=required_content,
        advisory_workflow_content=advisory_content,
    )


def _load_f5_a_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f5_a.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F5-A fixture configuration must contain a JSON object.")
    return load_f5_a_spec(value)


def _load_f5_b_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f5_b.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F5-B fixture configuration must contain a JSON object.")
    return load_f5_b_spec(value)


def _load_f6_a_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f6_a.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F6-A fixture configuration must contain a JSON object.")
    workflow = value.get("required_workflow")
    if not isinstance(workflow, dict) or not isinstance(workflow.get("resource"), str):
        raise ValueError("F6-A required_workflow.resource is invalid.")
    content = context.resolve_resource(workflow["resource"]).read_text(encoding="utf-8")
    return load_f6_a_spec(value, workflow_content=content)


def _load_f6_b_configuration(
    context: experiment_runtime_context,
):
    path = context.resolve_resource("assets/fixtures/f6_b.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("F6-B fixture configuration must contain a JSON object.")
    workflow = value.get("required_workflow")
    if not isinstance(workflow, dict) or not isinstance(workflow.get("resource"), str):
        raise ValueError("F6-B required_workflow.resource is invalid.")
    content = context.resolve_resource(workflow["resource"]).read_text(encoding="utf-8")
    return load_f6_b_spec(value, workflow_content=content)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
