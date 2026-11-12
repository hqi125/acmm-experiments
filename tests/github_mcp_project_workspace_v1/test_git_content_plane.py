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
        experiment_secret_binding_key(EXPERIMENT_ID, "github_app_private_key"),
        _write_secret(tmp_path / "github-app-private-key", "test-private-key-pem"),
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




class _fake_clock:
    def __init__(self) -> None:
        self.value = 1000.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


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
    clock = _fake_clock()
    plane = github_git_content_plane(
        "fixture-token",
        remote_url_factory=lambda _owner, _name: str(remote),
        root=tmp_path / "git-work",
        authentication=False,
        sleep=clock.sleep,
        monotonic=clock.now,
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
    clock = _fake_clock()
    plane = github_git_content_plane(
        "fixture-token",
        remote_url_factory=lambda _owner, _name: str(remote),
        root=tmp_path / "controller-git-work",
        authentication=False,
        sleep=clock.sleep,
        monotonic=clock.now,
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


def test_git_content_plane_batches_multiple_local_commits_into_one_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_git_content_plane, _github_git_error, _ = _load_types(tmp_path, monkeypatch)
    remote = _bare_repository(tmp_path / "batch-remote.git")
    clock = _fake_clock()
    plane = github_git_content_plane(
        "fixture-token",
        remote_url_factory=lambda _owner, _name: str(remote),
        root=tmp_path / "batch-git-work",
        authentication=False,
        sleep=clock.sleep,
        monotonic=clock.now,
    )

    with plane.publish_batch("octo", "demo"):
        first = plane.write_file(
            "octo", "demo", "a.txt", message="add a", content="a\n"
        )
        second = plane.write_file(
            "octo", "demo", "b.txt", message="add b", content="b\n", branch="main"
        )

    assert first.commit_sha != second.commit_sha
    metrics = plane.usage_snapshot()["metrics"]
    assert metrics["commits"] == 2
    assert metrics["pushes"] == 1
    assert metrics["published_branches"] == 1
    rendered = subprocess.run(
        ["git", f"--git-dir={remote}", "show", "refs/heads/main:b.txt"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout
    assert rendered == "b\n"


def test_git_content_plane_applies_provider_gate_and_remote_pacing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_git_content_plane, _github_git_error, _ = _load_types(tmp_path, monkeypatch)
    remote = _bare_repository(tmp_path / "paced-remote.git")
    clock = _fake_clock()
    from contextlib import contextmanager

    gates: list[bool] = []

    @contextmanager
    def provider_context(content_generating: bool):
        gates.append(content_generating)
        yield

    plane = github_git_content_plane(
        "fixture-token",
        remote_url_factory=lambda _owner, _name: str(remote),
        root=tmp_path / "paced-git-work",
        authentication=False,
        sleep=clock.sleep,
        monotonic=clock.now,
        provider_context=provider_context,
    )

    plane.write_file(
        "octo", "demo", "README.md", message="seed", content="seed\n"
    )
    plane.ref_fingerprint("octo", "demo")

    assert True in gates  # push/content-generating remote operation
    assert False in gates  # fetch/ls-remote remote read
    metrics = plane.usage_snapshot()["metrics"]
    assert metrics["pushes"] == 1
    assert metrics["ref_fingerprints"] == 1


def test_git_content_plane_rejects_weaker_than_github_repository_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_git_content_plane, _github_git_error, _ = _load_types(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="at least 10 seconds"):
        github_git_content_plane(
            "fixture-token",
            push_interval_seconds=9.99,
            root=tmp_path / "bad-push",
        )
    with pytest.raises(ValueError, match="at least 1/15 second"):
        github_git_content_plane(
            "fixture-token",
            remote_read_interval_seconds=0.01,
            root=tmp_path / "bad-read",
        )


def test_git_content_plane_reuses_fresh_fetch_until_rest_side_ref_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_git_content_plane, _github_git_error, _ = _load_types(tmp_path, monkeypatch)
    remote = _bare_repository(tmp_path / "freshness-remote.git")
    clock = _fake_clock()
    plane = github_git_content_plane(
        "fixture-token",
        remote_url_factory=lambda _owner, _name: str(remote),
        root=tmp_path / "freshness-work",
        authentication=False,
        sleep=clock.sleep,
        monotonic=clock.now,
    )

    plane.write_file(
        "octo", "demo", "seed.txt", message="seed", content="seed\n"
    )
    clock.value += 1.0
    assert plane.file_info("octo", "demo", "seed.txt", ref="main") is not None
    fetches_after_read = plane.usage_snapshot()["metrics"]["fetches"]

    plane.write_file(
        "octo", "demo", "next.txt", message="next", content="next\n", branch="main"
    )
    assert plane.usage_snapshot()["metrics"]["fetches"] == fetches_after_read

    plane.mark_remote_changed("octo", "demo")
    plane.write_file(
        "octo", "demo", "after-rest.txt", message="after rest", content="after\n", branch="main"
    )
    assert plane.usage_snapshot()["metrics"]["fetches"] == fetches_after_read + 1
