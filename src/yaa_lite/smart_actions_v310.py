"""Your Assistant Agent v3.1: opt-in, local, lightweight action primitives.

This module does not run on import, call Groq, access a browser, or start threads.
All mutations require a caller-issued, operation-bound PIN authorization.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

MAX_ZIP_BYTES = 200 * 1024 * 1024
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_ENTRIES = 3000
BLOCKED_NAMES = {'.env', '.env.local', 'id_rsa', 'id_ed25519', 'credentials.json'}


class ActionError(Exception):
    pass


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


class Workspace:
    def __init__(self, roots: list[Path], staging: Path):
        self.roots = [Path(p).expanduser().resolve() for p in roots]
        self.staging = Path(staging).expanduser().resolve()
        if not self.roots or not any(_inside(self.staging, p) for p in self.roots):
            raise ActionError('Staging must be inside an approved root')

    def check(self, path: Path) -> Path:
        p = Path(path).expanduser().resolve(strict=False)
        if not any(_inside(p, root) for root in self.roots):
            raise ActionError('Path is outside approved workspace')
        return p

    def stage_zip(self, source: Path) -> dict:
        source = self.check(source)
        if not source.is_file() or not zipfile.is_zipfile(source):
            raise ActionError('Not a valid ZIP file')
        self.staging.mkdir(parents=True, exist_ok=True)
        target = Path(tempfile.mkdtemp(prefix='yaa-', dir=str(self.staging)))
        entries = []
        total = 0
        try:
            with zipfile.ZipFile(source) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_ENTRIES:
                    raise ActionError('Too many ZIP entries')
                seen_paths = set()
                for info in infos:
                    name = info.filename.replace('\\', '/')
                    parts = name.rstrip('/').split('/')
                    if (not name or name.startswith('/') or '\x00' in name or
                            any(p in ('', '.', '..') for p in parts) or
                            re.match(r'^[a-zA-Z]:', name)):
                        raise ActionError('Unsafe archive path')
                    # Refuse symlinks and non-regular Unix file types.
                    unix_type = (info.external_attr >> 16) & 0o170000
                    if unix_type not in (0, 0o100000, 0o040000):
                        raise ActionError('Unsupported archive entry type')
                    if info.flag_bits & 0x1:
                        raise ActionError('Encrypted ZIP entries are not supported')
                    if info.file_size > MAX_FILE_BYTES:
                        raise ActionError('ZIP member too large')
                    total += info.file_size
                    if total > MAX_ZIP_BYTES:
                        raise ActionError('ZIP uncompressed size limit exceeded')
                    if tuple(parts) in seen_paths:
                        raise ActionError('Duplicate ZIP member path')
                    seen_paths.add(tuple(parts))
                    dest = target.joinpath(*parts)
                    if not _inside(dest, target):
                        raise ActionError('ZIP path escapes staging')
                    if info.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        written = 0
                        with archive.open(info) as inp, dest.open('xb') as out:
                            while True:
                                chunk = inp.read(65536)
                                if not chunk:
                                    break
                                written += len(chunk)
                                if written > MAX_FILE_BYTES or total > MAX_ZIP_BYTES:
                                    raise ActionError('ZIP extraction limit exceeded')
                                out.write(chunk)
                        entries.append(name)
            return {'staging': str(target), 'files': entries, 'count': len(entries)}
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise

    def compare(self, staged: Path, destination: Path) -> dict:
        staged = self.check(staged)
        destination = self.check(destination)
        if not _inside(staged, self.staging) or not staged.is_dir():
            raise ActionError('Source must be a staged directory')
        added, changed, unchanged, blocked = [], [], [], []
        for src in staged.rglob('*'):
            if not src.is_file():
                continue
            rel = src.relative_to(staged)
            if any(p.lower() in BLOCKED_NAMES or p.lower().endswith(('.pem', '.key')) for p in rel.parts):
                blocked.append(str(rel))
                continue
            dst = destination / rel
            self.check(dst)
            if dst.exists() and (not dst.is_file() or dst.is_symlink()):
                blocked.append(str(rel))
            elif not dst.exists():
                added.append(str(rel))
            elif _sha(src) == _sha(dst):
                unchanged.append(str(rel))
            else:
                changed.append(str(rel))
        return {'added': added, 'changed': changed, 'unchanged': unchanged, 'blocked': blocked,
                'staging': str(staged), 'destination': str(destination)}


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


class PinVault:
    """Scrypt-protected local PIN verification. Never sends PIN to cloud."""
    def __init__(self, state_file: Path):
        self.path = Path(state_file)
        self._failures = 0
        self._lock_until = 0.0

    def enrolled(self) -> bool:
        return self.path.is_file()

    def enroll(self, pin: str) -> None:
        if self.enrolled():
            raise ActionError('PIN already enrolled; explicit reset required')
        if not re.fullmatch(r'\d{6,12}', pin):
            raise ActionError('PIN must contain 6-12 digits')
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(pin.encode(), salt=salt, n=2**14, r=8, p=1)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('x', encoding='utf-8') as f:
            json.dump({'salt': salt.hex(), 'hash': digest.hex()}, f)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def verify(self, pin: str) -> bool:
        if time.monotonic() < self._lock_until or not self.enrolled():
            return False
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            actual = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(data['salt']), n=2**14, r=8, p=1)
            ok = hmac.compare_digest(actual, bytes.fromhex(data['hash']))
        except (ValueError, KeyError, OSError):
            ok = False
        if ok:
            self._failures = 0
        else:
            self._failures += 1
            if self._failures >= 5:
                self._lock_until = time.monotonic() + 60
                self._failures = 0
        return ok


@dataclass
class Approval:
    action: str
    fingerprint: str
    expires: float
    used: bool = False


class ApprovalGate:
    def __init__(self, vault: PinVault):
        self.vault = vault
        self.pending: Approval | None = None

    def request(self, action: str, payload: dict) -> str:
        if action not in {'replace_files', 'delete_files', 'git_commit', 'git_push', 'publish', 'add_program'}:
            raise ActionError('Unrecognized protected operation')
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.pending = Approval(action, fingerprint, time.monotonic() + 120)
        return fingerprint

    def authorize(self, action: str, payload: dict, pin: str) -> bool:
        approval = self.pending
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if not approval or approval.used or time.monotonic() > approval.expires:
            return False
        if approval.action != action or approval.fingerprint != fingerprint:
            return False
        if not self.vault.verify(pin):
            return False
        approval.used = True
        return True


def git_status(repo: Path, workspace: Workspace, git: str = 'git') -> dict:
    repo = workspace.check(repo)
    if not (repo / '.git').exists():
        raise ActionError('Not a Git repository')
    try:
        result = subprocess.run([git, '-C', str(repo), 'status', '--porcelain=v1', '--branch'],
                                capture_output=True, text=True, encoding='utf-8', errors='replace',
                                timeout=8, check=False, stdin=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ActionError('Git status unavailable') from exc
    if result.returncode:
        raise ActionError('Git status failed')
    lines = result.stdout.splitlines()
    return {'branch': lines[0][3:] if lines and lines[0].startswith('## ') else '',
            'changes': lines[1:] if lines and lines[0].startswith('## ') else lines}


class LearningPreferences:
    """Explicit opt-in preferences, not full chat history or auto-trained model."""
    def __init__(self, file: Path):
        self.file = Path(file)

    def read(self) -> dict:
        if not self.file.exists():
            return {}
        data = json.loads(self.file.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}

    def remember(self, key: str, value: str, confirmed: bool = False) -> None:
        if not confirmed:
            raise ActionError('Preference requires user confirmation')
        if not re.fullmatch(r'[a-z][a-z0-9_]{1,60}', key):
            raise ActionError('Invalid preference key')
        if len(value) > 500 or re.search(r'(?i)(password|secret|token|api.key|كلمة مرور)', key):
            raise ActionError('Sensitive or oversized preference')
        data = self.read()
        data[key] = value
        self.file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.file.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.file)

    def forget(self, key: str) -> None:
        data = self.read()
        data.pop(key, None)
        self.file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
