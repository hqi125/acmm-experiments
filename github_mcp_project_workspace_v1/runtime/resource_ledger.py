from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping


_LEDGER_NAME = "github_runtime_resources.json"


class github_resource_ledger:
    def __init__(self, session_dir: str | Path) -> None:
        self.path = Path(session_dir) / _LEDGER_NAME

    def record_repository(
        self,
        *,
        run_index: int,
        repository_id: int,
        owner: str,
        name: str,
        full_name: str,
        preparation_mode: str = "scenario_slice",
        preparation_attempt: int = 1,
    ) -> None:
        value = self._load()
        repositories = value["repositories"]
        if any(item.get("repository_id") == repository_id for item in repositories):
            raise RuntimeError(
                f"GitHub runtime resource ledger already contains repository id {repository_id}."
            )
        repositories.append(
            {
                "run_index": run_index,
                "repository_id": repository_id,
                "owner": owner,
                "name": name,
                "full_name": full_name,
                "preparation_mode": preparation_mode,
                "preparation_attempt": preparation_attempt,
                "preparation_state": "preparing",
                "installation_attached": False,
                "token_minted": False,
                "token_fingerprint": None,
                "token_revoked": False,
                "subject_bound": False,
                "subject_unbound": False,
                "installation_detached": False,
                "repository_retired": False,
                "updated_at": _now(),
            }
        )
        self._write(value)

    def update(self, repository_id: int, **changes: Any) -> None:
        value = self._load()
        for item in value["repositories"]:
            if item.get("repository_id") != repository_id:
                continue
            for key, change in changes.items():
                if key not in item:
                    raise ValueError(f"Unknown GitHub runtime resource ledger field '{key}'.")
                item[key] = change
            item["updated_at"] = _now()
            self._write(value)
            return
        raise RuntimeError(
            f"GitHub runtime resource ledger does not contain repository id {repository_id}."
        )

    def repositories(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(dict(item) for item in self._load()["repositories"])

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema_version": "0.1", "repositories": []}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"GitHub runtime resource ledger is unreadable: {self.path}"
            ) from exc
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != "0.1"
            or not isinstance(value.get("repositories"), list)
            or any(not isinstance(item, dict) for item in value["repositories"])
        ):
            raise RuntimeError(
                f"GitHub runtime resource ledger is invalid: {self.path}"
            )
        return value

    def _write(self, value: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        data = (json.dumps(dict(value), indent=2, sort_keys=True) + "\n").encode("utf-8")
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            import os
            os.fsync(handle.fileno())
        temporary.replace(self.path)


def github_runtime_resource_ledger_path(session_dir: str | Path) -> Path:
    return Path(session_dir) / _LEDGER_NAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
