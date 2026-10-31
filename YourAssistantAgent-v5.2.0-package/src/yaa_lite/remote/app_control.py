"""Discover and launch observed Start-menu shortcuts, without command strings."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import secrets
import time

from ..agent.intent import normalized_command


@dataclass(frozen=True)
class ObservedApplication:
    path: Path
    root: Path
    signature: tuple
    observed_at: float


class AppControl:
    """Methods require WindowsDesktop's enabled, unlocked desktop session."""

    @staticmethod
    def _application_roots():
        # APPDATA follows Windows' roaming-profile location. Common and personal
        # shortcuts can share a name; keep both entries so the owner can choose.
        return [Path(value) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs'
                for name in ('APPDATA', 'PROGRAMDATA')
                if (value := os.environ.get(name))]

    @staticmethod
    def _shortcut_signature(path: Path, root: Path):
        from .desktop import DesktopError
        if path.suffix.lower() != '.lnk' or path.is_symlink():
            raise DesktopError('هذا ليس اختصار برنامج مرصوداً صالحاً.')
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise DesktopError('تغيّر مسار اختصار البرنامج. حدّث قائمة البرامج.')
        parent = path.parent
        while parent != root and parent != parent.parent:
            if parent.is_symlink():
                raise DesktopError('اختصار البرنامج موجود داخل رابط رمزي. حدّث قائمة البرامج.')
            parent = parent.parent
        metadata = path.stat()
        if metadata.st_size > 1024 * 1024:
            raise DesktopError('حجم اختصار البرنامج غير معتاد؛ لم يتم تشغيله.')
        # A changed shortcut must be observed again even if its name is stable.
        with path.open('rb') as source:
            payload = source.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            raise DesktopError('حجم اختصار البرنامج غير معتاد؛ لم يتم تشغيله.')
        digest = hashlib.sha256(payload).hexdigest()
        return (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns, digest)

    def list_applications(self, query='', offset=0):
        from .desktop import DesktopError
        if not isinstance(query, str) or len(query) > 180:
            raise DesktopError('اسم البحث عن البرنامج يجب ألا يتجاوز 180 حرفاً.')
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 2000:
            raise DesktopError('موضع قائمة البرامج غير صالح.')
        with self._lock, self._session():
            now = time.monotonic()
            self._applications = {key: value for key, value in self._applications.items()
                                  if now - value.observed_at <= 120}
            candidates = []
            seen = set()
            query = normalized_command(query)
            deadline = now + 5
            inspected = 0
            truncated = False
            for raw_root in self._application_roots():
                try:
                    root = Path(raw_root).resolve(strict=True)
                    if not root.is_dir():
                        continue
                    for directory, subdirs, files in os.walk(root, followlinks=False):
                        if time.monotonic() > deadline:
                            truncated = True
                            break
                        subdirs[:] = sorted(name for name in subdirs
                            if not (Path(directory) / name).is_symlink())
                        for filename in sorted(files):
                            inspected += 1
                            if inspected > 2000 or time.monotonic() > deadline:
                                truncated = True
                                break
                            path = Path(directory) / filename
                            if path.suffix.lower() != '.lnk' or path.is_symlink():
                                continue
                            if query and query not in normalized_command(path.stem):
                                continue
                            resolved = path.resolve(strict=True)
                            if not resolved.is_relative_to(root) or resolved in seen:
                                continue
                            seen.add(resolved)
                            candidates.append((path, root))
                        if truncated:
                            break
                except OSError:
                    continue
                if truncated:
                    break
            candidates.sort(key=lambda row: (normalized_command(row[0].stem), str(row[0]).casefold()))
            rows = []
            for path, root in candidates[offset:offset + 10]:
                try:
                    signature = self._shortcut_signature(path, root)
                except (OSError, DesktopError):
                    continue
                identifier = secrets.token_urlsafe(12)
                self._applications[identifier] = ObservedApplication(path, root, signature, time.monotonic())
                rows.append({'id': identifier, 'name': path.stem[:180],
                             'location': path.relative_to(root).as_posix()[:100]})
            # Bound retained IDs while allowing pagination without invalidating
            # every application observed on the previous page.
            while len(self._applications) > 400:
                self._applications.pop(next(iter(self._applications)))
            return {'applications': rows, 'total': len(candidates),
                    'next_offset': offset + 10 if offset + 10 < len(candidates) else None,
                    'truncated': truncated,
                    'note': 'Observed Start-menu shortcuts only, not every installed application. '
                            'Choose a returned ID; duplicate names need selection. IDs expire in 120 seconds.'}

    def launch_application(self, identifier):
        from .desktop import DesktopError
        with self._lock, self._session():
            item = self._applications.get(str(identifier))
            if not item or time.monotonic() - item.observed_at > 120:
                raise DesktopError('حدّث قائمة البرامج واختر معرّفاً مرصوداً قبل التشغيل.')
            try:
                current = self._shortcut_signature(item.path, item.root)
            except (OSError, DesktopError):
                raise DesktopError('تغيّر اختصار البرنامج. حدّث قائمة البرامج قبل التشغيل.') from None
            if current != item.signature:
                raise DesktopError('تغيّر اختصار البرنامج. حدّث قائمة البرامج قبل التشغيل.')
            try:
                os.startfile(str(item.path))
            except OSError:
                raise DesktopError('رفض Windows تشغيل الاختصار. افحص البرنامج من شاشة الهاتف.') from None
            return {'ok': True, 'application': item.path.stem,
                    'result': 'أُرسل طلب تشغيل الاختصار إلى Windows. راقب النافذة للتأكد من فتح البرنامج.'}

    def open_folder(self, path):
        from .desktop import DesktopError
        with self._lock, self._session():
            if not isinstance(path, (str, Path)):
                raise DesktopError('مسار المجلد غير صالح.')
            try:
                folder = Path(path).resolve(strict=True)
                if not folder.is_dir():
                    raise DesktopError('المسار المحدد ليس مجلداً.')
                os.startfile(str(folder))
            except (OSError, ValueError):
                raise DesktopError('تعذر فتح المجلد في مستكشف الملفات. تحقق من وجوده وصلاحياته.') from None
            return {'ok': True, 'result': 'أُرسل طلب فتح المجلد إلى مستكشف الملفات. راقب الشاشة للتأكد من النتيجة.'}
