from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "apparatus" / "agent-zero" / "plugins" / "acmm_tools" / "tools"
CONFIG = {
    "workspace_id": "workspace-test",
    "initial_source_value": 41,
    "current_source_value": 73,
    "target_value": 0,
    "initial_source_revision": 1,
    "current_source_revision": 2,
    "transition_after_source_reads": 1,
}


class _response:
    def __init__(self, *, message, break_loop):
        self.message = message
        self.break_loop = break_loop


class _tool:
    def __init__(self) -> None:
        self.args = {}
        self.agent = object()


class _plugins_module(ModuleType):
    def get_plugin_config(self, name, *, agent):
        del name, agent
        return dict(CONFIG)


def _load_tool(filename: str):
    helpers = ModuleType("helpers")
    plugins = _plugins_module("helpers.plugins")
    tool_module = ModuleType("helpers.tool")
    tool_module.Response = _response
    tool_module.Tool = _tool
    helpers.plugins = plugins

    previous = {
        name: sys.modules.get(name)
        for name in ("helpers", "helpers.plugins", "helpers.tool")
    }
    sys.modules["helpers"] = helpers
    sys.modules["helpers.plugins"] = plugins
    sys.modules["helpers.tool"] = tool_module

    try:
        path = TOOLS_ROOT / filename
        spec = importlib.util.spec_from_file_location(
            f"authoritative_{filename}",
            path,
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, value in previous.items():
            if value is None:
                del sys.modules[name]
            else:
                sys.modules[name] = value


def test_agent_zero_authoritative_state_tools_share_transition_state(
    tmp_path: Path,
) -> None:
    read_module = _load_tool("read_record.py")
    write_module = _load_tool("write_record.py")
    state_path = tmp_path / "agent-zero-workspace.json"
    read_module._STATE_PATH = state_path
    write_module._STATE_PATH = state_path

    read_source = read_module.ReadRecord()
    read_source.args = {"record_id": "source"}
    read_target = read_module.ReadRecord()
    read_target.args = {"record_id": "target"}
    write_target = write_module.WriteRecord()
    write_target.args = {"record_id": "target", "value": 41}

    first = json.loads(asyncio.run(read_source.execute()).message)
    stale = json.loads(asyncio.run(write_target.execute()).message)
    second = json.loads(asyncio.run(read_source.execute()).message)
    target = json.loads(asyncio.run(read_target.execute()).message)

    assert first["value"] == 41
    assert first["revision"] == 1
    assert stale["observed_value"] == 41
    assert second["value"] == 73
    assert second["revision"] == 2
    assert target["value"] == 41
