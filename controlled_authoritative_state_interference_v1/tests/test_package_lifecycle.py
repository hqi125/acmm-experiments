from __future__ import annotations

from pathlib import Path
import shutil

from acmm.contract.validator import default_contract_schema_path
from acmm.experiment_package import (
    install_experiment_package,
    load_staged_experiment_apparatus,
    load_staged_experiment_runtime,
)
from acmm_infra.profiles.agent_zero import load_agent_zero_profile
from acmm_infra.profiles.common import default_repo_root
from acmm_infra.profiles.experiments import (
    with_agent_zero_apparatus,
    with_hermes_apparatus,
    with_open_webui_apparatus,
)
from acmm_infra.profiles.hermes import load_hermes_profile
from acmm_infra.profiles.open_webui import load_open_webui_profile
from acmm_infra.subject_managers import build_package_subject_manager


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "controlled_authoritative_state_interference_v1"


def _install_copy(tmp_path: Path):
    source = tmp_path / "source"
    shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"))
    return install_experiment_package(
        source,
        tmp_path / "runtime-root",
        contract_schema_path=default_contract_schema_path(),
    )


def test_package_runtime_activates_from_staged_snapshot(tmp_path: Path) -> None:
    package = _install_copy(tmp_path)
    shutil.rmtree(tmp_path / "source")

    loaded = load_staged_experiment_runtime(package)

    assert loaded.context.experiment_id == EXPERIMENT_ID
    assert set(loaded.runtime.fixtures) == {"authoritative_state_workspace_v1"}
    assert set(loaded.runtime.evaluators) == {
        "authoritative_state_goal",
        "temporal_revalidation_procedure",
        "authoritative_state_fidelity",
    }
    assert loaded.runtime.capabilities.tools == frozenset({"read_record", "write_record"})


def test_package_apparatus_composes_for_all_subjects(tmp_path: Path) -> None:
    package = _install_copy(tmp_path)
    repo = default_repo_root()

    hermes_component = load_staged_experiment_apparatus(package, "hermes")
    open_webui_component = load_staged_experiment_apparatus(package, "open-webui")
    agent_zero_component = load_staged_experiment_apparatus(package, "agent-zero")

    hermes = with_hermes_apparatus(
        hermes_component.root,
        load_hermes_profile(repo),
        EXPERIMENT_ID,
    )
    open_webui = with_open_webui_apparatus(
        open_webui_component.root,
        load_open_webui_profile(repo),
        EXPERIMENT_ID,
    )
    agent_zero = with_agent_zero_apparatus(
        agent_zero_component.root,
        load_agent_zero_profile(repo),
        EXPERIMENT_ID,
    )

    assert hermes.plugins[0].name == "acmm-tools"
    assert hermes.plugins[0].source_root == hermes_component.root
    assert (hermes_component.root / hermes.plugins[0].source / "__init__.py").is_file()
    assert open_webui.tools[0].id == "acmm_tools"
    assert open_webui.tools[0].source_root == open_webui_component.root
    assert agent_zero.experiment_isolation.allowed_tools == (
        "plugin:acmm_tools:read_record",
        "plugin:acmm_tools:write_record",
    )
    assert agent_zero.plugins[0].source_root == agent_zero_component.root


def test_core_builds_subject_managers_from_external_package(tmp_path: Path) -> None:
    package = _install_copy(tmp_path)
    repo = default_repo_root()
    runtime_root = tmp_path / "subject-runtime"

    for infrastructure_subject in ("hermes", "open-webui", "agent-zero"):
        context = build_package_subject_manager(
            repo,
            runtime_root,
            infrastructure_subject,
            package,
        )
        assert context.experiment_id == EXPERIMENT_ID
        assert context.package_sha256 == package.package_sha256
        assert context.llm_baseline_id == "nemotron_3_nano_30b_cloud_v1"
