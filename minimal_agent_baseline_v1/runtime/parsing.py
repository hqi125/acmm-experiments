from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acmm.experiment_api import decode_json_object_text


_RESULT_FIELD_BY_KIND = {
    "schedule_constraints": "schedule",
    "sequence_constraints": "sequence",
    "group_allocation": "assignments",
    "weighted_allocation": "placements",
    "inventory_state": "events",
    "lifecycle_state": "events",
    "ordered_policy": "cases",
    "record_reconciliation": "records",
    "configuration_reconciliation": "configuration",
    "schedule_repair": "schedule",
    "manifest_repair": "manifest",
    "workflow_cases": "cases",
    "staged_plan": "stages",
    "conditional_staged_plan": "common_stages",
}


@dataclass(frozen=True)
class parsed_result_object:
    value: dict[str, Any]
    normalizations: tuple[str, ...] = ()


def load_result_object(
    text: str,
    scenario_kind: str,
) -> parsed_result_object | None:
    expected_field = _RESULT_FIELD_BY_KIND.get(scenario_kind)
    if expected_field is None:
        raise ValueError(f"Unsupported Minimal Agent Baseline scenario kind: {scenario_kind!r}")

    wrapper = decode_json_object_text(
        text,
        required_keys=("result",),
    )
    if wrapper is not None:
        result = wrapper.value.get("result")
        if isinstance(result, dict):
            return parsed_result_object(
                value=result,
                normalizations=wrapper.normalizations,
            )
        if isinstance(result, str):
            nested = decode_json_object_text(
                result,
                required_keys=(expected_field,),
            )
            if nested is not None:
                return parsed_result_object(
                    value=nested.value,
                    normalizations=(
                        *wrapper.normalizations,
                        "result_string_unwrap",
                        *nested.normalizations,
                    ),
                )
        return None

    # If the outer ``{"result": ...}`` wrapper itself is damaged, recover only an object carrying
    # the scenario's expected payload field.  This prevents a decodable child row from being
    # mistaken for the complete answer.
    payload = decode_json_object_text(
        text,
        required_keys=(expected_field,),
    )
    if payload is None:
        return None

    return parsed_result_object(
        value=payload.value,
        normalizations=payload.normalizations,
    )


def normalized_symbol(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip().upper()


def scalar_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, str) and isinstance(right, str):
        return left.strip().casefold() == right.strip().casefold()
    return left == right
