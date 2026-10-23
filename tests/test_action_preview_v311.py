import tempfile
import unittest
import zipfile
from pathlib import Path
from yaa_lite.action_preview_v311 import preview_zip, describe_diff


class PreviewTests(unittest.TestCase):
    def test_preview_is_read_only_and_paths_are_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / 'project'
            dest.mkdir()
            (dest / 'old.txt').write_text('before')
            archive = root / 'patch.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('old.txt', 'after')
                z.writestr('folder/new.txt', 'new')
                z.writestr('.env', 'SECRET')
            diff = preview_zip(archive, dest, root / 'AssistantWorkspace')
            self.assertEqual(diff['changed'], ['old.txt'])
            self.assertEqual(diff['added'], ['folder/new.txt'])
            self.assertEqual(diff['blocked'], ['.env'])
            self.assertEqual((dest / 'old.txt').read_text(), 'before')
            self.assertFalse((dest / 'folder').exists())
            self.assertIn('بدون تعديل', describe_diff(diff))

    def test_unsafe_zip_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('../escape.txt', 'bad')
            with self.assertRaises(Exception):
                preview_zip(archive, root / 'project', root / 'AssistantWorkspace')
            self.assertFalse((root / 'escape.txt').exists())
