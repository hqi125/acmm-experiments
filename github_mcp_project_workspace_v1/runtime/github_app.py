from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Mapping

from .api_governor import github_api_governor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


Transport = Callable[
    [str, str, Mapping[str, str], bytes | None],
    tuple[int, Mapping[str, str], bytes],
]
Signer = Callable[[bytes, str], bytes]


class github_app_error(RuntimeError):
    pass


@dataclass(frozen=True)
class github_app_installation_token:
    token: str = field(repr=False)
    expires_at: str
    repository_id: int
    repository_full_name: str
    permissions: Mapping[str, str]


class github_app_client:
    def __init__(
        self,
        *,
        app_id: int,
        installation_id: int,
        private_key_pem: str,
        api_base: str = "https://api.github.com",
        transport: Transport | None = None,
        signer: Signer | None = None,
        now: Callable[[], datetime] | None = None,
        governor: github_api_governor | None = None,
    ) -> None:
        if app_id <= 0:
            raise ValueError("GitHub App id must be positive.")
        if installation_id <= 0:
            raise ValueError("GitHub App installation id must be positive.")
        if not private_key_pem.strip():
            raise ValueError("GitHub App private key must not be empty.")
        self._app_id = app_id
        self._installation_id = installation_id
        self._private_key_pem = private_key_pem
        self._api_base = api_base.rstrip("/")
        self._transport = transport or _urllib_transport
        self._signer = signer or _openssl_rs256_sign
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._governor = governor

    @property
    def installation_id(self) -> int:
        return self._installation_id

    @property
    def api_base(self) -> str:
        return self._api_base

    def mint_repository_token(
        self,
        *,
        repository_id: int,
        expected_repository_full_name: str,
    ) -> github_app_installation_token:
        if repository_id <= 0:
            raise ValueError("GitHub repository id must be positive.")
        if not expected_repository_full_name.strip():
            raise ValueError("Expected repository full name must not be empty.")

        payload = {
            "repository_ids": [repository_id],
            "permissions": {
                "actions": "read",
                "contents": "write",
                "issues": "write",
                "metadata": "read",
                "pull_requests": "write",
            },
        }
        status, _headers, body = self._request(
            "POST",
            f"/app/installations/{self._installation_id}/access_tokens",
            authorization=self._app_jwt(),
            payload=payload,
            route="app.installation_token.mint",
            primary_domain="app",
        )
        if status != 201:
            raise github_app_error(
                "GitHub App installation-token mint returned HTTP "
                f"{status}: {_safe_detail(body)}"
            )
        value = _json_object(body, "GitHub App installation-token response")
        token = value.get("token")
        expires_at = value.get("expires_at")
        repositories = value.get("repositories")
        permissions = value.get("permissions")
        if not isinstance(token, str) or not token.strip():
            raise github_app_error("GitHub App installation-token response has no token.")
        if not isinstance(expires_at, str) or not expires_at.strip():
            raise github_app_error(
                "GitHub App installation-token response has no expiry timestamp."
            )
        if not isinstance(repositories, list) or len(repositories) != 1:
            raise github_app_error(
                "GitHub App installation token must expose exactly one repository."
            )
        repository = repositories[0]
        if not isinstance(repository, Mapping):
            raise github_app_error(
                "GitHub App installation-token repository metadata is invalid."
            )
        observed_id = repository.get("id")
        observed_full_name = repository.get("full_name")
        if observed_id != repository_id:
            raise github_app_error(
                "GitHub App installation token resolved unexpected repository id "
                f"{observed_id!r}; expected {repository_id}."
            )
        if (
            not isinstance(observed_full_name, str)
            or observed_full_name.casefold()
            != expected_repository_full_name.casefold()
        ):
            raise github_app_error(
                "GitHub App installation token resolved unexpected repository "
                f"{observed_full_name!r}; expected {expected_repository_full_name!r}."
            )
        if not isinstance(permissions, Mapping):
            raise github_app_error(
                "GitHub App installation-token permissions are missing."
            )
        expected_permissions = payload["permissions"]
        observed_permissions = {
            key: permissions.get(key)
            for key in expected_permissions
        }
        if observed_permissions != expected_permissions:
            raise github_app_error(
                "GitHub App installation-token permissions do not match the "
                "qualified Experiment 2 envelope."
            )
        if permissions.get("workflows") not in {None, "none"}:
            raise github_app_error(
                "GitHub App installation token unexpectedly exposes workflows permission."
            )

        return github_app_installation_token(
            token=token.strip(),
            expires_at=expires_at.strip(),
            repository_id=repository_id,
            repository_full_name=expected_repository_full_name,
            permissions=dict(expected_permissions),
        )

    def revoke(self, token: str) -> None:
        if not token.strip():
            raise ValueError("GitHub App installation token must not be empty.")
        status, _headers, body = self._request(
            "DELETE",
            "/installation/token",
            authorization=token.strip(),
            payload=None,
            route="app.installation_token.revoke",
            primary_domain="installation",
            enforce_primary_headroom=False,
        )
        if status != 204:
            raise github_app_error(
                "GitHub App installation-token revocation returned HTTP "
                f"{status}: {_safe_detail(body)}"
            )

    def _app_jwt(self) -> str:
        now = self._now().astimezone(timezone.utc)
        issued_at = int((now - timedelta(seconds=60)).timestamp())
        expires_at = int((now + timedelta(minutes=9)).timestamp())
        header = _base64url_json({"alg": "RS256", "typ": "JWT"})
        payload = _base64url_json(
            {
                "iat": issued_at,
                "exp": expires_at,
                "iss": str(self._app_id),
            }
        )
        signing_input = f"{header}.{payload}".encode("ascii")
        signature = self._signer(signing_input, self._private_key_pem)
        return f"{header}.{payload}.{_base64url(signature)}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        authorization: str,
        payload: Mapping[str, Any] | None,
        route: str,
        primary_domain: str,
        enforce_primary_headroom: bool = True,
    ) -> tuple[int, Mapping[str, str], bytes]:
        data = None
        if payload is not None:
            data = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {authorization}",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "acmm-github-app-runtime",
        }
        secondary_attempt = 0
        while True:
            try:
                if self._governor is not None:
                    with self._governor.serialized_provider_access():
                        self._governor.before_request(
                            method=method,
                            route=route,
                            url=self._api_base + path,
                            content_generating=False,
                            primary_domain=primary_domain,
                            enforce_primary_headroom=enforce_primary_headroom,
                            recovery_retry=secondary_attempt > 0,
                        )
                        try:
                            status, response_headers, body = self._transport(
                                method,
                                self._api_base + path,
                                headers,
                                data,
                            )
                        except BaseException as exc:
                            self._governor.provider_request_error(
                                f"{exc.__class__.__name__}: {exc}"
                            )
                            raise
                        self._governor.observe_response(
                            route=route,
                            status=status,
                            headers=response_headers,
                            content_generating=False,
                            primary_domain=primary_domain,
                        )
                        recovery = self._governor.rate_limit_recovery(
                            status=status,
                            headers=response_headers,
                            detail=_safe_detail(body),
                            primary_domain=primary_domain,
                            route=route,
                            attempt=secondary_attempt,
                        )
                else:
                    status, response_headers, body = self._transport(
                        method,
                        self._api_base + path,
                        headers,
                        data,
                    )
                    recovery = None
            except Exception as exc:
                if isinstance(exc, github_app_error):
                    raise
                raise github_app_error(
                    f"GitHub App request {method} {path} failed: {exc}"
                ) from exc

            if recovery is not None:
                if secondary_attempt < self._governor.policy.max_secondary_retries:
                    self._governor.actuate_provider_recovery(
                        recovery,
                        attempt=secondary_attempt + 1,
                    )
                    secondary_attempt += 1
                    continue
                raise github_app_error(
                    "GitHub App rate-limit recovery exhausted after "
                    f"{secondary_attempt} retries during {method} {path}: "
                    f"{_safe_detail(body)}"
                )
            return status, response_headers, body


