from pathlib import Path
import shutil

from acmm.experiment_package import (
    install_experiment_package,
    load_experiment_package,
    load_staged_experiment_runtime,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "minimal_agent_baseline_v1"
BASELINE_PACKAGE_SHA256 = "676f24acad6c706634c0c6d68d2b48a75d2f630c08f8f0b13c10c90974f8eec7"


def _install_copy(tmp_path: Path):
    source = tmp_path / BASELINE.name
    shutil.copytree(
        BASELINE,
        source,
        ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"),
    )
    return install_experiment_package(source, tmp_path / "runtime-root")


def test_minimal_agent_baseline_is_unchanged_and_activates(tmp_path: Path) -> None:
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

    staged = _install_copy(tmp_path)
    loaded = load_staged_experiment_runtime(staged)
    assert loaded.runtime.capabilities.evaluators == frozenset({"minimal_baseline"})
    assert loaded.runtime.capabilities.fixtures == frozenset()
    assert set(loaded.runtime.evaluators) == {"minimal_baseline"}
