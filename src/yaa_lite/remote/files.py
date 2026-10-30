"""Owner-selected local file area, with bounded uploads and streaming downloads."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import tempfile

MAX_TRANSFER = 256 * 1024 * 1024


class FileError(ValueError):
    pass


class RemoteFiles:
    def __init__(self, root, *, all_drives=False, roots=None):
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise FileError('مجلد الملفات غير موجود.')
        self.all_drives = all_drives is True
        self.roots = {}
        if self.all_drives:
            if roots is None:
                roots = {}
                if os.name == 'nt':
                    import ctypes
                    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                    kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
                    kernel.GetDriveTypeW.restype = ctypes.c_uint
                    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                        drive = letter + ':\\'
                        if kernel.GetDriveTypeW(drive) in (2, 3):
                            roots[letter] = Path(drive)
            for label, path in roots.items():
                if not re.fullmatch('[A-Z]', label):
                    raise FileError('معرّف قرص غير صالح.')
                try:
                    area = Path(path).resolve(strict=True)
                    if area.is_dir(): self.roots[label] = area
                except OSError:
                    # An empty removable reader must not disable the companion.
                    continue

    def _area(self, relative):
        if not isinstance(relative, str) or '\x00' in relative or '\\' in relative or ':' in relative:
            raise FileError('مسار غير صالح.')
        if relative.startswith('/') or '..' in relative.split('/'):
            raise FileError('المسار خارج مجلد المشاركة.')
        if self.all_drives:
            parts = relative.split('/')
            if len(parts) < 2 or parts[0] != '@drives' or parts[1] not in self.roots:
                raise FileError('اختر قرصاً من قائمة الكمبيوتر أولاً.')
            return self.roots[parts[1]], '/'.join(parts[2:]), '@drives/' + parts[1]
        return self.root, relative, ''

    def resolve(self, relative='', *, file=False):
        root, inner, _ = self._area(relative)
        path = root.joinpath(*inner.split('/')).resolve(strict=True)
        if not path.is_relative_to(root):
            raise FileError('المسار خارج مجلد المشاركة.')
        if file and not path.is_file():
            raise FileError('الملف غير موجود.')
        return path

    def listing(self, relative=''):
        if self.all_drives and relative in ('', '@drives'):
            return {'path': '', 'root_name': 'الكمبيوتر', 'display_path': 'الكمبيوتر', 'can_upload': False, 'limit': 1000,
                    'entries': [{'name': key + ':', 'path': '@drives/' + key,
                                 'directory': True, 'size': 0} for key in sorted(self.roots)]}
        root, _, prefix = self._area(relative)
        path = self.resolve(relative)
        if not path.is_dir():
            raise FileError('اختر مجلداً.')
        entries = []
        for item in path.iterdir():
            if len(entries) >= 1000:
                break
            try:
                resolved = item.resolve(strict=True)
                if not resolved.is_relative_to(root):
                    continue
                entries.append({'name': item.name, 'path': '/'.join(p for p in (prefix, item.relative_to(root).as_posix()) if p),
                                'directory': item.is_dir(), 'size': item.stat().st_size if item.is_file() else 0})
            except OSError:
                continue
        entries.sort(key=lambda e: (not e['directory'], e['name'].casefold()))
        inner = '' if path == root else path.relative_to(root).as_posix()
        return {'path': '/'.join(p for p in (prefix, inner) if p), 'can_upload': True,
                'display_path': (prefix.split('/')[-1] + ':\\' + inner.replace('/', '\\')) if self.all_drives else str(path),
                'entries': entries, 'root_name': 'الكمبيوتر' if self.all_drives else (root.name or str(root)), 'limit': 1000}

    @staticmethod
    def name(value):
        if not isinstance(value, str) or not 1 <= len(value) <= 180 or value in {'.', '..'} or re.search(r'[\\/:*?"<>|\x00-\x1f]', value) or value.endswith((' ', '.')):
            raise FileError('اسم الملف غير صالح.')
        if value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
            raise FileError('اسم الملف محجوز في Windows.')
        return value

    def import_file(self, source, folder, name):
        directory = self.resolve(folder)
        target = directory / self.name(name)
        if not directory.is_dir() or target.exists() or target.is_symlink():
            raise FileError('يوجد ملف بنفس الاسم أو المجلد غير صالح. غيّر الاسم أولاً.')
        if Path(source).stat().st_size > MAX_TRANSFER:
            raise FileError('حجم الملف أكبر من 256 MiB.')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, prefix='.yaa-upload-', delete=False) as output:
                temporary = Path(output.name)
                with Path(source).open('rb') as input_file:
                    shutil.copyfileobj(input_file, output, 65536)
            # Windows rename refuses an existing destination and works on FAT
            # as well as NTFS. POSIX rename would replace it, so use an atomic
            # exclusive hard-link there instead.
            if os.name == 'nt':
                os.rename(temporary, target)
            else:
                os.link(temporary, target)
            return {'ok': True, 'path': '/'.join(p for p in (folder.strip('/'), target.name) if p)}
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
