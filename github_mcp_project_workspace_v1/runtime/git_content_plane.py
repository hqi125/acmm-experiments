from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
import time
from typing import Any, Callable, Mapping


class github_git_error(RuntimeError):
    pass


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class github_git_write_result:
    path: str
    blob_sha: str
    commit_sha: str
    branch: str
    changed: bool


class github_git_content_plane:
    def __init__(
        self,
        token: str,
        *,
        default_branch: str = "main",
        remote_url_factory: Callable[[str, str], str] | None = None,
        runner: Runner | None = None,
        root: Path | None = None,
        authentication: bool = True,
    ) -> None:
        if not token.strip():
            raise ValueError("GitHub Git token must not be empty.")
        self._token = token.strip()
        self._default_branch = default_branch
        self._remote_url_factory = remote_url_factory or (
            lambda owner, name: f"https://github.com/{owner}/{name}.git"
        )
        self._runner = runner or subprocess.run
        self._root = root or Path(tempfile.mkdtemp(prefix="acmm-github-git-"))
        self._root.mkdir(parents=True, exist_ok=True)
        self._authentication = authentication
        self._workspaces: dict[str, Path] = {}
        self._last_fetch_monotonic: dict[str, float] = {}
        self._metrics: dict[str, int] = {
            "git_commands": 0,
            "fetches": 0,
            "pushes": 0,
            "commits": 0,
            "file_writes": 0,
            "file_reads": 0,
            "ref_fingerprints": 0,
        }

    def usage_snapshot(self) -> Mapping[str, Any]:
        return {"schema_version": "0.1", "metrics": dict(self._metrics)}

    def discard_repository(self, owner: str, name: str) -> None:
        key = self._key(owner, name)
        workspace = self._workspaces.pop(key, None)
        self._last_fetch_monotonic.pop(key, None)
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)

    def close(self) -> None:
        shutil.rmtree(self._root, ignore_errors=True)
        self._workspaces.clear()

    def write_file(
        self,
        owner: str,
        name: str,
        path: str,
        *,
        message: str,
        content: str,
        branch: str | None = None,
        sha: str | None = None,
    ) -> github_git_write_result:
        target_branch = branch or self._default_branch
        workspace = self._workspace(owner, name)
        self._synchronize(workspace, target_branch)
        relative = self._safe_relative_path(path)

        if sha is not None:
            actual_sha = self._blob_sha_optional(workspace, target_branch, relative)
            if actual_sha != sha:
                raise github_git_error(
                    f"Git write precondition failed for {owner}/{name}:{path}@{target_branch}; "
                    f"expected blob {sha}, observed {actual_sha or '<missing>'}."
                )

        destination = workspace / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="")
        self._git(workspace, "add", "--", relative.as_posix())

        status = self._git(workspace, "status", "--porcelain", "--", relative.as_posix()).stdout.strip()
        if status:
            self._git(workspace, "commit", "-m", message)
            self._metrics["commits"] += 1
            self._metrics["file_writes"] += 1
            commit_sha = self._git(workspace, "rev-parse", "HEAD").stdout.strip()
            blob_sha = self._git(workspace, "rev-parse", f"HEAD:{relative.as_posix()}").stdout.strip()
            self._git(
                workspace,
                "push",
                "origin",
                f"HEAD:refs/heads/{target_branch}",
            )
            self._metrics["pushes"] += 1
            self._last_fetch_monotonic[self._key(owner, name)] = time.monotonic()
            return github_git_write_result(
                path=relative.as_posix(),
                blob_sha=blob_sha,
                commit_sha=commit_sha,
                branch=target_branch,
                changed=True,
            )

        commit_sha = self._git(workspace, "rev-parse", "HEAD").stdout.strip()
        blob_sha = self._git(workspace, "rev-parse", f"HEAD:{relative.as_posix()}").stdout.strip()
        return github_git_write_result(
            path=relative.as_posix(),
            blob_sha=blob_sha,
            commit_sha=commit_sha,
            branch=target_branch,
            changed=False,
        )

    def file_info(
        self,
        owner: str,
        name: str,
        path: str,
        *,
        ref: str,
    ) -> Mapping[str, Any] | None:
        workspace = self._workspace(owner, name)
        relative = self._safe_relative_path(path)
        resolved = self._resolve_read_ref(owner, name, workspace, ref)
        exists = self._git(
            workspace,
            "cat-file",
            "-e",
            f"{resolved}:{relative.as_posix()}",
            check=False,
        )
        if exists.returncode != 0:
            return None
        content = self._git(
            workspace,
            "show",
            f"{resolved}:{relative.as_posix()}",
        ).stdout
        blob_sha = self._git(
            workspace,
            "rev-parse",
            f"{resolved}:{relative.as_posix()}",
        ).stdout.strip()
        self._metrics["file_reads"] += 1
        return {
            "type": "file",
            "path": relative.as_posix(),
            "sha": blob_sha,
            "encoding": "base64",
            "content": __import__("base64").b64encode(content.encode("utf-8")).decode("ascii"),
        }

    def read_text_file(
        self,
        owner: str,
        name: str,
        path: str,
        *,
        ref: str,
    ) -> str:
        value = self.file_info(owner, name, path, ref=ref)
        if value is None:
            raise github_git_error(
                f"Repository content '{path}' does not exist at ref '{ref}'."
            )
        import base64
        return base64.b64decode(str(value["content"]).encode("ascii")).decode("utf-8")

    def ref_fingerprint(self, owner: str, name: str) -> Mapping[str, Any]:
        remote = self._remote_url_factory(owner, name)
        result = self._git_remote(owner, name, "ls-remote", "--heads", "--tags", remote)
        refs: dict[str, str] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                raise github_git_error(
                    f"Unexpected git ls-remote output for {owner}/{name}: {line!r}"
                )
            commit_sha, ref_name = parts
            if ref_name.endswith("^{}"):
                continue
            refs[ref_name] = commit_sha
        payload = "\n".join(f"{key}\t{refs[key]}" for key in sorted(refs)) + "\n"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self._metrics["ref_fingerprints"] += 1
        return {
            "schema_version": "0.1",
            "sha256": digest,
            "refs": refs,
        }

    def _workspace(self, owner: str, name: str) -> Path:
        key = self._key(owner, name)
        existing = self._workspaces.get(key)
        if existing is not None:
            return existing
        workspace = self._root / hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        workspace.mkdir(parents=True, exist_ok=True)
        self._git(workspace, "init", "-b", self._default_branch)
        self._git(workspace, "config", "user.name", "ACMM Fixture Controller")
        self._git(workspace, "config", "user.email", "acmm-fixture-controller@invalid.local")
        self._git(workspace, "remote", "add", "origin", self._remote_url_factory(owner, name))
        self._workspaces[key] = workspace
        return workspace

    def _synchronize(self, workspace: Path, branch: str) -> None:
        self._fetch(workspace, force=True)

        remote_ref = f"refs/remotes/origin/{branch}"
        local_ref = f"refs/heads/{branch}"
        if self._git(workspace, "show-ref", "--verify", "--quiet", remote_ref, check=False).returncode == 0:
            self._git(workspace, "checkout", "-B", branch, f"origin/{branch}")
            return
        if self._git(workspace, "show-ref", "--verify", "--quiet", local_ref, check=False).returncode == 0:
            self._git(workspace, "checkout", branch)
            return
        has_head = self._git(workspace, "rev-parse", "--verify", "HEAD", check=False).returncode == 0
        if not has_head and branch == self._default_branch:
            self._git(workspace, "checkout", "-B", branch)
            return
        raise github_git_error(
            f"Git branch '{branch}' does not exist for controller write. Create the branch before writing files."
        )

    def _resolve_read_ref(
        self,
        owner: str,
        name: str,
        workspace: Path,
        ref: str,
    ) -> str:
        del owner, name
        if len(ref) == 40 and all(character in "0123456789abcdefABCDEF" for character in ref):
            exists = self._git(workspace, "cat-file", "-e", f"{ref}^{{commit}}", check=False)
            if exists.returncode != 0:
                self._fetch(workspace, force=True)
            return ref
        self._fetch(workspace, force=False)
        remote_ref = f"refs/remotes/origin/{ref}"
        if self._git(workspace, "show-ref", "--verify", "--quiet", remote_ref, check=False).returncode == 0:
            return f"origin/{ref}"
        local_ref = f"refs/heads/{ref}"
        if self._git(workspace, "show-ref", "--verify", "--quiet", local_ref, check=False).returncode == 0:
            return ref
        tag_ref = f"refs/tags/{ref}"
        if self._git(workspace, "show-ref", "--verify", "--quiet", tag_ref, check=False).returncode == 0:
            return tag_ref
        raise github_git_error(f"Git ref '{ref}' does not exist for controller read.")

    def _fetch(self, workspace: Path, *, force: bool) -> None:
        key = next((key for key, value in self._workspaces.items() if value == workspace), str(workspace))
        now = time.monotonic()
        last = self._last_fetch_monotonic.get(key, 0.0)
        if not force and now - last < 0.25:
            return
        fetch = self._git(workspace, "fetch", "--prune", "origin", check=False)
        self._metrics["fetches"] += 1
        if fetch.returncode != 0:
            lowered = (fetch.stderr or "").casefold()
            empty_remote = (
                "couldn't find remote ref" in lowered
                or "does not appear to be a git repository" in lowered
            )
            if not empty_remote:
                raise github_git_error(self._command_error("git fetch", fetch))
        self._last_fetch_monotonic[key] = now

    def _blob_sha_optional(self, workspace: Path, branch: str, path: PurePosixPath) -> str | None:
        del branch
        value = self._git(workspace, "rev-parse", f"HEAD:{path.as_posix()}", check=False)
        if value.returncode != 0:
            return None
        return value.stdout.strip()

    def _git(self, workspace: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self._execute(["git", *args], cwd=workspace, check=check)

    def _git_remote(self, owner: str, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        del owner, name
        return self._execute(["git", *args], cwd=self._root, check=True)

    def _execute(
        self,
        command: list[str],
        *,
        cwd: Path,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        self._metrics["git_commands"] += 1
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        askpass_path: Path | None = None
        if self._authentication:
            askpass_path = self._root / "askpass.sh"
            if not askpass_path.exists():
                askpass_path.write_text(
                    "#!/bin/sh\n"
                    "case \"$1\" in\n"
                    "  *Username*) printf '%s\\n' \"$ACMM_GIT_USERNAME\" ;;\n"
                    "  *) printf '%s\\n' \"$ACMM_GIT_TOKEN\" ;;\n"
                    "esac\n",
                    encoding="utf-8",
                    newline="\n",
                )
                askpass_path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            env["GIT_ASKPASS"] = str(askpass_path)
            env["ACMM_GIT_USERNAME"] = "x-access-token"
            env["ACMM_GIT_TOKEN"] = self._token
        result = self._runner(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and result.returncode != 0:
            raise github_git_error(self._command_error(" ".join(command[:2]), result))
        return result

    @staticmethod
    def _command_error(label: str, result: subprocess.CompletedProcess[str]) -> str:
        detail = (result.stderr or result.stdout or "unknown git failure").strip()
        return f"{label} failed with exit code {result.returncode}: {detail}"

    @staticmethod
    def _safe_relative_path(path: str) -> PurePosixPath:
        value = PurePosixPath(path)
        if not path or value.is_absolute() or ".." in value.parts:
            raise github_git_error(f"Unsafe repository path for Git content write: {path!r}")
        return value

    @staticmethod
    def _key(owner: str, name: str) -> str:
        return f"{owner.casefold()}/{name.casefold()}"
