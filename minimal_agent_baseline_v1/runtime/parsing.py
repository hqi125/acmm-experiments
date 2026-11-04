from __future__ import annotations

from typing import Any


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
