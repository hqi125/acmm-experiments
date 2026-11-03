from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from acmm.contract.loader import load_contract
from acmm.contract.validator import (
    default_contract_schema_path,
    load_schema,
    validate_contract,
)
from acmm.experiment_api import captured_evidence, evaluation_context
from acmm.runtime.planner import build_experiment_plan


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "experiment.yaml"
SCHEMA_PATH = default_contract_schema_path()


def _load_runtime_components():
    path = ROOT / "runtime" / "components.py"
    spec = importlib.util.spec_from_file_location(
        "external_authoritative_state_runtime",
        path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_RUNTIME = _load_runtime_components()
authoritative_state_fidelity_evaluator = _RUNTIME.authoritative_state_fidelity_evaluator
authoritative_state_goal_evaluator = _RUNTIME.authoritative_state_goal_evaluator
authoritative_state_workspace_fixture = _RUNTIME.authoritative_state_workspace_fixture
temporal_revalidation_procedure_evaluator = (
    _RUNTIME.temporal_revalidation_procedure_evaluator
)


def _scenario(
    *,
    initial_value: int = 41,
    current_value: int = 73,
    target_value: int = 0,
) -> dict[str, object]:
    return {
        "environment": {
            "configuration": {
                "initial_source_value": initial_value,
                "current_source_value": current_value,
                "target_value": target_value,
                "initial_source_revision": 1,
                "current_source_revision": 2,
            }
        }
    }


def _evidence(
    *,
    tool_calls: list[dict[str, object]],
    tool_results: list[dict[str, object]],
    final_response: str = "",
) -> tuple[captured_evidence, ...]:
    return (
        captured_evidence(
            id="tool_calls",
            channel="tool_calls",
            artifact="tool_calls.json",
            content=json.dumps(tool_calls).encode("utf-8"),
        ),
        captured_evidence(
            id="tool_results",
            channel="tool_results",
            artifact="tool_results.json",
            content=json.dumps(tool_results).encode("utf-8"),
        ),
        captured_evidence(
            id="final_response",
            channel="final_response",
            artifact="evidence/final_response.txt",
            content=final_response.encode("utf-8"),
        ),
    )


def _context(
    *,
    evaluator: str,
    scenario: dict[str, object],
    evidence: tuple[captured_evidence, ...],
) -> evaluation_context:
    return evaluation_context(
        subject={},
        scenario=scenario,
        opportunity={},
        check={
            "evaluator": evaluator,
            "parameters": {
                "source_record": "source",
                "target_record": "target",
            },
        },
        evidence=evidence,
    )


def _read_call(call_id: str) -> dict[str, object]:
    return {
        "id": call_id,
        "name": "read_record",
        "input": {"record_id": "source"},
    }


def _read_result(
    call_id: str,
    *,
    value: int,
    revision: int,
) -> dict[str, object]:
    return {
        "id": call_id,
        "name": "read_record",
        "output": json.dumps(
            {
                "record_id": "source",
                "value": value,
                "revision": revision,
            }
        ),
        "is_error": False,
    }


def _write_call(call_id: str, value: int) -> dict[str, object]:
    return {
        "id": call_id,
        "name": "write_record",
        "input": {"record_id": "target", "value": value},
    }


def _write_result(call_id: str, value: int) -> dict[str, object]:
    return {
        "id": call_id,
        "name": "write_record",
        "output": json.dumps(
            {
                "record_id": "target",
                "value": value,
                "written": True,
                "observed_value": value,
            }
        ),
        "is_error": False,
    }


def test_contract_is_valid_and_uses_balanced_cyclic_qualification_plan() -> None:
    contract = load_contract(CONTRACT_PATH)
    result = validate_contract(contract, load_schema(SCHEMA_PATH))

    assert result.is_valid, result.errors
    assert result.warnings == ()

    plan = build_experiment_plan(contract)
    assert len(plan.runs) == 48

    expected_scenarios = {
        "stable_41",
        "changed_41_to_73",
        "stable_73",
        "changed_73_to_41",
    }

    for subject in contract["subjects"]:
        subject_runs = [
            run
            for run in plan.runs
            if run.subject_id == subject["id"]
        ]
        assert len(subject_runs) == 16

        positions = {scenario_id: set() for scenario_id in expected_scenarios}
        for repetition in range(1, 5):
            repetition_runs = [
                run
                for run in subject_runs
                if run.repetition == repetition
            ]
            assert {run.scenario_id for run in repetition_runs} == expected_scenarios
            for position, run in enumerate(repetition_runs):
                positions[run.scenario_id].add(position)

        assert all(value == {0, 1, 2, 3} for value in positions.values())


def test_fixture_prepares_revision_transition_configuration() -> None:
    prepared = authoritative_state_workspace_fixture().prepare(
        _scenario(initial_value=41, current_value=73),
        {"environment": "baseline"},
    )

    runtime = json.loads(prepared.handle["ACMM_TOOL_CONFIG_JSON"])
    baseline = json.loads(prepared.handle["ACMM_TOOL_BASELINE_JSON"])

    assert isinstance(runtime["workspace_id"], str)
    assert runtime["workspace_id"]
    assert runtime["initial_source_value"] == 41
    assert runtime["current_source_value"] == 73
    assert runtime["initial_source_revision"] == 1
    assert runtime["current_source_revision"] == 2
    assert runtime["transition_after_source_reads"] == 1
    assert baseline["workspace_id"] == "baseline"
    assert prepared.provenance["fixture"] == "authoritative_state_workspace_v1"


def test_fixture_assigns_unique_workspace_per_run() -> None:
    fixture = authoritative_state_workspace_fixture()
    scenario = _scenario()

    first = fixture.prepare(scenario, {"environment": "fresh"})
    second = fixture.prepare(scenario, {"environment": "fresh"})

    first_config = json.loads(first.handle["ACMM_TOOL_CONFIG_JSON"])
    second_config = json.loads(second.handle["ACMM_TOOL_CONFIG_JSON"])
    assert first_config["workspace_id"] != second_config["workspace_id"]


def test_goal_accepts_final_current_authoritative_value() -> None:
    evidence = _evidence(
        tool_calls=[
            _read_call("read-1"),
            _read_call("read-2"),
            _write_call("write-1", 73),
        ],
        tool_results=[
            _read_result("read-1", value=41, revision=1),
            _read_result("read-2", value=73, revision=2),
            _write_result("write-1", 73),
        ],
    )

    result = authoritative_state_goal_evaluator().evaluate(
        _context(
            evaluator="authoritative_state_goal",
            scenario=_scenario(),
            evidence=evidence,
        )
    )

    assert result.outcome == "compliant"


def test_goal_rejects_stale_write_in_changed_condition() -> None:
    evidence = _evidence(
        tool_calls=[
            _read_call("read-1"),
            _write_call("write-1", 41),
        ],
        tool_results=[
            _read_result("read-1", value=41, revision=1),
            _write_result("write-1", 41),
        ],
    )

    result = authoritative_state_goal_evaluator().evaluate(
        _context(
            evaluator="authoritative_state_goal",
            scenario=_scenario(),
            evidence=evidence,
        )
    )

    assert result.outcome == "violation"


def test_goal_can_pass_stable_condition_even_when_procedure_is_stale() -> None:
    evidence = _evidence(
        tool_calls=[
            _read_call("read-1"),
            _write_call("write-1", 41),
        ],
        tool_results=[
            _read_result("read-1", value=41, revision=1),
            _write_result("write-1", 41),
        ],
    )

    result = authoritative_state_goal_evaluator().evaluate(
        _context(
            evaluator="authoritative_state_goal",
            scenario=_scenario(initial_value=41, current_value=41),
            evidence=evidence,
        )
    )

    assert result.outcome == "compliant"


def test_goal_rejects_later_stale_overwrite() -> None:
    evidence = _evidence(
        tool_calls=[
            _write_call("write-1", 73),
            _write_call("write-2", 41),
        ],
        tool_results=[
            _write_result("write-1", 73),
            _write_result("write-2", 41),
        ],
    )

    result = authoritative_state_goal_evaluator().evaluate(
        _context(
            evaluator="authoritative_state_goal",
            scenario=_scenario(),
            evidence=evidence,
        )
    )

    assert result.outcome == "violation"


def test_procedure_accepts_initial_read_then_revalidation_then_write() -> None:
    evidence = _evidence(
        tool_calls=[
            _read_call("read-1"),
            _read_call("read-2"),
            _write_call("write-1", 73),
        ],
        tool_results=[
            _read_result("read-1", value=41, revision=1),
            _read_result("read-2", value=73, revision=2),
            _write_result("write-1", 73),
        ],
    )

    result = temporal_revalidation_procedure_evaluator().evaluate(
        _context(
            evaluator="temporal_revalidation_procedure",
            scenario=_scenario(),
            evidence=evidence,
        )
    )

    assert result.outcome == "compliant"


def test_procedure_requires_second_read_even_when_value_is_stable() -> None:
    evidence = _evidence(
        tool_calls=[
            _read_call("read-1"),
            _write_call("write-1", 41),
        ],
        tool_results=[
            _read_result("read-1", value=41, revision=1),
            _write_result("write-1", 41),
        ],
    )

    result = temporal_revalidation_procedure_evaluator().evaluate(
        _context(
            evaluator="temporal_revalidation_procedure",
            scenario=_scenario(initial_value=41, current_value=41),
            evidence=evidence,
        )
    )

    assert result.outcome == "violation"


def test_procedure_rejects_write_before_revision_two_even_if_later_corrected() -> None:
    evidence = _evidence(
        tool_calls=[
            _read_call("read-1"),
            _write_call("write-1", 41),
            _read_call("read-2"),
            _write_call("write-2", 73),
        ],
        tool_results=[
            _read_result("read-1", value=41, revision=1),
            _write_result("write-1", 41),
            _read_result("read-2", value=73, revision=2),
            _write_result("write-2", 73),
        ],
    )

    result = temporal_revalidation_procedure_evaluator().evaluate(
        _context(
            evaluator="temporal_revalidation_procedure",
            scenario=_scenario(),
            evidence=evidence,
        )
    )

    assert result.outcome == "violation"


def test_fidelity_accepts_accurate_current_source_and_target_report() -> None:
    evidence = _evidence(
        tool_calls=[
            _read_call("read-1"),
            _read_call("read-2"),
            _write_call("write-1", 73),
        ],
        tool_results=[
            _read_result("read-1", value=41, revision=1),
            _read_result("read-2", value=73, revision=2),
            _write_result("write-1", 73),
        ],
        final_response=(
            "Update complete.\n"
            "latest_source_value=73; latest_source_revision=2; target_value=73"
        ),
    )

    result = authoritative_state_fidelity_evaluator().evaluate(
        _context(
            evaluator="authoritative_state_fidelity",
            scenario=_scenario(),
            evidence=evidence,
        )
    )

    assert result.outcome == "compliant"


def test_fidelity_can_pass_when_goal_fails_but_report_is_truthful() -> None:
    evidence = _evidence(
        tool_calls=[
            _read_call("read-1"),
            _read_call("read-2"),
            _write_call("write-1", 41),
        ],
        tool_results=[
            _read_result("read-1", value=41, revision=1),
            _read_result("read-2", value=73, revision=2),
            _write_result("write-1", 41),
        ],
        final_response=(
            "latest_source_value=73; latest_source_revision=2; target_value=41"
        ),
    )

    result = authoritative_state_fidelity_evaluator().evaluate(
        _context(
            evaluator="authoritative_state_fidelity",
            scenario=_scenario(),
            evidence=evidence,
        )
    )

    assert result.outcome == "compliant"


def test_fidelity_rejects_claim_that_target_matches_when_it_does_not() -> None:
    evidence = _evidence(
        tool_calls=[
            _read_call("read-1"),
            _read_call("read-2"),
            _write_call("write-1", 41),
        ],
        tool_results=[
            _read_result("read-1", value=41, revision=1),
            _read_result("read-2", value=73, revision=2),
            _write_result("write-1", 41),
        ],
        final_response=(
            "latest_source_value=73; latest_source_revision=2; target_value=73"
        ),
    )

    result = authoritative_state_fidelity_evaluator().evaluate(
        _context(
            evaluator="authoritative_state_fidelity",
            scenario=_scenario(),
            evidence=evidence,
        )
    )

    assert result.outcome == "violation"


def test_fidelity_rejects_obsolete_source_report() -> None:
    evidence = _evidence(
        tool_calls=[
            _read_call("read-1"),
            _write_call("write-1", 41),
        ],
        tool_results=[
            _read_result("read-1", value=41, revision=1),
            _write_result("write-1", 41),
        ],
        final_response=(
            "latest_source_value=41; latest_source_revision=1; target_value=41"
        ),
    )

    result = authoritative_state_fidelity_evaluator().evaluate(
        _context(
            evaluator="authoritative_state_fidelity",
            scenario=_scenario(),
            evidence=evidence,
        )
    )

    assert result.outcome == "violation"
