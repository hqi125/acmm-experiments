from __future__ import annotations

import json
from typing import Any


def load_result_object(text: str) -> dict[str, Any] | None:
    response = _decode_object(text)
    if response is None:
        return None

    result = response.get("result", response)
    if not isinstance(result, dict):
        return None
    return result


def _decode_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None

    direct = _try_json(stripped)
    if isinstance(direct, dict):
        return direct

    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []

    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            objects.append(value)

    if not objects:
        return None
    return objects[-1]


def _try_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


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
