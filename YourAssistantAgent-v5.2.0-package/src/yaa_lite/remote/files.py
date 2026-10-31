"""Owner-selected local file area, with bounded uploads and streaming downloads."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import threading
import zipfile

MAX_TRANSFER = 256 * 1024 * 1024
MAX_ZIP_ENTRIES = 2000
MAX_ZIP_UNPACKED = 300 * 1024 * 1024
MAX_ZIP_MEMBER = 100 * 1024 * 1024


class FileError(ValueError):
    pass


class RemoteFiles:
    def __init__(self, root, *, all_drives=False, roots=None):
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise FileError('مجلد الملفات غير موجود.')
        self.all_drives = all_drives is True
        self.roots = {}
        self._mutation_lock = threading.RLock()
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
        if value.split('.')[0].rstrip(' ').upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
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

    def _mutation_path(self, relative, *, file=False):
        """Require an actual observed path, without following shortcut links."""
        root, inner, _ = self._area(relative)
        lexical = root.joinpath(*inner.split('/'))
        current = lexical
        while current != root:
            if current.is_symlink():
                raise FileError('المسار يحتوي رابطاً رمزياً؛ اختر الملف أو المجلد الأصلي.')
            current = current.parent
        return self.resolve(relative, file=file)

    @staticmethod
    def _relative_child(parent, name):
        return '/'.join(part for part in (parent.strip('/'), name) if part)

    def _destination(self, parent, name):
        directory = self._mutation_path(parent)
        if not directory.is_dir():
            raise FileError('اختر مجلد وجهة موجوداً من قائمة الملفات.')
        name = self.name(name)
        target = directory / name
        if target.exists() or target.is_symlink():
            raise FileError('يوجد ملف أو مجلد بنفس الاسم؛ اختر اسماً آخر. لم أستبدله.')
        return target, self._relative_child(parent, name)

    def create_folder(self, parent, name):
        with self._mutation_lock:
            target, relative = self._destination(parent, name)
            target.mkdir()
            return {'ok': True, 'path': relative, 'result': 'تم إنشاء المجلد: ' + relative}

    def copy_file(self, source, destination_folder, new_name=''):
        with self._mutation_lock:
            original = self._mutation_path(source, file=True)
            target, relative = self._destination(destination_folder, new_name or original.name)
            # import_file stages bytes and publishes the destination exclusively;
            # a failed copy never overwrites or leaves a partial visible file.
            self.import_file(original, destination_folder, target.name)
            return {'ok': True, 'path': relative, 'result': 'تم نسخ الملف إلى: ' + relative}

    def move_file(self, source, destination_folder, new_name=''):
        with self._mutation_lock:
            original = self._mutation_path(source, file=True)
            target, relative = self._destination(destination_folder, new_name or original.name)
            before = original.stat()
            self.import_file(original, destination_folder, target.name)
            # A source edited during a copy must remain intact. Keep the new
            # destination too so no completed copy is silently discarded.
            after = original.stat()
            if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                raise FileError('تغيّر المصدر أثناء النقل. احتفظت بالمصدر والنسخة الجديدة؛ راجعهما قبل المحاولة مجدداً.')
            try:
                original.unlink()
            except OSError as exc:
                raise FileError('تم نسخ الملف لكن تعذر إزالة المصدر؛ ما زالت النسختان موجودتين.') from exc
            return {'ok': True, 'path': relative, 'source': source, 'result': 'تم نقل الملف إلى: ' + relative}

    def extract_zip(self, path, destination_folder, new_name):
        """Extract into a new reviewed folder; never execute archive contents."""
        with self._mutation_lock:
            archive = self._mutation_path(path, file=True)
            if archive.stat().st_size > MAX_TRANSFER:
                raise FileError('حجم ZIP أكبر من 256 MiB.')
            target, relative = self._destination(destination_folder, new_name)
            temporary = None
            try:
                with zipfile.ZipFile(archive) as zipped:
                    members = zipped.infolist()
                    if not members or len(members) > MAX_ZIP_ENTRIES:
                        raise FileError('ZIP فارغ أو يحتوي أكثر من 2000 عنصر.')
                    validated = []
                    seen = {}
                    path_spellings = {}
                    unpacked = 0
                    for member in members:
                        raw = member.orig_filename
                        if not raw or raw.startswith('/') or '\\' in raw or '\x00' in raw:
                            raise FileError('ZIP يحتوي مساراً غير صالح.')
                        parts = raw.rstrip('/').split('/')
                        for part in parts:
                            self.name(part)
                        for size in range(1, len(parts) + 1):
                            spelling = '/'.join(parts[:size])
                            previous = path_spellings.setdefault(spelling.casefold(), spelling)
                            if previous != spelling:
                                raise FileError('ZIP يحتوي مسارات تختلف بحالة الأحرف فقط وتتعارض على Windows.')
                        mode = member.external_attr >> 16
                        kind = stat.S_IFMT(mode)
                        if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or member.flag_bits & 1:
                            raise FileError('ZIP يحتوي رابطاً أو عنصراً خاصاً أو ملفاً مشفراً غير مدعوم.')
                        directory = member.is_dir()
                        canonical = '/'.join(parts).casefold()
                        if canonical in seen:
                            raise FileError('ZIP يحتوي أسماء مكررة قد تتعارض على Windows.')
                        seen[canonical] = directory
                        unpacked += member.file_size
                        if member.file_size > MAX_ZIP_MEMBER or unpacked > MAX_ZIP_UNPACKED:
                            raise FileError('حجم الملفات بعد فك ZIP يتجاوز الحد المسموح.')
                        if member.file_size > 1024 * 1024 and member.file_size > max(1, member.compress_size) * 1000:
                            raise FileError('نسبة ضغط ZIP مرتفعة جداً. أعد ضغط الملفات دون ضغط شديد.')
                        validated.append((member, parts, directory))
                    for _, parts, _ in validated:
                        for size in range(1, len(parts)):
                            if seen.get('/'.join(parts[:size]).casefold()) is False:
                                raise FileError('ZIP يحتوي ملفاً ومجلداً بالمسار نفسه.')
                    temporary = Path(tempfile.mkdtemp(prefix='.yaa-extract-', dir=target.parent))
                    file_count = 0
                    for member, parts, directory in validated:
                        output = temporary.joinpath(*parts)
                        if directory:
                            output.mkdir(parents=True, exist_ok=True)
                            continue
                        output.parent.mkdir(parents=True, exist_ok=True)
                        written = 0
                        with zipped.open(member) as source, output.open('xb') as destination:
                            while block := source.read(65536):
                                written += len(block)
                                if written > member.file_size or written > MAX_ZIP_MEMBER:
                                    raise FileError('حجم أحد ملفات ZIP لا يطابق بياناته.')
                                destination.write(block)
                        if written != member.file_size:
                            raise FileError('ZIP غير مكتمل؛ لم يتم نشر مجلد فك الضغط.')
                        file_count += 1
                    self._publish_directory(temporary, target)
                    temporary = None
                    return {'ok': True, 'path': relative, 'files': file_count,
                            'result': f'تم فك {file_count} ملف داخل: {relative}'}
            except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:
                raise FileError('تعذر قراءة ZIP. تأكد أنه ملف سليم وغير مشفر.') from exc
            except OSError as exc:
                raise FileError('تعذر حفظ مجلد ZIP الجديد؛ افحص المساحة والصلاحيات أو اختر اسماً آخر.') from exc
            finally:
                if temporary is not None:
                    shutil.rmtree(temporary, ignore_errors=True)

    @staticmethod
    def _publish_directory(temporary, target):
        if os.name == 'nt':
            # Windows rename never replaces an existing destination.
            temporary.rename(target)
            return
        # Linux renameat2 preserves atomic folder publication AND refuses to
        # replace a concurrently created empty directory (plain rename does not).
        import ctypes
        import errno
        library = ctypes.CDLL(None, use_errno=True)
        rename = getattr(library, 'renameat2', None)
        if rename is not None:
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            rename.restype = ctypes.c_int
            if rename(-100, os.fsencode(temporary), -100, os.fsencode(target), 1) == 0:
                return
            error = ctypes.get_errno()
            if error not in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP}:
                raise FileError('تعذر نشر مجلد فك الضغط؛ قد توجد وجهة بنفس الاسم.') from OSError(error, os.strerror(error))
        raise FileError('نظام الملفات لا يدعم نشر المجلد دون استبدال؛ لم أكتب مجلد الوجهة.')