def _base64url_json(value: Mapping[str, Any]) -> str:
    return _base64url(
        json.dumps(dict(value), separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _openssl_rs256_sign(message: bytes, private_key_pem: str) -> bytes:
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="acmm-github-app-",
            suffix=".pem",
            delete=False,
        ) as handle:
            path = Path(handle.name)
            os.chmod(path, 0o600)
            handle.write(private_key_pem.encode("utf-8"))
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(path)],
            input=message,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise github_app_error(
                "OpenSSL could not sign the GitHub App JWT"
                + (f": {detail}" if detail else ".")
            )
        if not result.stdout:
            raise github_app_error("OpenSSL returned an empty GitHub App JWT signature.")
        return result.stdout
    except FileNotFoundError as exc:
        raise github_app_error(
            "OpenSSL is required to sign GitHub App JWTs but was not found."
        ) from exc
    finally:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def _urllib_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    payload: bytes | None,
) -> tuple[int, Mapping[str, str], bytes]:
    request = Request(url, data=payload, method=method, headers=dict(headers))
    try:
        with urlopen(request, timeout=30.0) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()
    except URLError as exc:
        raise github_app_error(f"GitHub App transport failed: {exc.reason}") from exc


def _json_object(body: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise github_app_error(f"{label} is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise github_app_error(f"{label} must be a JSON object.")
    return value


def _safe_detail(body: bytes) -> str:
    if not body:
        return "empty response"
    return body.decode("utf-8", errors="replace")[:1000]
