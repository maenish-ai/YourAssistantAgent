from pathlib import Path
import tempfile
import unittest
import zipfile
from yaa_lite.attachments_v420 import candidate_repo, inspect_files, summary, validate_files

class AttachmentTests(unittest.TestCase):
    def test_repository_suggestion(self):
        self.assertEqual(candidate_repo('Your Assistant Agent PATCH.zip'), 'maenish-ai/YourAssistantAgent')
        self.assertIsNone(candidate_repo('invoice.pdf'))
    def test_text_preview(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'notes.txt'; p.write_text('hello', encoding='utf-8')
            item = inspect_files([str(p)])[0]
            self.assertEqual(item['preview'], 'hello')
            self.assertIn('notes.txt', summary([item]))
    def test_zip_metadata_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'patch.zip'
            with zipfile.ZipFile(p,'w') as z: z.writestr('src/yaa_lite/demo.py','hello')
            item=inspect_files([str(p)])[0]
            self.assertEqual(item['repo'], 'maenish-ai/YourAssistantAgent')
    def test_limit(self):
        with self.assertRaises(ValueError): validate_files(['missing']*21)
if __name__=='__main__': unittest.main()
