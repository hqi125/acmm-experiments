from __future__ import annotations

from typing import Any, Mapping


_PACKAGE_MARKER_PREFIX = "<!-- acmm-fixture:github_workspace_"
_PACKAGE_BRANCH_PREFIX = "acmm/fixture/"


def package_owned_body(value: Any) -> bool:
    return isinstance(value, str) and _PACKAGE_MARKER_PREFIX in value


def package_owned_branch(name: Any) -> bool:
    return isinstance(name, str) and name.startswith(_PACKAGE_BRANCH_PREFIX)


def package_owned_catalog_item(item: Mapping[str, Any]) -> bool:
    return package_owned_body(item.get("body"))
