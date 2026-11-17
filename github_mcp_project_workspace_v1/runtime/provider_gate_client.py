from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid


@dataclass(frozen=True)
class github_provider_gate_admission:
    request_id: str
    action_id: str
    decision_id: str
    admission: Mapping[str, Any]


@dataclass(frozen=True)
class github_provider_gate_feedback:
    retry: bool
    recovery: Mapping[str, Any]
    result: Mapping[str, Any]


class github_provider_gate_error(RuntimeError):
    pass


class github_provider_gate_client:
    """Loopback client for Core's active Provider Pressure gate.

    The control file is authoritative about whether an ACMM logical run currently
    owns the provider gate.  When inactive or absent, trusted controller traffic
    falls back to its conservative local governor.  When active, failures are
    fail-closed so no request leaks around PPH/APP.
    """

    def __init__(self, control_path: Path) -> None:
        self._control_path = Path(control_path)

    @property
    def control_path(self) -> Path:
        return self._control_path

    def active(self) -> bool:
        control = self._load_control()
        return bool(control and control.get("active"))

    def admit(
        self,
        *,
        method: str,
        url: str,
        request_kind: str,
        metadata: Mapping[str, Any],
    ) -> github_provider_gate_admission | None:
        control = self._load_control()
        if not control or not bool(control.get("active")):
            return None
        request_id = uuid.uuid4().hex
        payload = {
            "request_id": request_id,
            "plane": "trusted_controller",
            "method": str(method).upper(),
            "url": str(url),
            "request_kind": str(request_kind),
            "metadata": dict(metadata),
        }
        value = self._post(control, "/v1/admit", payload)
        action_id = str(value.get("action_id") or "").strip()
        decision_id = str(value.get("decision_id") or "").strip()
        if not action_id or not decision_id:
            raise github_provider_gate_error(
                "Core Provider Pressure admission response is incomplete."
            )
        admission = value.get("admission")
        return github_provider_gate_admission(
            request_id=request_id,
            action_id=action_id,
            decision_id=decision_id,
            admission=dict(admission) if isinstance(admission, Mapping) else {},
        )

    def feedback(
        self,
        admission: github_provider_gate_admission,
        *,
        status: int | None,
        headers: Mapping[str, str],
        body: str,
        attempt: int,
        error: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> github_provider_gate_feedback:
        control = self._require_active_control()
        selected_headers = {
            str(key): str(value)
            for key, value in headers.items()
            if str(key).casefold()
            in {
                "retry-after",
                "x-ratelimit-remaining",
                "x-ratelimit-reset",
                "x-ratelimit-resource",
            }
        }
        payload = {
            "request_id": admission.request_id,
            "status": status,
            "headers": selected_headers,
            "body": str(body),
            "error": error,
            "metadata": {
                "attempt": int(attempt),
                **dict(metadata or {}),
            },
        }
        value = self._post(control, "/v1/feedback", payload)
        recovery = value.get("recovery")
        result = value.get("result")
        return github_provider_gate_feedback(
            retry=bool(value.get("retry", False)),
            recovery=dict(recovery) if isinstance(recovery, Mapping) else {},
            result=dict(result) if isinstance(result, Mapping) else {},
        )

    def cancel(
        self,
        admission: github_provider_gate_admission,
        detail: str,
    ) -> None:
        control = self._require_active_control()
        self._post(
            control,
            "/v1/cancel",
            {"request_id": admission.request_id, "detail": str(detail)},
        )

    def _require_active_control(self) -> Mapping[str, Any]:
        control = self._load_control()
        if not control or not bool(control.get("active")):
            raise github_provider_gate_error(
                "Core Provider Pressure gate became inactive during a managed request."
            )
        return control

    def _load_control(self) -> Mapping[str, Any] | None:
        try:
            raw = self._control_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise github_provider_gate_error(
                f"Cannot read Core Provider Pressure gate control: {exc}"
            ) from exc
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise github_provider_gate_error(
                "Core Provider Pressure gate control is malformed."
            ) from exc
        if not isinstance(value, Mapping):
            raise github_provider_gate_error(
                "Core Provider Pressure gate control is malformed."
            )
        if not bool(value.get("active")):
            return dict(value)
        endpoint = str(value.get("local_url") or value.get("url") or "").strip()
        token = str(value.get("token") or "").strip()
        if not endpoint or not token:
            raise github_provider_gate_error(
                "Active Core Provider Pressure gate control is incomplete."
            )
        result = dict(value)
        result["endpoint"] = endpoint.rstrip("/")
        return result

    def _post(
        self,
        control: Mapping[str, Any],
        path: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        endpoint = str(control.get("endpoint") or "").rstrip("/") + path
        token = str(control.get("token") or "")
        request = Request(
            endpoint,
            data=(json.dumps(dict(payload), sort_keys=True) + "\n").encode("utf-8"),
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=None) as response:  # noqa: S310 - loopback control plane
                body = response.read(256 * 1024)
                status = int(response.status)
        except HTTPError as exc:
            detail = exc.read(256 * 1024).decode("utf-8", errors="replace").strip()
            raise github_provider_gate_error(
                f"Core Provider Pressure gate {path} returned HTTP {exc.code}: {detail}"
            ) from exc
        except (OSError, URLError) as exc:
            raise github_provider_gate_error(
                f"Core Provider Pressure gate {path} is unavailable: {exc}"
            ) from exc
        if status != 200:
            raise github_provider_gate_error(
                f"Core Provider Pressure gate {path} returned HTTP {status}."
            )
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise github_provider_gate_error(
                f"Core Provider Pressure gate {path} returned invalid JSON."
            ) from exc
        if not isinstance(value, Mapping):
            raise github_provider_gate_error(
                f"Core Provider Pressure gate {path} returned invalid JSON."
            )
        return dict(value)


__all__ = [
    "github_provider_gate_admission",
    "github_provider_gate_client",
    "github_provider_gate_error",
    "github_provider_gate_feedback",
]
