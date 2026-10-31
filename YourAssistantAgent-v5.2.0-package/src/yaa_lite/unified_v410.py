"""v4.1 opt-in Windows inventory and safe local task primitives.

Importing this module performs no I/O, launches no threads, and opens no ports.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SECRET_NAMES = {'.env', '.env.local', 'id_rsa', 'id_ed25519', 'credentials.json'}
MAX_APPLY_BYTES = 200 * 1024 * 1024


class UnsafeOperation(ValueError):
    pass


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _safe_relative(value: str) -> Path:
    name = value.replace('\\', '/')
    parts = name.split('/')
    if (not name or name.startswith('/') or re.match(r'^[a-zA-Z]:', name) or
            any(p in ('', '.', '..') or p.endswith((' ', '.')) or ':' in p or
                p.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'LPT1'}
                for p in parts)):
        raise UnsafeOperation('Unsafe relative path')
    if any(p.lower() in SECRET_NAMES or p.lower().endswith(('.key', '.pem')) for p in parts):
        raise UnsafeOperation('Protected file')
    return Path(*parts)


def inventory_windows() -> list[dict[str, str]]:
    """On-demand registry and Start Menu inventory. No execution or network.

    Best effort: per-user/machine uninstall entries and .lnk names; does not
    promise to discover portable applications or infer their capabilities.
    """
    if os.name != 'nt':
        return []
    import winreg
    found: dict[tuple[str, str], dict[str, str]] = {}
    uninstall = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                base = winreg.OpenKey(hive, uninstall, 0, winreg.KEY_READ | view)
            except OSError:
                continue
            with base:
                index = 0
                while True:
                    try:
                        keyname = winreg.EnumKey(base, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(base, keyname) as sub:
                            name = str(winreg.QueryValueEx(sub, 'DisplayName')[0]).strip()
                            if not name:
                                continue
                            try:
                                version = str(winreg.QueryValueEx(sub, 'DisplayVersion')[0])
                            except OSError:
                                version = ''
                            found[(name.casefold(), version)] = {'name': name, 'version': version, 'source': 'registry'}
                    except OSError:
                        continue
    roots = [os.environ.get('APPDATA', ''), os.environ.get('PROGRAMDATA', '')]
    for root in filter(None, roots):
        folder = Path(root) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs'
        if not folder.exists():
            continue
        try:
            for item in folder.rglob('*.lnk'):
                if item.is_file():
                    name = item.stem.strip()
                    found.setdefault((name.casefold(), ''), {'name': name, 'version': '', 'source': 'start-menu'})
        except OSError:
            continue
    return sorted(found.values(), key=lambda x: x['name'].casefold())


def save_inventory(path: Path, items: list[dict[str, str]]) -> None:
    """Store locally only; no credentials, executable paths, or network calls."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'updated': int(time.time()), 'programs': items}, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


@dataclass(frozen=True)
class Change:
    path: str
    action: str
    sha256: str
    size: int


class SafeFilePlan:
    """Reviewable copy plan, hash pinning, backup and best-effort rollback.

    Caller must validate a fresh operation-bound PIN before calling apply().
    Do not use against untrusted or concurrently modified destinations.
    """
    def __init__(self, staged: Path, destination: Path, approved_root: Path):
        self.staged = Path(staged).resolve()
        self.destination = Path(destination).resolve()
        self.root = Path(approved_root).resolve()
        if not _under(self.staged, self.root) or not _under(self.destination, self.root):
            raise UnsafeOperation('Outside approved root')
        if not self.staged.is_dir() or self.staged == self.destination or _under(self.destination, self.staged):
            raise UnsafeOperation('Invalid staging or destination')
        self.changes: list[Change] = []
        total = 0
        for src in self.staged.rglob('*'):
            if src.is_symlink():
                raise UnsafeOperation('Symlinks not allowed')
            if not src.is_file():
                continue
            rel = _safe_relative(src.relative_to(self.staged).as_posix())
            dst = self.destination / rel
            if dst.is_symlink() or not _under(dst, self.root):
                raise UnsafeOperation('Unsafe destination')
            size = src.stat().st_size
            total += size
            if total > MAX_APPLY_BYTES:
                raise UnsafeOperation('Size limit exceeded')
            digest = hashlib.sha256(src.read_bytes()).hexdigest()
            if dst.exists() and not dst.is_file():
                raise UnsafeOperation('Destination is not a file')
            if dst.exists() and hashlib.sha256(dst.read_bytes()).hexdigest() == digest:
                continue
            self.changes.append(Change(rel.as_posix(), 'replace' if dst.exists() else 'create', digest, size))

    def preview(self) -> list[dict]:
        return [vars(c).copy() for c in self.changes]

    def apply(self, *, authorized: bool, backup_root: Path) -> dict:
        if not authorized:
            raise PermissionError('Fresh PIN approval required')
        backup_root = Path(backup_root).resolve()
        if not _under(backup_root, self.root) or _under(backup_root, self.destination):
            raise UnsafeOperation('Backup must be in approved root, outside destination')
        backup = backup_root / ('yaa-' + uuid.uuid4().hex)
        backup.mkdir(parents=True, exist_ok=False)
        completed = []
        try:
            for change in self.changes:
                rel = _safe_relative(change.path)
                src, dst = self.staged / rel, self.destination / rel
                if src.is_symlink() or dst.is_symlink() or not _under(dst, self.root):
                    raise UnsafeOperation('Path changed since review')
                if hashlib.sha256(src.read_bytes()).hexdigest() != change.sha256:
                    raise UnsafeOperation('Staged file changed since review')
                if change.action == 'create' and dst.exists():
                    raise UnsafeOperation('Destination changed since review')
                if change.action == 'replace' and not dst.is_file():
                    raise UnsafeOperation('Destination changed since review')
                old = backup / rel
                if dst.exists():
                    old.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dst, old)
                dst.parent.mkdir(parents=True, exist_ok=True)
                tmp = dst.with_name(dst.name + '.yaa-' + uuid.uuid4().hex + '.tmp')
                try:
                    shutil.copy2(src, tmp)
                    os.replace(tmp, dst)
                finally:
                    tmp.unlink(missing_ok=True)
                completed.append((dst, old, change.action))
            return {'count': len(completed), 'backup': str(backup)}
        except Exception:
            for dst, old, action in reversed(completed):
                if action == 'create':
                    dst.unlink(missing_ok=True)
                elif old.exists():
                    shutil.copy2(old, dst)
            raise


class TaskQueue:
    """Single worker, no thread until start(); cooperative cancellation."""
    def __init__(self):
        self.tasks: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None

    def submit(self, callback: Callable[[threading.Event], None]) -> None:
        if self.stop_event.is_set():
            raise RuntimeError('Queue stopped')
        self.tasks.put(callback)

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.worker = threading.Thread(target=self._run, name='yaa-task-worker', daemon=True)
        self.worker.start()

    def _run(self):
        while not self.stop_event.is_set():
            try:
                callback = self.tasks.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.cancel_event.clear()
                callback(self.cancel_event)
            finally:
                self.tasks.task_done()

    def cancel_current(self):
        self.cancel_event.set()

    def stop(self):
        self.cancel_current()
        self.stop_event.set()


def git_status(repo: Path) -> str:
    """Read-only Git operation, bounded runtime and no shell."""
    result = subprocess.run(['git', '-C', str(Path(repo).resolve()), 'status', '--short'],
                            capture_output=True, text=True, timeout=10, check=True)
    return result.stdout
