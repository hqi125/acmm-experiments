from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from acmm.experiment_package import install_experiment_package, load_staged_experiment_runtime
from acmm.secret_bindings import (
    bind_secret_file,
    experiment_secret_binding_key,
    initialize_secret_store,
    secret_binding_key,
)


ROOT = Path(__file__).resolve().parents[2] / "github_mcp_project_workspace_v1"
EXPERIMENT_ID = "github_mcp_project_workspace_v1"


def _write_secret(path: Path, value: str) -> Path:
    path.write_text(value + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _load_types(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "source"
    shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"))
    bindings = tmp_path / "secret-bindings.yaml"
    monkeypatch.setenv("ACMM_SECRET_BINDINGS_FILE", str(bindings))
    monkeypatch.setenv("ACMM_SECRET_DIRECTORY", str(tmp_path / "secrets"))
    monkeypatch.setenv("ACMM_GITHUB_PROVIDER_STATE_ROOT", str(tmp_path / "provider-state"))
    initialize_secret_store()
    bind_secret_file(
        experiment_secret_binding_key(EXPERIMENT_ID, "controller_access_token"),
        _write_secret(tmp_path / "controller-token", "controller-secret-value"),
    )
    bind_secret_file(
        secret_binding_key(EXPERIMENT_ID, "github_mcp", "access_token"),
        _write_secret(tmp_path / "subject-token", "subject-secret-value"),
    )
    package = install_experiment_package(source, tmp_path / "runtime-root")
    loaded = load_staged_experiment_runtime(package)
    diagnostic = loaded.runtime.diagnostics["github_fixture_controller"]
    controller_module = sys.modules[type(diagnostic._client).__module__]
    git_module = sys.modules[controller_module.github_git_content_plane.__module__]
    return (
        git_module.github_git_content_plane,
        git_module.github_git_error,
        controller_module.github_controller_client,
    )


def _bare_repository(path: Path) -> Path:
    subprocess.run(
        ["git", "init", "--bare", str(path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return path


def test_git_content_plane_writes_updates_and_fingerprints_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_git_content_plane, github_git_error, _ = _load_types(tmp_path, monkeypatch)
    remote = _bare_repository(tmp_path / "remote.git")
    plane = github_git_content_plane(
        "fixture-token",
        remote_url_factory=lambda _owner, _name: str(remote),
        root=tmp_path / "git-work",
        authentication=False,
    )

    first = plane.write_file(
        "octo",
        "demo",
        "README.md",
        message="initial fixture",
        content="first\n",
    )
    assert first.branch == "main"
    assert first.changed is True

    second = plane.write_file(
        "octo",
        "demo",
        "README.md",
        message="update fixture",
        content="second\n",
        branch="main",
        sha=first.blob_sha,
    )
    assert second.changed is True
    assert second.commit_sha != first.commit_sha

    with pytest.raises(github_git_error, match="precondition failed"):
        plane.write_file(
            "octo",
            "demo",
            "README.md",
            message="stale write",
            content="third\n",
            branch="main",
            sha="0" * 40,
        )

    rendered = subprocess.run(
        ["git", f"--git-dir={remote}", "show", "refs/heads/main:README.md"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout
    assert rendered == "second\n"

    fingerprint = plane.ref_fingerprint("octo", "demo")
    assert fingerprint["refs"] == {"refs/heads/main": second.commit_sha}
    assert len(fingerprint["sha256"]) == 64
    metrics = plane.usage_snapshot()["metrics"]
    assert metrics["file_writes"] == 2
    assert metrics["pushes"] == 2
    assert metrics["ref_fingerprints"] == 1


def test_controller_uses_git_content_plane_for_production_file_write_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_git_content_plane, _github_git_error, github_controller_client = _load_types(
        tmp_path, monkeypatch
    )
    remote = _bare_repository(tmp_path / "controller-remote.git")
    plane = github_git_content_plane(
        "fixture-token",
        remote_url_factory=lambda _owner, _name: str(remote),
        root=tmp_path / "controller-git-work",
        authentication=False,
    )
    client = github_controller_client(
        "fixture-token",
        git_content_plane=plane,
    )

    result = client.create_or_update_file(
        "octo",
        "demo",
        "docs/policy.md",
        message="seed policy",
        content="# Policy\n",
    )

    assert result["content"]["path"] == "docs/policy.md"
    assert len(result["content"]["sha"]) == 40
    assert len(result["commit"]["sha"]) == 40
    assert client.read_text_file(
        "octo", "demo", "docs/policy.md", ref=result["commit"]["sha"]
    ) == "# Policy\n"
    info = client.contents_optional(
        "octo", "demo", "docs/policy.md", ref="main"
    )
    assert info is not None
    assert info["sha"] == result["content"]["sha"]
    assert client.repository_ref_fingerprint("octo", "demo")["refs"] == {
        "refs/heads/main": result["commit"]["sha"]
    }
