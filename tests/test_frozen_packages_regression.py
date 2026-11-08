from pathlib import Path
import shutil

from acmm.experiment_package import (
    install_experiment_package,
    load_experiment_package,
    load_staged_experiment_runtime,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "minimal_agent_baseline_v1"
QUALIFICATION = ROOT / "github_mcp_integration_qualification_v1"

BASELINE_PACKAGE_SHA256 = "676f24acad6c706634c0c6d68d2b48a75d2f630c08f8f0b13c10c90974f8eec7"
QUALIFICATION_PACKAGE_SHA256 = "5e096940561472d1e33b5634852ff6cdafc4eb966906aa5ace4e44cd13a3fcf2"


def _install_copy(source_root: Path, tmp_path: Path):
    source = tmp_path / source_root.name
    shutil.copytree(
        source_root,
        source,
        ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"),
    )
    return install_experiment_package(source, tmp_path / "runtime-root")


def test_frozen_minimal_agent_baseline_is_unchanged_and_activates(tmp_path: Path) -> None:
    source_package = load_experiment_package(BASELINE)
    assert source_package.package_sha256 == BASELINE_PACKAGE_SHA256
    assert source_package.schema_version == "0.1"
    assert source_package.experiment_id == "minimal_agent_baseline_v1"
    assert source_package.integrations == ()
    assert source_package.runtime is not None
    assert len(source_package.contract["subjects"]) == 3
    assert len(source_package.contract["scenarios"]) == 16
    assert source_package.contract["run_protocol"]["repetitions"] == 8
    assert source_package.contract["run_protocol"]["ordering"] == "subject_repetition_scenario"
    assert source_package.contract["run_protocol"]["scenario_ordering"] == "cyclic_rotation"

    contract_ids = {item["id"] for item in source_package.contract["scenarios"]}
    asset_ids = {
        path.stem for path in (BASELINE / "assets" / "scenarios").glob("*.json")
    }
    assert asset_ids == contract_ids

    staged = _install_copy(BASELINE, tmp_path)
    loaded = load_staged_experiment_runtime(staged)
    assert loaded.runtime.capabilities.evaluators == frozenset({"minimal_baseline"})
    assert loaded.runtime.capabilities.fixtures == frozenset()
    assert set(loaded.runtime.evaluators) == {"minimal_baseline"}


def test_frozen_github_mcp_qualification_is_unchanged() -> None:
    package = load_experiment_package(QUALIFICATION)

    assert package.package_sha256 == QUALIFICATION_PACKAGE_SHA256
    assert package.schema_version == "0.2"
    assert package.experiment_id == "github_mcp_integration_qualification_v1"
    assert package.runtime is not None
    assert len(package.integrations) == 1
    integration = package.integrations[0]
    assert integration.integration_id == "github_mcp"
    assert tuple(secret.secret_id for secret in integration.secrets) == ("access_token",)
    assert tuple(integration.configuration["tools"]) == (
        "issue_read",
        "issue_write",
        "add_issue_comment",
    )
