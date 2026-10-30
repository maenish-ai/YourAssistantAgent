"""Explicit, local GitHub ZIP publishing workflow for YourAssistantAgent.

No cloud model receives file bytes or Git credentials. A ZIP is previewed against
an already-authenticated local checkout; only an explicit UI approval can publish.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

TARGET_REPO = 'maenish-ai/YourAssistantAgent'
MAX_ENTRIES = 2000
MAX_UNPACKED = 300 * 1024 * 1024
MAX_MEMBER = 100 * 1024 * 1024
BLOCKED_PARTS = {'.git', '.ssh', '.gnupg', '.venv', 'venv', '__pycache__', 'node_modules'}
WINDOWS_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
ROOT_ENTRIES = {'src', 'tests', '.github', 'assets', 'installer', 'launcher.py', 'readme.md', 'pyproject.toml'}
PENDING_UPLOAD_KEY = 'yaa.pending-upload-commit'
PENDING_UPLOAD_REPO_KEY = 'yaa.pending-upload-repository'
_PUBLISH_LOCKS: dict[str, threading.RLock] = {}
_PUBLISH_LOCKS_GUARD = threading.Lock()


class GitHubUploadError(Exception):
    """Expected refusal or failure, safe to display in the UI."""


@dataclass(frozen=True)
class UploadFile:
    member: str
    relative_path: str
    sha256: str
    size: int
    change: str


@dataclass(frozen=True)
class UploadPlan:
    archive: Path
    archive_sha256: str
    checkout: Path
    git_executable: str
    base_head: str
    branch: str
    files: tuple[UploadFile, ...]
    pending_commit: str = ''
    expected_repo: str = TARGET_REPO

    @property
    def changes(self) -> tuple[UploadFile, ...]:
        return tuple(f for f in self.files if f.change != 'unchanged')


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def find_git() -> str:
    git = shutil.which('git')
    if git:
        return git
    if os.name == 'nt':
        local = Path(os.environ.get('LOCALAPPDATA', ''))
        root = local / 'GitHubDesktop'
        paths = sorted(root.glob('app-*/resources/app/git/cmd/git.exe'), reverse=True) if root.is_dir() else []
        paths += [Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Git' / 'cmd' / 'git.exe']
        for path in paths:
            if path.is_file():
                return str(path)
    raise GitHubUploadError('Git was not found. Install Git or GitHub Desktop first.')


def _git(git: str, checkout: Path, *args: str, timeout: int = 35) -> str:
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    try:
        p = subprocess.run([git, '-C', str(checkout), *args], capture_output=True,
                           text=True, encoding='utf-8', errors='replace',
                           timeout=timeout, env=env,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitHubUploadError(f'Git command could not complete: {type(exc).__name__}') from exc
    if p.returncode != 0:
        # Avoid leaking passwords, tokens or machine-local repository URLs.
        raise GitHubUploadError(f'Git {args[0]} failed (exit {p.returncode}). Check command-line Git authentication, '
                                'repository permissions and network connection. GitHub Desktop login alone may not authenticate Git.')
    # Keep machine-readable -z output intact. strip() also removes a valid
    # leading space from the first staged filename, breaking the reviewed set.
    return p.stdout.rstrip('\r\n')


def validate_repository(value: str) -> str:
    """Validate a configured GitHub owner/name, never a URL or Git option."""
    repository = str(value or '').strip()
    parts = repository.split('/')
    if (len(parts) != 2 or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?', parts[0])
            or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', parts[1])
            or parts[1] in {'.', '..'}):
        raise GitHubUploadError('GitHub repository must be owner/name, for example maenish-ai/YourAssistantAgent.')
    return repository


def _matches_repository(remote: str, expected_repo: str) -> bool:
    return bool(re.fullmatch(
        r'(?:https://(?:[^/@]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)'
        + re.escape(expected_repo) + r'(?:\.git)?/?', remote, re.I))


def _check_checkout(path: Path, git: str, expected_repo: str = TARGET_REPO) -> tuple[Path, str, str]:
    expected_repo = validate_repository(expected_repo)
    checkout = path.expanduser().resolve()
    if not checkout.is_dir():
        raise GitHubUploadError('Choose an existing local GitHub repository folder.')
    top = Path(_git(git, checkout, 'rev-parse', '--show-toplevel')).resolve()
    if top != checkout:
        raise GitHubUploadError('Choose the repository root, not a subfolder.')
    remote = _git(git, checkout, 'remote', 'get-url', 'origin')
    # Both fetch and push destinations must match. A separate pushurl can direct
    # Git to another host/repository even when the ordinary origin looks right.
    push_urls = _git(git, checkout, 'remote', 'get-url', '--push', '--all', 'origin').splitlines()
    if (not _matches_repository(remote, expected_repo) or len(push_urls) != 1
            or not _matches_repository(push_urls[0], expected_repo)):
        raise GitHubUploadError('The selected folder is not the expected GitHub repository: ' + expected_repo)
    if _git(git, checkout, 'status', '--porcelain=v1', '--untracked-files=all'):
        raise GitHubUploadError('The repository contains uncommitted or untracked changes. Review/commit these in GitHub Desktop first.')
    branch = _git(git, checkout, 'branch', '--show-current')
    if not branch:
        raise GitHubUploadError('Detached HEAD: select a normal branch in GitHub Desktop first.')
    head = _git(git, checkout, 'rev-parse', 'HEAD')
    return checkout, branch, head


def _pending_upload(git: str, checkout: Path, branch: str, head: str,
                    expected_repo: str = TARGET_REPO) -> str:
    """Only offer a retry for this repository, branch and unchanged HEAD."""
    pending = _git(git, checkout, 'config', '--local', '--default', '', '--get', PENDING_UPLOAD_KEY)
    repository = _git(git, checkout, 'config', '--local', '--default', '', '--get', PENDING_UPLOAD_REPO_KEY)
    # Legacy uploads only targeted the original repository; they can be retried
    # there, but must never migrate to a newly configured repository.
    same_repo = repository.casefold() == expected_repo.casefold() if repository else expected_repo.casefold() == TARGET_REPO.casefold()
    return head if same_repo and pending == f'{branch}:{head}' else ''


def _validate_name(name: str) -> str:
    if not name or '\x00' in name or '\\' in name or name.startswith('/'):
        raise GitHubUploadError('ZIP contains an unsafe path.')
    parts = name.rstrip('/').split('/')
    if not parts or any(p in ('', '.', '..') for p in parts):
        raise GitHubUploadError('ZIP contains a relative/path traversal entry.')
    if any(p.lower() in BLOCKED_PARTS for p in parts):
        raise GitHubUploadError('ZIP contains a forbidden internal or dependency folder.')
    for part in parts:
        if (':' in part or any(ord(ch) < 32 or ch in '<>"|?*' for ch in part)
                or part.endswith(('.', ' ')) or part.split('.', 1)[0].upper() in WINDOWS_RESERVED):
            raise GitHubUploadError('ZIP contains a filename not safe on Windows.')
    if len(name) > 235:
        raise GitHubUploadError('ZIP member path is too long.')
    filename = parts[-1].lower()
    if (filename == '.env' or (filename.startswith('.env.') and filename not in ('.env.example', '.env.sample'))
            or filename in ('credentials.json', 'secrets.json', 'desktop-setup.json', 'id_rsa', 'id_ed25519')
            or filename.endswith(('.pem', '.p12', '.pfx', '.key', '.kdbx'))):
        raise GitHubUploadError('ZIP includes a file that looks like a credential/secret. Remove it before publishing.')
    return '/'.join(parts)


def _zip_members(archive: Path, *, repository_name: str = "YourAssistantAgent") -> list[tuple[zipfile.ZipInfo, str]]:
    if not archive.is_file() or archive.suffix.lower() != '.zip' or not zipfile.is_zipfile(archive):
        raise GitHubUploadError('Select a valid ZIP archive.')
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES:
            raise GitHubUploadError(f'ZIP exceeds the {MAX_ENTRIES} entry limit.')
        total = sum(info.file_size for info in infos)
        if total > MAX_UNPACKED:
            raise GitHubUploadError('ZIP expands beyond the 300 MB safety limit.')
        raw: list[tuple[zipfile.ZipInfo, str]] = []
        seen = set()
        for info in infos:
            name = _validate_name(info.filename)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise GitHubUploadError('ZIP contains symbolic links or special files.')
            if info.flag_bits & 1:
                raise GitHubUploadError('Encrypted ZIP entries are not supported.')
            if info.file_size > MAX_MEMBER:
                raise GitHubUploadError('ZIP contains a file larger than 100 MB.')
            if info.is_dir():
                continue
            key = name.casefold()
            if key in seen:
                raise GitHubUploadError('ZIP contains duplicate destination paths.')
            seen.add(key)
            raw.append((info, name))
        if not raw:
            raise GitHubUploadError('ZIP has no usable files.')
        parts = [name.split('/') for _, name in raw]
        common = parts[0][0] if all(len(p) > 1 and p[0] == parts[0][0] for p in parts) else None
        strip = bool(common and (common.casefold() in {repository_name.casefold(),
                                  repository_name.casefold() + '-main', repository_name.casefold() + '-master'}
                                 or re.sub(r'[^a-z0-9]', '', common.lower()) == 'yourassistantagent'
                                 or re.match(r'^yourassistantagent[-_]', common, re.I)
                                 or all(len(p) > 1 and p[1].lower() in ROOT_ENTRIES for p in parts)))
        result = []
        seen.clear()
        for info, name in raw:
            relative = '/'.join(name.split('/')[1:]) if strip else name
            _validate_name(relative)
            key = relative.casefold()
            if key in seen:
                raise GitHubUploadError('ZIP contains conflicting file paths.')
            seen.add(key)
            result.append((info, relative))
        return result


def _safe_destination(checkout: Path, relative: str) -> Path:
    root = checkout.resolve()
    out = root.joinpath(*PurePosixPath(relative).parts)
    parent = out
    while parent != root:
        if parent.is_symlink():
            raise GitHubUploadError('Destination contains a symbolic link; upload cancelled.')
        parent = parent.parent
    if not out.resolve().is_relative_to(root):
        raise GitHubUploadError('ZIP would write outside the repository.')
    if out.exists() and not out.is_file():
        raise GitHubUploadError('ZIP file would overwrite a directory.')
    return out


def prepare_upload(archive: Path | str, checkout: Path | str, git_executable: str | None = None,
                   *, expected_repo: str = TARGET_REPO) -> UploadPlan:
    expected_repo = validate_repository(expected_repo)
    archive = Path(archive).expanduser().resolve()
    if archive.stat().st_size > 300 * 1024 * 1024:
        raise GitHubUploadError('ZIP archive is larger than 300 MB.')
    git = git_executable or find_git()
    checkout, branch, head = _check_checkout(Path(checkout), git, expected_repo)
    entries = _zip_members(archive, repository_name=expected_repo.split('/')[1])
    output = []
    with zipfile.ZipFile(archive) as z:
        for info, relative in entries:
            destination = _safe_destination(checkout, relative)
            h = hashlib.sha256()
            with z.open(info) as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    h.update(block)
            content_hash = h.hexdigest()
            if destination.is_file():
                change = 'unchanged' if _sha256(destination) == content_hash else 'modified'
            else:
                change = 'added'
            output.append(UploadFile(info.filename, relative, content_hash, info.file_size, change))
    pending = _pending_upload(git, checkout, branch, head, expected_repo)
    return UploadPlan(archive, _sha256(archive), checkout, git, head, branch, tuple(output), pending, expected_repo)


def prepare_configured_upload(archive: Path | str, settings, choose_checkout=None) -> UploadPlan:
    """Use the saved target across chats; a picker is needed only for first setup.

    Remote callers omit the picker and fail clearly when no checkout is set.
    A newly chosen checkout is remembered only after repository validation.
    """
    repository = validate_repository(getattr(settings, 'github_repository', TARGET_REPO))
    folder = str(getattr(settings, 'github_checkout', '') or '').strip()
    if not folder:
        if choose_checkout is None:
            raise GitHubUploadError('Configure the local GitHub checkout in Settings before uploading remotely.')
        folder = str(choose_checkout() or '').strip()
        if not folder:
            raise GitHubUploadError('No local GitHub checkout was selected.')
    plan = prepare_upload(archive, folder, expected_repo=repository)
    if str(getattr(settings, 'github_checkout', '') or '') != str(plan.checkout):
        settings.github_repository = repository
        settings.github_checkout = str(plan.checkout)
        settings.save()
    return plan


def describe_plan(plan: UploadPlan) -> str:
    added = sum(f.change == 'added' for f in plan.files)
    modified = sum(f.change == 'modified' for f in plan.files)
    unchanged = sum(f.change == 'unchanged' for f in plan.files)
    names = [f'  {"+" if f.change == "added" else "~"} {f.relative_path}' for f in plan.changes]
    sample = '\n'.join(names[:28])
    if len(names) > 28:
        sample += f'\n  ... and {len(names)-28} more files'
    workflow_note = '\nWARNING: GitHub Actions workflow files will change.' if any(
        f.relative_path.lower().startswith('.github/workflows/') for f in plan.changes) else ''
    pending_note = (f'\nPending upload commit: {plan.pending_commit[:12]} (will retry PUSH).'
                    if plan.pending_commit else '')
    if plan.changes:
        action = 'Approving will WRITE these files, COMMIT, and PUSH to origin.'
    elif plan.pending_commit:
        action = 'Approving will retry PUSH of the pending commit to origin; no new commit will be created.'
    else:
        action = 'All files already match; no commit or push is needed.'
    return (f'Repository: {plan.expected_repo}\nLocal folder: {plan.checkout}\n'
            f'Target branch: {plan.branch}\nArchive: {plan.archive.name}\n'
            f'Added: {added} | Modified: {modified} | Unchanged: {unchanged}\n'
            f'Files to commit:\n{sample}{workflow_note}{pending_note}\n\n'
            f'No files will be deleted. {action}')


def _push_upload(plan: UploadPlan, checkout: Path, branch: str, commit: str) -> str:
    _, current_branch, current_head = _check_checkout(checkout, plan.git_executable, plan.expected_repo)
    if current_branch != branch or current_head != commit:
        raise GitHubUploadError('Repository changed before push. Inspect the local commit in GitHub Desktop.')
    # Persist the branch and commit ID in local Git metadata. A failed or interrupted
    # push can then be retried after a fresh preview and explicit approval.
    _git(plan.git_executable, checkout, 'config', '--local', PENDING_UPLOAD_REPO_KEY, plan.expected_repo)
    _git(plan.git_executable, checkout, 'config', '--local', PENDING_UPLOAD_KEY, f'{branch}:{commit}')
    try:
        _git(plan.git_executable, checkout, 'push', 'origin', f'{commit}:refs/heads/{branch}', timeout=120)
    except GitHubUploadError as exc:
        raise GitHubUploadError(f'Local commit {commit[:12]} is ready, but PUSH FAILED. '
                                'Resolve command-line Git authentication/network issues, then select the same ZIP to retry. '
                                'You can also push this local commit from GitHub Desktop. '
                                f'{exc}') from exc
    try:
        _git(plan.git_executable, checkout, 'config', '--local', '--unset-all', PENDING_UPLOAD_KEY)
        _git(plan.git_executable, checkout, 'config', '--local', '--unset-all', PENDING_UPLOAD_REPO_KEY)
    except GitHubUploadError:
        # Remote publication already succeeded. Do not report a failed upload
        # solely because local metadata could not be cleaned up.
        return ' Push succeeded; local retry metadata could not be cleared.'
    return ''


def publish_upload(plan: UploadPlan, *, approved: bool = False) -> str:
    """Serialize local and remote uploads to the same checkout in this app."""
    key = os.path.normcase(str(plan.checkout.resolve()))
    with _PUBLISH_LOCKS_GUARD:
        lock = _PUBLISH_LOCKS.setdefault(key, threading.RLock())
    with lock:
        return _publish_upload(plan, approved=approved)


def _publish_upload(plan: UploadPlan, *, approved: bool = False) -> str:
    if not approved:
        raise GitHubUploadError('Upload requires explicit user approval.')
    checkout, branch, head = _check_checkout(plan.checkout, plan.git_executable, plan.expected_repo)
    if branch != plan.branch or head != plan.base_head or _sha256(plan.archive) != plan.archive_sha256:
        raise GitHubUploadError('Repository or archive changed since preview. Re-open the upload preview.')
    if _pending_upload(plan.git_executable, checkout, branch, head, plan.expected_repo) != plan.pending_commit:
        raise GitHubUploadError('Pending upload changed since preview. Re-open the upload preview.')
    if not plan.changes:
        if plan.pending_commit:
            note = _push_upload(plan, checkout, branch, head)
            return (f'Published pending upload to {plan.expected_repo} ({branch}). '
                    f'Commit: https://github.com/{plan.expected_repo}/commit/{head}{note}')
        return 'All ZIP files already match the repository. No commit or push needed.'
    # Fully validate and stage archive payloads in an isolated temporary directory
    # before writing a single file into the local checkout.
    with tempfile.TemporaryDirectory(prefix='yaa-github-upload-') as temp:
        stage = Path(temp)
        with zipfile.ZipFile(plan.archive) as z:
            for f in plan.changes:
                target = stage.joinpath(*PurePosixPath(f.relative_path).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with z.open(f.member) as source, target.open('wb') as dest:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        digest.update(block)
                        dest.write(block)
                if digest.hexdigest() != f.sha256:
                    raise GitHubUploadError('ZIP contents changed during validation. No changes were written.')
        for f in plan.changes:
            destination = _safe_destination(checkout, f.relative_path)
            if destination.is_file():
                if _sha256(destination) == f.sha256:
                    raise GitHubUploadError('Existing repository file changed since preview.')
                if next((x for x in plan.files if x.relative_path == f.relative_path), None) != f:
                    raise GitHubUploadError('Preview mismatch; upload cancelled.')
        for f in plan.changes:
            dest = _safe_destination(checkout, f.relative_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage.joinpath(*PurePosixPath(f.relative_path).parts), dest)
    changed = [f.relative_path for f in plan.changes]
    # Batch path arguments to stay below the Windows command-line size limit.
    for start in range(0, len(changed), 40):
        _git(plan.git_executable, checkout, 'add', '--', *changed[start:start + 40])
    staged = _git(plan.git_executable, checkout, 'diff', '--cached', '--name-only', '-z')
    # -z is machine-safe, including filenames with whitespace.
    actual = {p for p in staged.split('\x00') if p}
    if not actual.issubset(set(changed)):
        raise GitHubUploadError('Staged files differ from the reviewed ZIP. No commit or push was run.')
    # On Windows, core.autocrlf and .gitattributes can normalize ZIP bytes to
    # exactly the already-tracked content. Such files produce no staged diff;
    # they must not cause an otherwise valid upload to fail (or an empty commit).
    normalized = set(changed) - actual
    for relative in normalized:
        _git(plan.git_executable, checkout, 'ls-files', '--error-unmatch', '--', relative)
        _git(plan.git_executable, checkout, 'diff', '--quiet', '--', relative)
    if not actual:
        if plan.pending_commit:
            note = _push_upload(plan, checkout, branch, head)
            return (f'Published pending upload to {plan.expected_repo} ({branch}). '
                    f'Commit: https://github.com/{plan.expected_repo}/commit/{head}{note}')
        return 'All ZIP files already match the repository after Git normalization. No commit or push needed.'
    _git(plan.git_executable, checkout, 'commit', '-m', 'Apply reviewed ZIP update via YourAssistantAgent')
    commit = _git(plan.git_executable, checkout, 'rev-parse', 'HEAD')
    note = _push_upload(plan, checkout, branch, commit)
    return f'Published {len(actual)} files to {plan.expected_repo} ({branch}). Commit: https://github.com/{plan.expected_repo}/commit/{commit}{note}'


def is_upload_request(text: str) -> bool:
    s = ' '.join(str(text or '').lower().split())
    action = re.search(r'ارفع|ارفعه|رفع|انشر|ادفع|حدّث|حدث|upload|push|publish|commit', s)
    target = re.search(r'github|جيت\s*[ -]?ها?ب|جتهب|المستودع|\brepo\b|git\s*hub', s)
    question = re.search(r'^(?:كيف|ليش|لماذا|هل|what|how|why)\b', s)
    return bool(action and target and not question)


def apply_v430_ui() -> None:
    """Add a visible ZIP publishing action and intercept explicit upload requests."""
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from .ui.chat_window import ChatWindow

    if getattr(ChatWindow, '_yaa_v430', False):
        return
    old_build = ChatWindow._build
    old_send = ChatWindow.send

    def show(self, content: str) -> None:
        self._append('assistant', content)
        try:
            self.db.add_message('assistant', content, 'hammer', self.session_id)
        except Exception:
            pass

    def upload(self) -> None:
        if getattr(self, 'busy', False):
            return
        zip_paths = [Path(p) for p in getattr(self, 'attachments', []) if Path(p).suffix.lower() == '.zip']
        if not zip_paths:
            chosen = filedialog.askopenfilename(parent=self, title='Choose a ZIP archive', filetypes=[('ZIP files', '*.zip')])
            if not chosen:
                return
            zip_paths = [Path(chosen)]
        if len(zip_paths) != 1:
            messagebox.showerror('GitHub upload', 'Select exactly one ZIP archive per upload.', parent=self)
            return
        candidate_paths = [Path.home() / 'Documents' / 'GitHub' / 'YourAssistantAgent',
                           Path.home() / 'Desktop' / 'YourAssistantAgent']
        default = next((p for p in candidate_paths if p.is_dir()), Path.home())
        def choose_checkout():
            return filedialog.askdirectory(parent=self, title='Select local GitHub checkout',
                                           initialdir=str(default), mustexist=True)
        try:
            plan = prepare_configured_upload(zip_paths[0], self.settings, choose_checkout)
            if not plan.changes and not plan.pending_commit:
                show(self, 'ZIP inspected. No file changes detected; nothing was published.')
                return
            if not messagebox.askyesno('Approve GitHub Commit + Push', describe_plan(plan), parent=self):
                show(self, 'GitHub ZIP upload cancelled. No files were changed.')
                return
            # No network access or repository writes before affirmative GUI approval.
            self.busy = True
            if hasattr(self, '_v300_update_buttons'):
                self._v300_update_buttons()
            message = self.input.get('1.0', 'end-1c').strip() or 'Upload ZIP to GitHub'
            self.input.delete('1.0', 'end')
            self._append('user', message)
            self.db.add_message('user', message, 'hammer', self.session_id)
            show(self, 'GitHub upload approved. Applying reviewed ZIP changes...')
            import threading
            def work():
                try:
                    result = publish_upload(plan, approved=True)
                except Exception as exc:
                    result = 'GitHub upload failed: ' + str(exc)
                def finish():
                    self.busy = False
                    if hasattr(self, '_v300_update_buttons'):
                        self._v300_update_buttons()
                    show(self, result)
                    if result.startswith('Published '):
                        self.attachments.clear()
                        label = getattr(self, '_v420_files_label', None)
                        if label and label.winfo_exists():
                            label.configure(text='No attachments')
                self.after(0, finish)
            threading.Thread(target=work, daemon=True, name='yaa-github-zip-publish').start()
        except (GitHubUploadError, OSError, ValueError, zipfile.BadZipFile) as exc:
            messagebox.showerror('GitHub upload', str(exc), parent=self)

    def build(self):
        old_build(self)
        # v4.2 creates an attachment toolbar in the main grid's row 6.
        toolbar = next((child for child in self.winfo_children()
                        if isinstance(child, tk.Frame)
                        and child.grid_info().get('row') == 6), None)
        if toolbar is not None:
            tk.Button(toolbar, text='⬆ ZIP → GitHub',
                      command=lambda: upload(self)).pack(side='left', padx=4)

    def send(self):
        if getattr(self,'_v300_mic_active',False):
            self._v300_finish_dictation();return
        text = self.input.get('1.0', 'end-1c').strip()
        if is_upload_request(text):
            return upload(self)
        return old_send(self)

    ChatWindow._build = build
    ChatWindow.send = send
    ChatWindow._v430_upload = upload
    ChatWindow._yaa_v430 = True
