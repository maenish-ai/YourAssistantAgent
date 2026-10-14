from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest

from your_assistant_agent.github_deploy import GitHubDeployer, GitHubDeployError


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def test_infer_github_repo_slug():
    assert GitHubDeployer.infer_repo_slug("https://github.com/acme/demo.git") == "acme/demo"
    assert GitHubDeployer.infer_repo_slug("git@github.com:acme/demo.git") == "acme/demo"
    assert GitHubDeployer.infer_repo_slug("https://example.com/acme/demo.git") == ""


def test_inspect_patch_accepts_safe_zip(tmp_path: Path):
    archive = tmp_path / "safe.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("your_assistant_agent/example.py", "VALUE = 1\n")
        zf.writestr("README.txt", "ok\n")
    info = GitHubDeployer().inspect_patch(archive)
    assert info.count == 2
    assert "README.txt" in info.files


def test_inspect_patch_rejects_path_traversal(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../evil.txt", "nope")
    with pytest.raises(GitHubDeployError):
        GitHubDeployer().inspect_patch(archive)


def test_apply_patch_uses_new_branch_and_never_touches_git_dir(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "Agent Tests")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(repo, "commit", "-m", "baseline")

    archive = tmp_path / "patch.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("base.txt", "updated\n")
        zf.writestr("new.txt", "new\n")

    result = GitHubDeployer().apply_patch(repo, archive, branch_prefix="agent-update-v0.9.0")
    assert result.branch.startswith("agent-update-v0.9.0-")
    assert _git(repo, "branch", "--show-current") == result.branch
    assert (repo / "base.txt").read_text(encoding="utf-8") == "updated\n"
    assert (repo / "new.txt").read_text(encoding="utf-8") == "new\n"
    assert ".git" not in result.files
