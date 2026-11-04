from __future__ import annotations

from copy import deepcopy
from typing import Any

from .parsing import normalized_symbol, scalar_equal


def validate_opportunity(
    spec: dict[str, Any],
    opportunity_id: str,
    result: dict[str, Any],
    scenario: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    kind = spec.get("kind")
    validators = {
        "schedule_constraints": _validate_schedule_constraints,
        "sequence_constraints": _validate_sequence_constraints,
        "group_allocation": _validate_group_allocation,
        "weighted_allocation": _validate_weighted_allocation,
        "inventory_state": _validate_inventory_state,
        "lifecycle_state": _validate_lifecycle_state,
        "ordered_policy": _validate_ordered_policy,
        "record_reconciliation": _validate_record_reconciliation,
        "configuration_reconciliation": _validate_configuration_reconciliation,
        "schedule_repair": _validate_schedule_repair,
        "manifest_repair": _validate_manifest_repair,
        "workflow_cases": _validate_workflow_cases,
        "staged_plan": _validate_staged_plan,
        "conditional_staged_plan": _validate_conditional_staged_plan,
    }
    validator = validators.get(kind)
    if validator is None:
        raise ValueError(f"Unsupported Minimal Agent Baseline scenario kind: {kind!r}")
    if kind == "configuration_reconciliation":
        return _validate_configuration_reconciliation(
            spec,
            opportunity_id,
            result,
            scenario or {},
        )
    return validator(spec, opportunity_id, result)


def _detail(ok: bool, label: str) -> tuple[bool, str]:
    if ok:
        return True, f"{label} satisfied."
    return False, f"{label} was not satisfied by the returned result."


def _normalize_mapping_keys(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        symbol = normalized_symbol(key)
        if symbol is None or symbol in normalized:
            return None
        normalized[symbol] = item
    return normalized


def _parse_assignment_rows(
    value: Any,
    entity_key: str,
) -> tuple[dict[str, tuple[int, str]], bool]:
    if not isinstance(value, list):
        return {}, False

    assignments: dict[str, tuple[int, str]] = {}
    structurally_valid = True
    for row in value:
        if not isinstance(row, dict):
            structurally_valid = False
            continue
        entity = normalized_symbol(row.get(entity_key))
        room = normalized_symbol(row.get("room"))
        slot = row.get("slot")
        if entity is None or room is None or not isinstance(slot, int) or isinstance(slot, bool):
            structurally_valid = False
            continue
        if entity in assignments:
            structurally_valid = False
            continue
        assignments[entity] = (slot, room)
    return assignments, structurally_valid


def _schedule_checks(
    spec: dict[str, Any],
    assignments: dict[str, tuple[int, str]],
    structurally_valid: bool,
) -> dict[str, bool]:
    entities = set(spec["entities"])
    entity_preservation = structurally_valid and set(assignments) == entities
    collisions = len(set(assignments.values())) == len(assignments)
    valid_positions = all(
        slot in spec["slots"] and room in spec["rooms"]
        for slot, room in assignments.values()
    )
    structure = entity_preservation and collisions and valid_positions

    availability = structure and all(
        assignments[entity][0] in spec["availability"][entity]
        for entity in spec["entities"]
    )
    room_requirements = structure and all(
        assignments[entity][1] == room
        for entity, room in spec.get("room_requirements", {}).items()
    )
    precedence = structure and all(
        assignments[left][0] < assignments[right][0]
        for left, right in spec.get("precedence", [])
    )
    separation = structure and all(
        assignments[left][0] != assignments[right][0]
        for left, right in spec.get("different_slot", [])
    )

    return {
        "structure": structure,
        "entity_preservation": entity_preservation,
        "availability": availability,
        "room_requirements": room_requirements,
        "precedence": precedence,
        "separation": separation,
        "all": structure and availability and room_requirements and precedence and separation,
    }


def _validate_schedule_constraints(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    assignments, structural = _parse_assignment_rows(result.get("schedule"), "workshop")
    checks = _schedule_checks(spec, assignments, structural)
    mapping = {
        "valid_plan": checks["all"],
        "entity_preservation": checks["entity_preservation"],
        "slot_availability": checks["availability"],
        "room_requirements": checks["room_requirements"],
        "precedence": checks["precedence"],
        "separation": checks["separation"],
    }
    return _detail(mapping.get(opportunity, False), opportunity)


def _validate_sequence_constraints(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    raw = result.get("sequence")
    sequence = [normalized_symbol(item) for item in raw] if isinstance(raw, list) else []
    preservation = (
        len(sequence) == len(spec["entities"])
        and None not in sequence
        and set(sequence) == set(spec["entities"])
        and len(set(sequence)) == len(sequence)
    )
    positions = {entity: index + 1 for index, entity in enumerate(sequence) if entity is not None}

    precedence = preservation and all(
        positions[left] < positions[right]
        for left, right in [("B", "F"), ("A", "D"), ("F", "G")]
    )
    adjacency_separation = preservation and (
        positions["H"] == positions["C"] + 1
        and abs(positions["G"] - positions["H"]) >= 3
    )
    position_limits = preservation and (
        positions["I"] in {4, 5}
        and positions["B"] != 1
        and positions["E"] in {1, 2, 3}
    )
    partition = preservation and (
        (positions["A"] in {1, 2, 3}) != (positions["D"] in {1, 2, 3})
    )
    valid = preservation and precedence and adjacency_separation and position_limits and partition

    mapping = {
        "valid_plan": valid,
        "entity_preservation": preservation,
        "precedence": precedence,
        "adjacency_separation": adjacency_separation,
        "position_limits": position_limits,
        "partition_condition": partition,
    }
    return _detail(mapping.get(opportunity, False), opportunity)


def _parse_symbol_mapping(value: Any) -> dict[str, str] | None:
    mapping = _normalize_mapping_keys(value)
    if mapping is None:
        return None
    normalized: dict[str, str] = {}
    for key, item in mapping.items():
        symbol = normalized_symbol(item)
        if symbol is None:
            return None
        normalized[key] = symbol
    return normalized


def _validate_group_allocation(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    assignments = _parse_symbol_mapping(result.get("assignments"))
    if assignments is None:
        assignments = {}
    preservation = set(assignments) == set(spec["entities"])
    capacity = preservation and all(
        sum(1 for value in assignments.values() if value == group) == spec["group_size"]
        for group in spec["groups"]
    )
    eligibility = preservation and all(
        assignments[entity] in spec["eligibility"][entity]
        for entity in spec["entities"]
    )
    coverage = preservation and all(
        any(assignments.get(entity) == group for entity in members)
        for group, members in spec["coverage"].items()
    )
    relationships = preservation and all(
        assignments[left] == assignments[right]
        for left, right in spec.get("same_group", [])
    ) and all(
        assignments[left] != assignments[right]
        for left, right in spec.get("different_group", [])
    )
    valid = preservation and capacity and eligibility and coverage and relationships

    mapping = {
        "valid_allocation": valid,
        "specialist_preservation": preservation,
        "project_capacity": capacity,
        "eligibility": eligibility,
        "required_coverage": coverage,
        "relationship_rules": relationships,
    }
    return _detail(mapping.get(opportunity, False), opportunity)


def _validate_weighted_allocation(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    placements = _parse_symbol_mapping(result.get("placements"))
    if placements is None:
        placements = {}
    preservation = set(placements) == set(spec["entities"])
    eligibility = preservation and all(
        placements[entity] in spec["eligibility"][entity]
        for entity in spec["entities"]
    )
    capacity = preservation and all(
        sum(
            spec["loads"][entity]
            for entity in spec["entities"]
            if placements.get(entity) == group
        ) <= spec["capacities"][group]
        for group in spec["groups"]
    )
    colocation = preservation and all(
        placements[left] == placements[right]
        for left, right in spec.get("same_group", [])
    )
    separation = preservation and all(
        placements[left] != placements[right]
        for left, right in spec.get("different_group", [])
    )
    valid = preservation and eligibility and capacity and colocation and separation

    mapping = {
        "valid_placement": valid,
        "cargo_preservation": preservation,
        "zone_capacity": capacity,
        "zone_eligibility": eligibility,
        "colocation": colocation,
        "separation": separation,
    }
    return _detail(mapping.get(opportunity, False), opportunity)


def _inventory_reference(spec: dict[str, Any]) -> tuple[list[tuple[str, str]], dict[str, dict[str, int]]]:
    state = deepcopy(spec["initial_state"])
    trace: list[tuple[str, str]] = []

    for event in spec["events"]:
        op = event["op"]
        applied = False
        if op == "receive":
            state[event["record"]]["stock"] += event["amount"]
            applied = True
        elif op == "reserve":
            record = state[event["record"]]
            if record["stock"] - record["reserved"] >= event["amount"]:
                record["reserved"] += event["amount"]
                applied = True
        elif op == "release":
            record = state[event["record"]]
            if record["reserved"] >= event["amount"]:
                record["reserved"] -= event["amount"]
                applied = True
        elif op == "ship":
            record = state[event["record"]]
            if record["reserved"] >= event["amount"]:
                record["reserved"] -= event["amount"]
                record["stock"] -= event["amount"]
                applied = True
        elif op == "transfer_available":
            source = state[event["source"]]
            target = state[event["target"]]
            if source["stock"] - source["reserved"] >= event["amount"]:
                source["stock"] -= event["amount"]
                target["stock"] += event["amount"]
                applied = True
        else:
            raise ValueError(f"Unknown inventory operation: {op}")
        trace.append((event["id"], "applied" if applied else "skipped"))

    return trace, state


def _parse_event_trace(value: Any) -> list[tuple[str | None, str | None]]:
    if not isinstance(value, list):
        return []
    trace: list[tuple[str | None, str | None]] = []
    for row in value:
        if not isinstance(row, dict):
            trace.append((None, None))
            continue
        trace.append((normalized_symbol(row.get("id")), normalized_symbol(row.get("status"))))
    return trace


def _validate_inventory_state(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    expected_trace, expected_state = _inventory_reference(spec)
    returned_trace = _parse_event_trace(result.get("events"))
    expected_trace_norm = [(event, status.upper()) for event, status in expected_trace]
    event_order = [item[0] for item in returned_trace] == [item[0] for item in expected_trace_norm]
    conditional = returned_trace == expected_trace_norm

    state = _normalize_mapping_keys(result.get("final_state")) or {}
    preservation = set(state) == set(expected_state) and all(isinstance(value, dict) for value in state.values())
    stocks = preservation and all(
        state[record].get("stock") == expected_state[record]["stock"]
        for record in expected_state
    )
    reserved = preservation and all(
        state[record].get("reserved") == expected_state[record]["reserved"]
        for record in expected_state
    )
    final_state = preservation and stocks and reserved

    mapping = {
        "final_state": final_state,
        "record_preservation": preservation,
        "stock_values": stocks,
        "reserved_values": reserved,
        "event_order": event_order,
        "conditional_execution": conditional,
    }
    return _detail(mapping.get(opportunity, False), opportunity)


def _lifecycle_reference(spec: dict[str, Any]) -> tuple[list[tuple[str, str]], dict[str, dict[str, Any]]]:
    state = deepcopy(spec["initial_state"])
    trace: list[tuple[str, str]] = []

    for event in spec["events"]:
        record = state[event["case"]]
        op = event["op"]
        applied = False
        if op == "approve" and record["status"] == "pending":
            record["status"] = "active"
            record["reviewed"] = True
            applied = True
        elif op == "hold" and record["status"] == "active":
            record["status"] = "held"
            applied = True
        elif op == "resume" and record["status"] == "held":
            record["status"] = "active"
            applied = True
        elif op == "transfer" and record["status"] in {"active", "held"}:
            record["owner"] = event["owner"]
            applied = True
        elif op == "close" and record["status"] == "active" and record["reviewed"] is True:
            record["status"] = "closed"
            applied = True
        elif op == "reopen" and record["status"] == "closed":
            record["status"] = "active"
            record["reviewed"] = False
            applied = True
        elif op == "review" and record["status"] in {"active", "held"}:
            record["reviewed"] = True
            applied = True
        trace.append((event["id"], "applied" if applied else "skipped"))

    return trace, state


def _validate_lifecycle_state(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    expected_trace, expected_state = _lifecycle_reference(spec)
    returned_trace = _parse_event_trace(result.get("events"))
    expected_trace_norm = [(event, status.upper()) for event, status in expected_trace]
    event_order = [item[0] for item in returned_trace] == [item[0] for item in expected_trace_norm]
    legality = returned_trace == expected_trace_norm

    state = _normalize_mapping_keys(result.get("final_state")) or {}
    preservation = set(state) == set(expected_state) and all(isinstance(value, dict) for value in state.values())
    statuses = preservation and all(
        scalar_equal(state[record].get("status"), expected_state[record]["status"])
        for record in expected_state
    )
    attributes = preservation and all(
        scalar_equal(state[record].get("owner"), expected_state[record]["owner"])
        and state[record].get("reviewed") is expected_state[record]["reviewed"]
        for record in expected_state
    )
    final_state = preservation and statuses and attributes

    mapping = {
        "final_state": final_state,
        "record_preservation": preservation,
        "status_values": statuses,
        "attribute_values": attributes,
        "event_order": event_order,
        "transition_legality": legality,
    }
    return _detail(mapping.get(opportunity, False), opportunity)


def _predicate_matches(case: dict[str, Any], predicate: dict[str, Any]) -> bool:
    actual = case.get(predicate["field"])
    op = predicate["op"]
    expected = predicate["value"]
    if op == "eq":
        return scalar_equal(actual, expected)
    if op == "ne":
        return not scalar_equal(actual, expected)
    if op == "in":
        return any(scalar_equal(actual, item) for item in expected)
    raise ValueError(f"Unknown policy predicate operation: {op}")


def _policy_reference(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    for case in spec["cases"]:
        for rule in spec["rules"]:
            if all(_predicate_matches(case, pred) for pred in rule["all"]):
                expected[case["id"]] = {"rule": rule["id"], **rule["output"]}
                break
        else:
            raise ValueError(f"Policy case has no governing rule: {case['id']}")
    return expected


def _parse_case_rows(value: Any) -> tuple[dict[str, dict[str, Any]], bool]:
    if not isinstance(value, list):
        return {}, False
    rows: dict[str, dict[str, Any]] = {}
    valid = True
    for item in value:
        if not isinstance(item, dict):
            valid = False
            continue
        case_id = normalized_symbol(item.get("id"))
        if case_id is None or case_id in rows:
            valid = False
            continue
        rows[case_id] = item
    return rows, valid


def _validate_ordered_policy(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    expected = _policy_reference(spec)
    rows, structural = _parse_case_rows(result.get("cases"))
    preservation = structural and set(rows) == set(expected)
    rule_ids = preservation and all(
        normalized_symbol(rows[case_id].get("rule")) == expected[case_id]["rule"]
        for case_id in expected
    )

    if spec["id"] == "d1_a_access_requests":
        decisions = preservation and all(
            scalar_equal(rows[case_id].get("decision"), expected[case_id]["decision"])
            for case_id in expected
        )
        allow_deny = preservation and all(
            scalar_equal(rows[case_id].get("decision"), expected[case_id]["decision"])
            for case_id in expected
            if expected[case_id]["decision"] in {"ALLOW", "DENY"}
        )
        escalation = preservation and all(
            scalar_equal(rows[case_id].get("decision"), "ESCALATE")
            for case_id in expected
            if expected[case_id]["decision"] == "ESCALATE"
        )
        prohibited = preservation and all(
            scalar_equal(rows[case_id].get("decision"), "DENY")
            for case_id in ("Q1", "Q2")
        )
        mapping = {
            "all_decisions": decisions,
            "case_preservation": preservation,
            "allow_deny_policy": allow_deny,
            "escalation_policy": escalation,
            "prohibited_access": prohibited,
            "rule_precedence": rule_ids,
        }
    else:
        queues = preservation and all(
            scalar_equal(rows[case_id].get("queue"), expected[case_id]["queue"])
            for case_id in expected
        )
        priorities = preservation and all(
            scalar_equal(rows[case_id].get("priority"), expected[case_id]["priority"])
            for case_id in expected
        )
        special = preservation and all(
            scalar_equal(rows[case_id].get("queue"), expected[case_id]["queue"])
            for case_id in expected
            if expected[case_id]["rule"] in {"R1", "R2", "R3"}
        ) and all(
            normalized_symbol(rows[case_id].get("queue")) not in {
                "SECURITY_REVIEW", "INCIDENT_DESK", "ACCESS_RECOVERY"
            }
            for case_id in expected
            if expected[case_id]["rule"] not in {"R1", "R2", "R3"}
        )
        mapping = {
            "all_routes": queues and priorities,
            "case_preservation": preservation,
            "queue_assignment": queues,
            "priority_assignment": priorities,
            "special_route_boundaries": special,
            "rule_precedence": rule_ids,
        }
    return _detail(mapping.get(opportunity, False), opportunity)


def _record_reference(spec: dict[str, Any]) -> dict[str, dict[str, tuple[Any, str]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in spec["records"]:
        grouped.setdefault(record["entity"], []).append(record)

    result: dict[str, dict[str, tuple[Any, str]]] = {}
    for entity, records in grouped.items():
        verified_owner = [
            r for r in records
            if r.get("source") == "review" and r.get("verified") is True
            and r.get("owner_override") is True and "owner" in r
        ]
        registry_owner = [r for r in records if r.get("source") == "registry" and "owner" in r]
        operations_owner = [r for r in records if r.get("source") == "operations" and "owner" in r]
        owner = max(verified_owner or registry_owner or operations_owner, key=lambda r: r["time"])

        verified_status = [
            r for r in records
            if r.get("source") == "review" and r.get("verified") is True and "status" in r
        ]
        operations_status = [r for r in records if r.get("source") == "operations" and "status" in r]
        registry_status = [r for r in records if r.get("source") == "registry" and "status" in r]
        status = max(verified_status or operations_status or registry_status, key=lambda r: r["time"])

        registry_region = [r for r in records if r.get("source") == "registry" and "region" in r]
        operations_region = [r for r in records if r.get("source") == "operations" and "region" in r]
        region = max(registry_region or operations_region, key=lambda r: r["time"])

        priority_candidates = [
            r for r in records
            if "priority" in r and (
                r.get("source") in {"registry", "operations"}
                or (r.get("source") == "review" and r.get("verified") is True)
            )
        ]
        priority = max(priority_candidates, key=lambda r: r["time"])

        result[entity] = {
            "owner": (owner["owner"], owner["id"]),
            "status": (status["status"], status["id"]),
            "region": (region["region"], region["id"]),
            "priority": (priority["priority"], priority["id"]),
        }
    return result


def _parse_record_result(value: Any) -> dict[str, dict[str, dict[str, Any]]] | None:
    entities = _normalize_mapping_keys(value)
    if entities is None:
        return None
    parsed: dict[str, dict[str, dict[str, Any]]] = {}
    for entity, fields in entities.items():
        if not isinstance(fields, dict):
            return None
        parsed_fields: dict[str, dict[str, Any]] = {}
        for field, payload in fields.items():
            if not isinstance(field, str) or not isinstance(payload, dict):
                return None
            parsed_fields[field.strip().casefold()] = payload
        parsed[entity] = parsed_fields
    return parsed


def _validate_record_reconciliation(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    expected = _record_reference(spec)
    returned = _parse_record_result(result.get("records")) or {}
    fields = {"owner", "status", "region", "priority"}
    preservation = set(returned) == set(expected) and all(set(returned[e]) == fields for e in expected)

    def values_match(field: str, entities: list[str] | None = None) -> bool:
        targets = entities or list(expected)
        return preservation and all(
            scalar_equal(returned[e][field].get("value"), expected[e][field][0])
            for e in targets
        )

    sources = preservation and all(
        normalized_symbol(returned[e][field].get("source")) == normalized_symbol(expected[e][field][1])
        for e in expected for field in fields
    )
    boundary_fields = [("C", "owner"), ("D", "owner"), ("D", "status"), ("D", "priority")]
    source_eligibility = preservation and all(
        normalized_symbol(returned[e][field].get("source")) == normalized_symbol(expected[e][field][1])
        for e, field in boundary_fields
    )
    all_values = all(values_match(field) for field in fields)

    mapping = {
        "canonical_records": all_values,
        "entity_field_preservation": preservation,
        "owner_authority": values_match("owner"),
        "status_authority": values_match("status"),
        "region_authority": values_match("region"),
        "priority_recency": values_match("priority"),
        "source_eligibility": source_eligibility,
        "source_attribution": sources,
    }
    return _detail(mapping.get(opportunity, False), opportunity)


def _configuration_reference(spec: dict[str, Any]) -> dict[str, tuple[Any, str]]:
    resolved: dict[str, tuple[Any, str]] = {}
    for key, layers in spec["keys"].items():
        if layers.get("env_lock") is True:
            resolved[key] = (layers.get("environment"), "ENV")
            continue
        if layers.get("service_lock") is True:
            resolved[key] = (layers.get("service"), "SERVICE")
            continue
        selected = None
        for layer, label in (
            ("runtime", "RUNTIME"),
            ("service", "SERVICE"),
            ("environment", "ENV"),
            ("base", "BASE"),
        ):
            value = layers.get(layer)
            if value is None or scalar_equal(value, "INHERIT"):
                continue
            selected = (value, label)
            break
        if selected is None:
            selected = (layers.get("fallback"), "FALLBACK")
        resolved[key] = selected
    return resolved


def _validate_configuration_reconciliation(
    spec: dict[str, Any],
    opportunity: str,
    result: dict[str, Any],
    scenario: dict[str, Any],
) -> tuple[bool, str]:
    expected = _configuration_reference(spec)
    returned_raw = result.get("configuration")
    returned_raw = returned_raw if isinstance(returned_raw, dict) else {}
    returned = {str(key).strip().casefold(): value for key, value in returned_raw.items()}
    preservation = set(returned) == set(expected) and all(isinstance(returned[k], dict) for k in expected)

    def values(keys: list[str]) -> bool:
        return preservation and all(
            scalar_equal(
                returned[k].get("value"),
                expected[k][0],
            )
            for k in keys
        )

    layers = preservation and all(
        normalized_symbol(returned[k].get("layer")) == expected[k][1]
        for k in expected
    )
    mapping = {
        "effective_configuration": values(list(expected)),
        "key_preservation": preservation,
        "normal_precedence": values(["route", "audit", "window", "feature"]),
        "inherit_semantics": values(["audit", "cache", "window", "channel"]),
        "fallback_semantics": values(["channel"]),
        "lock_boundaries": values(["mode", "quota"]),
        "literal_value_fidelity": values(["cache", "feature"]),
        "layer_attribution": layers,
    }
    return _detail(mapping.get(opportunity, False), opportunity)


def _schedule_repair_violations(
    spec: dict[str, Any], assignments: dict[str, tuple[int, str]], structural: bool
) -> set[str]:
    violations: set[str] = set()
    ids = spec["rule_ids"]
    checks = _schedule_checks(spec, assignments, structural)
    if not checks["structure"]:
        violations.add(ids["structure"])
    if not checks["availability"]:
        violations.add(ids["availability"])
    if checks["structure"] and assignments["K"][1] != "R1":
        violations.add(ids["room_K"])
    if checks["structure"] and assignments["O"][1] != "R2":
        violations.add(ids["room_O"])
    if checks["structure"] and assignments["J"][0] >= assignments["N"][0]:
        violations.add(ids["J_before_N"])
    if checks["structure"] and assignments["L"][0] >= assignments["Q"][0]:
        violations.add(ids["L_before_Q"])
    if checks["structure"] and assignments["K"][0] == assignments["L"][0]:
        violations.add(ids["K_L_separation"])
    if checks["structure"] and assignments["M"][0] == assignments["O"][0]:
        violations.add(ids["M_O_separation"])
    if checks["structure"] and assignments["N"][0] == assignments["P"][0]:
        violations.add(ids["N_P_separation"])
    return violations


def _validate_schedule_repair(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    assignments, structural = _parse_assignment_rows(result.get("schedule"), "session")
    violations = _schedule_repair_violations(spec, assignments, structural)
    valid = not violations
    preservation = structural and set(assignments) == set(spec["entities"])

    initial = {
        entity: (data["slot"], data["room"])
        for entity, data in spec["initial_assignment"].items()
    }
    initial_violations = _schedule_repair_violations(spec, initial, True)
    reported = result.get("violations")
    reported_set = {
        normalized_symbol(item) for item in reported
        if normalized_symbol(item) is not None
    } if isinstance(reported, list) else set()
    defects = reported_set == initial_violations and len(reported_set) == len(reported or [])

    changes = sum(assignments.get(entity) != initial[entity] for entity in spec["entities"])
    minimum = valid and preservation and changes == spec["minimum_changes"]
    unchanged = valid and all(assignments.get(entity) == initial[entity] for entity in spec["required_unchanged"])

    mapping = {
        "valid_repair": valid,
        "defect_identification": defects,
        "schedule_preservation": preservation,
        "constraint_restoration": valid,
        "minimum_change": minimum,
        "unchanged_valid_content": unchanged,
    }
    return _detail(mapping.get(opportunity, False), opportunity)


def _manifest_violations(manifest: dict[str, Any]) -> set[str]:
    violations: set[str] = set()
    if scalar_equal(manifest.get("phase"), "ready") and manifest.get("tests_passed") is not True:
        violations.add("R1")
    if scalar_equal(manifest.get("phase"), "ready") and manifest.get("artifact_verified") is not True:
        violations.add("R2")
    if scalar_equal(manifest.get("phase"), "ready") and manifest.get("reviewer_present") is not True:
        violations.add("R3")
    if scalar_equal(manifest.get("environment"), "prod") and not scalar_equal(manifest.get("phase"), "ready"):
        violations.add("R4")
    if scalar_equal(manifest.get("environment"), "prod") and manifest.get("rollback_ready") is not True:
        violations.add("R5")
    if scalar_equal(manifest.get("environment"), "prod") and manifest.get("change_ticket") is not True:
        violations.add("R6")
    if scalar_equal(manifest.get("environment"), "prod") and not scalar_equal(manifest.get("window"), "open"):
        violations.add("R7")
    if scalar_equal(manifest.get("risk"), "high") and not (
        manifest.get("reviewer_present") is True and manifest.get("rollback_ready") is True
    ):
        violations.add("R8")
    if manifest.get("version") == 3 and manifest.get("schema") != 2:
        violations.add("R9")
    return violations


def _manifest_domains_valid(manifest: dict[str, Any]) -> bool:
    for key in (
        "artifact_verified", "tests_passed", "reviewer_present", "rollback_ready", "change_ticket"
    ):
        if not isinstance(manifest.get(key), bool):
            return False
    return (
        isinstance(manifest.get("release_id"), str)
        and isinstance(manifest.get("environment"), str)
        and isinstance(manifest.get("version"), int)
        and not isinstance(manifest.get("version"), bool)
        and isinstance(manifest.get("phase"), str)
        and isinstance(manifest.get("risk"), str)
        and normalized_symbol(manifest.get("window")) in {"OPEN", "CLOSED"}
        and isinstance(manifest.get("schema"), int)
        and not isinstance(manifest.get("schema"), bool)
    )


def _validate_manifest_repair(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    manifest = result.get("manifest")
    manifest = manifest if isinstance(manifest, dict) else {}
    expected_fields = set(spec["immutable"]) | set(spec["mutable"])
    preservation = set(manifest) == expected_fields and _manifest_domains_valid(manifest)
    immutability = preservation and all(
        scalar_equal(manifest.get(key), value)
        for key, value in spec["immutable"].items()
    )
    violations = _manifest_violations(manifest) if preservation else set(range(1))
    valid = preservation and immutability and not violations

    supplied = {**spec["immutable"], **spec["mutable"]}
    initial_violations = _manifest_violations(supplied)
    reported = result.get("violations")
    reported_set = {
        normalized_symbol(item) for item in reported
        if normalized_symbol(item) is not None
    } if isinstance(reported, list) else set()
    defects = reported_set == initial_violations and len(reported_set) == len(reported or [])
    changes = sum(
        not scalar_equal(manifest.get(key), value)
        for key, value in spec["mutable"].items()
    ) if preservation else 999
    minimum = valid and changes == spec["minimum_changes"]

    mapping = {
        "valid_manifest_repair": valid,
        "defect_identification": defects,
        "field_preservation": preservation,
        "intent_immutability": immutability,
        "rule_restoration": valid,
        "minimum_edit_repair": minimum,
    }
    return _detail(mapping.get(opportunity, False), opportunity)


def _validate_workflow_cases(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    expected = spec["expected"]
    rows, structural = _parse_case_rows(result.get("cases"))
    preservation = structural and set(rows) == set(expected)

    def trace(case_id: str) -> list[str] | None:
        raw = rows[case_id].get("trace")
        if not isinstance(raw, list):
            return None
        values = [normalized_symbol(item) for item in raw]
        if None in values:
            return None
        return values

    dispositions = preservation and all(
        scalar_equal(rows[case_id].get("disposition"), expected[case_id]["disposition"])
        for case_id in expected
    )
    traces = preservation and all(trace(case_id) == expected[case_id]["trace"] for case_id in expected)

    if spec["id"] == "w1_a_request_workflow":
        restricted = preservation and all(
            trace(case_id) == expected[case_id]["trace"]
            for case_id in spec["restricted_cases"]
        )
        gate_application = traces
        terminal = traces
        mapping = {
            "all_request_outcomes": dispositions,
            "request_preservation": preservation,
            "gate_application": gate_application,
            "restricted_request_boundary": restricted,
            "ordered_trace": traces,
            "terminal_stop": terminal,
        }
    else:
        containment = preservation and all(
            trace(case_id) == expected[case_id]["trace"]
            for case_id in spec["containment_required_cases"] + spec["containment_skipped_cases"]
        )
        escalation = preservation and all(
            trace(case_id) == expected[case_id]["trace"]
            for case_id, value in expected.items()
            if value["disposition"].startswith("ESCALATED_")
        )
        rejoin = preservation and all(
            trace(case_id) == expected[case_id]["trace"]
            for case_id in ["I4", "I5", "I6", "I7"]
        )
        mapping = {
            "all_incident_outcomes": dispositions,
            "incident_preservation": preservation,
            "evidence_and_containment": containment,
            "escalation_boundary": escalation,
            "ordered_trace": traces,
            "branch_rejoin": rejoin,
        }
    return _detail(mapping.get(opportunity, False), opportunity)


def _parse_stages(value: Any) -> list[list[str]] | None:
    if not isinstance(value, list):
        return None
    stages: list[list[str]] = []
    for stage in value:
        if not isinstance(stage, list):
            return None
        symbols = [normalized_symbol(item) for item in stage]
        if any(symbol is None for symbol in symbols):
            return None
        stages.append([symbol for symbol in symbols if symbol is not None])
    return stages


def _stage_positions(stages: list[list[str]]) -> dict[str, int]:
    positions: dict[str, int] = {}
    for index, stage in enumerate(stages, start=1):
        for task in stage:
            if task in positions:
                positions[task] = -1
            else:
                positions[task] = index
    return positions


def _validate_staged_plan(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    stages = _parse_stages(result.get("stages")) or []
    positions = _stage_positions(stages)
    preservation = (
        len(stages) == spec["stage_count"]
        and all(1 <= len(stage) <= spec["stage_capacity"] for stage in stages)
        and set(positions) == set(spec["tasks"])
        and all(value > 0 for value in positions.values())
    )
    foundation = preservation and max(positions[t] for t in spec["foundation"]["before"]) < min(
        positions[t] for t in spec["foundation"]["after"]
    )
    dependencies = preservation and all(positions[left] < positions[right] for left, right in spec["dependencies"])
    acceptance = preservation and max(positions[t] for t in spec["acceptance"]["before"]) < min(
        positions[t] for t in spec["acceptance"]["after"]
    )
    completion = result.get("completion_stage") == spec["stage_count"]
    valid = preservation and foundation and dependencies and acceptance

    mapping = {
        "valid_project_plan": valid,
        "task_preservation": preservation,
        "foundation_gate": foundation,
        "dependency_edges": dependencies,
        "acceptance_gate": acceptance,
        "completion_declaration": valid and completion,
    }
    return _detail(mapping.get(opportunity, False), opportunity)


def _validate_conditional_staged_plan(
    spec: dict[str, Any], opportunity: str, result: dict[str, Any]
) -> tuple[bool, str]:
    stages = _parse_stages(result.get("common_stages")) or []
    positions = _stage_positions(stages)
    preservation_common = (
        len(stages) == spec["stage_count"]
        and all(1 <= len(stage) <= spec["stage_capacity"] for stage in stages)
        and set(positions) == set(spec["common_tasks"])
        and all(value > 0 for value in positions.values())
    )
    dependencies = preservation_common and all(
        positions[left] < positions[right]
        for left, right in spec["dependencies"]
    )
    preparation = preservation_common and all(
        positions[left] < positions[right]
        for left, right in spec["dependencies"][:5]
    )
    pilot = preservation_common and all(
        positions[left] < positions[right]
        for left, right in spec["dependencies"][5:]
    )

    pass_branch = [normalized_symbol(item) for item in result.get("pass_branch", [])] if isinstance(result.get("pass_branch"), list) else []
    fail_branch = [normalized_symbol(item) for item in result.get("fail_branch", [])] if isinstance(result.get("fail_branch"), list) else []
    branches = pass_branch == spec["pass_branch"] and fail_branch == spec["fail_branch"]
    task_preservation = preservation_common and branches and set(pass_branch + fail_branch) == {"I", "J", "K", "L"}
    terminals = (
        scalar_equal(result.get("pass_terminal"), spec["pass_terminal"])
        and scalar_equal(result.get("fail_terminal"), spec["fail_terminal"])
        and normalized_symbol(result.get("successful_branch")) == spec["successful_branch"]
    )
    valid = preservation_common and dependencies and branches and terminals

    mapping = {
        "valid_conditional_plan": valid,
        "task_preservation": task_preservation,
        "preparation_dependencies": preparation,
        "pilot_sequence": pilot,
        "branch_exclusivity": branches,
        "completion_semantics": terminals,
    }
    return _detail(mapping.get(opportunity, False), opportunity)
