from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Iterable


class GitHubDeployError(RuntimeError):
    pass


@dataclass
class PatchInspection:
    files: list[str]
    total_bytes: int

    @property
    def count(self) -> int:
        return len(self.files)


@dataclass
class CheckResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class ApplyResult:
    branch: str
    files: list[str]
    status: str


class GitHubDeployer:
    """Safe, local-first GitHub deployment helper.

    The helper never force-pushes. A ZIP is validated before extraction, the
    repository must be clean before applying a patch, and the patch is applied
    to a newly-created branch by default. Push is a separate explicit action.
    """

    MAX_FILES = 10000
    MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024

    def __init__(self, git_executable: str = "git"):
        self.git_executable = git_executable

    @staticmethod
    def _decode(data: bytes | str | None) -> str:
        if data is None:
            return ""
        if isinstance(data, str):
            return data
        return data.decode("utf-8", errors="replace")

    def _run_git(self, repo: str | os.PathLike[str], args: list[str], timeout: int = 120) -> str:
        cmd = [self.git_executable, *args]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(repo),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GitHubDeployError("Git is not installed or is not available in PATH.") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitHubDeployError(f"Git command timed out: {' '.join(cmd)}") from exc
        stdout = self._decode(proc.stdout).strip()
        stderr = self._decode(proc.stderr).strip()
        if proc.returncode != 0:
            raise GitHubDeployError(stderr or stdout or f"Git command failed: {' '.join(cmd)}")
        return stdout

    def validate_repo(self, repo: str | os.PathLike[str], require_clean: bool = False) -> Path:
        repo_path = Path(repo).expanduser().resolve()
        if not repo_path.exists() or not repo_path.is_dir():
            raise GitHubDeployError("Repository folder does not exist.")
        root = self._run_git(repo_path, ["rev-parse", "--show-toplevel"])
        root_path = Path(root).resolve()
        if root_path != repo_path:
            # Normalize to the actual top-level repository so all following
            # operations are deterministic even if the user selected a subfolder.
            repo_path = root_path
        if require_clean:
            status = self._run_git(repo_path, ["status", "--porcelain"])
            if status.strip():
                raise GitHubDeployError(
                    "The repository has uncommitted changes. Commit/stash them before applying an Agent patch."
                )
        return repo_path

    def current_branch(self, repo: str | os.PathLike[str]) -> str:
        root = self.validate_repo(repo)
        branch = self._run_git(root, ["branch", "--show-current"])
        return branch.strip() or "HEAD"

    def remote_url(self, repo: str | os.PathLike[str], remote: str = "origin") -> str:
        root = self.validate_repo(repo)
        return self._run_git(root, ["remote", "get-url", remote]).strip()

    @staticmethod
    def infer_repo_slug(remote_url: str) -> str:
        value = (remote_url or "").strip()
        if not value:
            return ""
        # https://github.com/owner/repo.git
        m = re.search(r"github\.com[/:]([^/\s:]+)/([^/\s]+?)(?:\.git)?$", value, re.I)
        if not m:
            return ""
        owner, repo = m.group(1), m.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]
        return f"{owner}/{repo}"

    @classmethod
    def _safe_member_name(cls, info: zipfile.ZipInfo) -> str | None:
        raw = info.filename.replace("\\", "/")
        if not raw or raw.endswith("/"):
            return None
        if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
            raise GitHubDeployError(f"Unsafe absolute ZIP path: {info.filename}")
        path = PurePosixPath(raw)
        if any(part in {"", ".", ".."} for part in path.parts):
            raise GitHubDeployError(f"Unsafe ZIP path: {info.filename}")
        if path.parts and path.parts[0].casefold() == ".git":
            raise GitHubDeployError("Patch ZIP is not allowed to modify the .git directory.")
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and stat.S_ISLNK(mode):
            raise GitHubDeployError(f"Symbolic links are not allowed in patch ZIPs: {info.filename}")
        if info.flag_bits & 0x1:
            raise GitHubDeployError(f"Encrypted ZIP entries are not supported: {info.filename}")
        return path.as_posix()

    def inspect_patch(self, zip_path: str | os.PathLike[str]) -> PatchInspection:
        path = Path(zip_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise GitHubDeployError("Patch ZIP does not exist.")
        try:
            with zipfile.ZipFile(path, "r") as zf:
                files: list[str] = []
                total = 0
                for info in zf.infolist():
                    safe = self._safe_member_name(info)
                    if safe is None:
                        continue
                    files.append(safe)
                    total += int(info.file_size or 0)
                    if len(files) > self.MAX_FILES:
                        raise GitHubDeployError("Patch ZIP contains too many files.")
                    if total > self.MAX_UNCOMPRESSED_BYTES:
                        raise GitHubDeployError("Patch ZIP is too large after extraction.")
                if not files:
                    raise GitHubDeployError("Patch ZIP contains no files.")
                return PatchInspection(files=files, total_bytes=total)
        except zipfile.BadZipFile as exc:
            raise GitHubDeployError("Selected file is not a valid ZIP archive.") from exc

    def _new_branch_name(self, prefix: str = "agent-update") -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_prefix = re.sub(r"[^A-Za-z0-9._/-]+", "-", prefix.strip() or "agent-update")
        return f"{safe_prefix}-{stamp}"

    def apply_patch(
        self,
        repo: str | os.PathLike[str],
        zip_path: str | os.PathLike[str],
        branch_prefix: str = "agent-update",
    ) -> ApplyResult:
        root = self.validate_repo(repo, require_clean=True)
        inspection = self.inspect_patch(zip_path)
        branch = self._new_branch_name(branch_prefix)
        self._run_git(root, ["switch", "-c", branch])

        try:
            with zipfile.ZipFile(Path(zip_path).expanduser().resolve(), "r") as zf:
                for info in zf.infolist():
                    safe = self._safe_member_name(info)
                    if safe is None:
                        continue
                    dest = (root / Path(*PurePosixPath(safe).parts)).resolve()
                    try:
                        dest.relative_to(root)
                    except ValueError as exc:
                        raise GitHubDeployError(f"Patch path escaped the repository: {safe}") from exc
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info, "r") as src, dest.open("wb") as out:
                        shutil.copyfileobj(src, out)
        except Exception:
            # We started from a clean worktree. Best effort: return the branch to
            # its pristine HEAD if extraction fails partway through.
            try:
                self._run_git(root, ["reset", "--hard", "HEAD"])
                self._run_git(root, ["clean", "-fd"])
            except Exception:
                pass
            raise

        status = self._run_git(root, ["status", "--short"])
        if not status.strip():
            raise GitHubDeployError("The patch produced no repository changes.")
        return ApplyResult(branch=branch, files=inspection.files, status=status)

    def run_command(self, repo: str | os.PathLike[str], command: str, timeout: int = 900) -> CheckResult:
        root = self.validate_repo(repo)
        cmd = (command or "").strip()
        if not cmd:
            return CheckResult(command="", returncode=0, stdout="", stderr="")
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(root),
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=max(1, int(timeout)),
                check=False,
            )
            return CheckResult(
                command=cmd,
                returncode=int(proc.returncode),
                stdout=self._decode(proc.stdout).strip(),
                stderr=self._decode(proc.stderr).strip(),
            )
        except subprocess.TimeoutExpired as exc:
            return CheckResult(command=cmd, returncode=124, stdout=self._decode(exc.stdout), stderr="Timed out")

    def run_checks(
        self,
        repo: str | os.PathLike[str],
        test_command: str = "python -m pytest -q",
        build_command: str = "",
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        for command in (test_command, build_command):
            if not (command or "").strip():
                continue
            result = self.run_command(repo, command)
            results.append(result)
            if not result.ok:
                break
        return results

    def commit_and_push(
        self,
        repo: str | os.PathLike[str],
        message: str,
        remote: str = "origin",
    ) -> tuple[str, str]:
        root = self.validate_repo(repo)
        status = self._run_git(root, ["status", "--porcelain"])
        if not status.strip():
            raise GitHubDeployError("There are no changes to commit.")
        branch = self.current_branch(root)
        if branch == "HEAD":
            raise GitHubDeployError("Refusing to push from a detached HEAD.")
        commit_message = (message or "").strip() or "Update Your Assistant Agent"
        self._run_git(root, ["add", "-A"])
        self._run_git(root, ["commit", "-m", commit_message], timeout=180)
        # Explicitly no --force/--force-with-lease. A non-fast-forward push fails safely.
        output = self._run_git(root, ["push", "-u", remote, branch], timeout=300)
        commit = self._run_git(root, ["rev-parse", "HEAD"])
        return commit.strip(), output

    def discard_paths(self, repo: str | os.PathLike[str], paths: Iterable[str]) -> None:
        """Discard only paths known to have come from the applied ZIP.

        This avoids a broad `git clean -fd` in normal UI use and therefore does
        not remove unrelated untracked user files.
        """
        root = self.validate_repo(repo)
        unique = []
        for raw in paths:
            p = PurePosixPath(str(raw).replace("\\", "/"))
            if not p.parts or any(part in {"", ".", ".."} for part in p.parts):
                continue
            safe = p.as_posix()
            if safe not in unique:
                unique.append(safe)
        if not unique:
            return

        tracked: list[str] = []
        untracked: list[str] = []
        for rel in unique:
            proc = subprocess.run(
                [self.git_executable, "ls-files", "--error-unmatch", "--", rel],
                cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            (tracked if proc.returncode == 0 else untracked).append(rel)
        if tracked:
            self._run_git(root, ["restore", "--source=HEAD", "--staged", "--worktree", "--", *tracked])
        for rel in untracked:
            target = (root / Path(*PurePosixPath(rel).parts)).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                continue
            if target.is_file() or target.is_symlink():
                target.unlink(missing_ok=True)
            elif target.is_dir():
                shutil.rmtree(target, ignore_errors=True)

    def latest_action_run(self, repo_slug: str, token: str = "") -> dict:
        slug = (repo_slug or "").strip().strip("/")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", slug):
            raise GitHubDeployError("GitHub repository must be in owner/repository format.")
        url = f"https://api.github.com/repos/{slug}/actions/runs?per_page=1"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Your-Assistant-Agent",
        }
        if (token or "").strip():
            headers["Authorization"] = f"Bearer {token.strip()}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise GitHubDeployError(f"GitHub API error {exc.code}: {body[:500]}") from exc
        except Exception as exc:
            raise GitHubDeployError(f"Could not query GitHub Actions: {exc}") from exc
        runs = data.get("workflow_runs") or []
        if not runs:
            return {}
        run = runs[0]
        return {
            "name": str(run.get("name") or ""),
            "status": str(run.get("status") or ""),
            "conclusion": str(run.get("conclusion") or ""),
            "branch": str(run.get("head_branch") or ""),
            "created_at": str(run.get("created_at") or ""),
            "updated_at": str(run.get("updated_at") or ""),
            "html_url": str(run.get("html_url") or ""),
        }
