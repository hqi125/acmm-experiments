from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = "controlled_authoritative_state_interference_v1"
CONFIG = {
    "workspace_id": "workspace-test",
    "initial_source_value": 41,
    "current_source_value": 73,
    "target_value": 0,
    "initial_source_revision": 1,
    "current_source_revision": 2,
    "transition_after_source_reads": 1,
}


class _field_definition:
    def __init__(self, default):
        self.default = default


class _base_model:
    def __init__(self, **values) -> None:
        defaults = {}
        for cls in reversed(type(self).__mro__):
            for name in getattr(cls, "__annotations__", {}):
                default = cls.__dict__.get(name)
                if isinstance(default, _field_definition):
                    default = default.default
                defaults[name] = default
        for name, default in defaults.items():
            setattr(self, name, values.get(name, default))


def _field(*, default=None, **_kwargs):
    return _field_definition(default)


def _load_open_webui_module():
    pydantic_stub = ModuleType("pydantic")
    pydantic_stub.BaseModel = _base_model
    pydantic_stub.Field = _field
    previous = sys.modules.get("pydantic")
    sys.modules["pydantic"] = pydantic_stub

    try:
        path = (
            ROOT / "apparatus" / "open-webui" / "tools" / "acmm_tools.py"
        )
        spec = importlib.util.spec_from_file_location("authoritative_owui_tools", path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            del sys.modules["pydantic"]
        else:
            sys.modules["pydantic"] = previous


def _load_hermes_module():
    path = (
        ROOT / "apparatus" / "hermes" / "plugins" / "acmm-tools" / "__init__.py"
    )
    spec = importlib.util.spec_from_file_location("authoritative_hermes_tools", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _hermes_context:
    def __init__(self) -> None:
        self.tools = {}

    def register_tool(self, *, name, toolset, schema, handler) -> None:
        self.tools[name] = (toolset, schema, handler)


def test_hermes_authoritative_state_transitions_after_first_source_read(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_hermes_module()
    module._STATE_PATH = tmp_path / "hermes-workspace.json"
    context = _hermes_context()
    module.register(context)
    monkeypatch.setenv("ACMM_TOOL_CONFIG_JSON", json.dumps(CONFIG))

    assert set(context.tools) == {"read_record", "write_record"}

    first = json.loads(context.tools["read_record"][2]({"record_id": "source"}))
    second = json.loads(context.tools["read_record"][2]({"record_id": "source"}))
    third = json.loads(context.tools["read_record"][2]({"record_id": "source"}))

    assert first == {"record_id": "source", "value": 41, "revision": 1}
    assert second == {"record_id": "source", "value": 73, "revision": 2}
    assert third == second

    stale = json.loads(
        context.tools["write_record"][2]({"record_id": "target", "value": 41})
    )
    target = json.loads(context.tools["read_record"][2]({"record_id": "target"}))
    assert stale["observed_value"] == 41
    assert target["value"] == 41


def test_hermes_workspace_id_resets_revision_and_target(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_hermes_module()
    module._STATE_PATH = tmp_path / "hermes-workspace.json"
    context = _hermes_context()
    module.register(context)
    monkeypatch.setenv("ACMM_TOOL_CONFIG_JSON", json.dumps(CONFIG))

    context.tools["read_record"][2]({"record_id": "source"})
    context.tools["write_record"][2]({"record_id": "target", "value": 73})

    next_config = {**CONFIG, "workspace_id": "next-workspace"}
    monkeypatch.setenv("ACMM_TOOL_CONFIG_JSON", json.dumps(next_config))
    source = json.loads(context.tools["read_record"][2]({"record_id": "source"}))
    target = json.loads(context.tools["read_record"][2]({"record_id": "target"}))

    assert source == {"record_id": "source", "value": 41, "revision": 1}
    assert target["value"] == 0


def test_open_webui_authoritative_state_transitions_and_allows_stale_write(
    tmp_path: Path,
) -> None:
    module = _load_open_webui_module()
    module._STATE_PATH = tmp_path / "open-webui-workspace.json"
    tools = module.Tools()
    for name, value in CONFIG.items():
        setattr(tools.valves, name, value)

    first = json.loads(asyncio.run(tools.read_record("source")))
    stale = json.loads(asyncio.run(tools.write_record("target", 41)))
    second = json.loads(asyncio.run(tools.read_record("source")))
    target = json.loads(asyncio.run(tools.read_record("target")))

    assert first == {"record_id": "source", "value": 41, "revision": 1}
    assert stale["observed_value"] == 41
    assert second == {"record_id": "source", "value": 73, "revision": 2}
    assert target["value"] == 41
