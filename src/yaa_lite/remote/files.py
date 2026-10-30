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
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise FileError('مجلد الملفات غير موجود.')

    def resolve(self, relative='', *, file=False):
        if not isinstance(relative, str) or '\x00' in relative or '\\' in relative or ':' in relative:
            raise FileError('مسار غير صالح.')
        parts = relative.split('/')
        if relative.startswith('/') or any(p == '..' for p in parts):
            raise FileError('المسار خارج مجلد المشاركة.')
        path = self.root.joinpath(*parts).resolve(strict=True)
        if not path.is_relative_to(self.root):
            raise FileError('المسار خارج مجلد المشاركة.')
        if file and not path.is_file():
            raise FileError('الملف غير موجود.')
        return path

    def listing(self, relative=''):
        path = self.resolve(relative)
        if not path.is_dir():
            raise FileError('اختر مجلداً.')
        entries = []
        for item in path.iterdir():
            if len(entries) >= 1000:
                break
            try:
                resolved = item.resolve(strict=True)
                if not resolved.is_relative_to(self.root):
                    continue
                entries.append({'name': item.name, 'path': item.relative_to(self.root).as_posix(),
                                'directory': item.is_dir(), 'size': item.stat().st_size if item.is_file() else 0})
            except OSError:
                continue
        entries.sort(key=lambda e: (not e['directory'], e['name'].casefold()))
        return {'path': '' if path == self.root else path.relative_to(self.root).as_posix(),
                'entries': entries, 'root_name': self.root.name or str(self.root), 'limit': 1000}

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
            return {'ok': True, 'path': target.relative_to(self.root).as_posix()}
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
