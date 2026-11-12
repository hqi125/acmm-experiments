from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "github_mcp_project_workspace_v1"
RUNTIME = ROOT / "runtime"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_direct_github_http_clients_are_confined_to_transport_modules() -> None:
    approved = {"controller.py", "github_app.py"}
    http_roots = {"urllib", "requests", "httpx", "aiohttp", "http"}
    offenders: list[str] = []
    for path in sorted(RUNTIME.glob("*.py")):
        imports = _imports(path)
        uses_http_client = any(
            name.split(".", 1)[0] in http_roots
            for name in imports
        )
        text = path.read_text(encoding="utf-8")
        uses_http_shell = any(
            marker in text
            for marker in (
                '["curl"',
                "['curl'",
                '["wget"',
                "['wget'",
                '["gh", "api"',
                "['gh', 'api'",
            )
        )
        if (uses_http_client or uses_http_shell) and path.name not in approved:
            offenders.append(path.name)
    assert offenders == []


def test_git_remote_commands_are_confined_to_git_content_plane() -> None:
    offenders: list[str] = []
    for path in sorted(RUNTIME.glob("*.py")):
        if path.name == "git_content_plane.py":
            continue
        text = path.read_text(encoding="utf-8")
        if '["git"' in text or "git fetch" in text or "git push" in text or "ls-remote" in text:
            offenders.append(path.name)
    assert offenders == []


def test_scenario_materializers_do_not_sleep_or_open_networks_directly() -> None:
    offenders: list[str] = []
    scenario_files = sorted(RUNTIME.glob("f*.py"))
    for path in scenario_files:
        imports = _imports(path)
        text = path.read_text(encoding="utf-8")
        forbidden_import = any(
            name == "urllib"
            or name.startswith("urllib.")
            or name == "requests"
            or name.startswith("requests.")
            for name in imports
        )
        if forbidden_import or "time.sleep(" in text or "self._sleep(" in text:
            offenders.append(path.name)
    assert offenders == []


def test_package_policy_is_never_weaker_than_github_best_practice_floors() -> None:
    config = json.loads((ROOT / "assets" / "controller.json").read_text(encoding="utf-8"))
    api_policy = config["api_policy"]
    git_policy = config["git_policy"]

    # GitHub documents >=1 second between mutative REST requests.
    assert float(api_policy["mutation_interval_seconds"]) >= 1.0
    # ACMM additionally spaces all trusted REST requests conservatively.
    assert float(api_policy["request_interval_seconds"]) >= 0.0
    # GitHub repository guidance: <=6 pushes/minute/repository.
    assert float(git_policy["push_interval_seconds"]) >= 10.0
    # GitHub repository guidance: <=15 Git read operations/second/repository.
    assert float(git_policy["remote_read_interval_seconds"]) >= (1.0 / 15.0)
