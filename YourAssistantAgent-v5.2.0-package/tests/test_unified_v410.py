import tempfile
import unittest
from pathlib import Path
from yaa_lite.unified_v410 import SafeFilePlan, UnsafeOperation, TaskQueue, inventory_windows

class UnifiedTests(unittest.TestCase):
    def test_inventory_non_windows(self):
        if __import__('os').name != 'nt':
            self.assertEqual(inventory_windows(), [])

    def test_preview_and_apply_requires_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            stage, dest = root/'stage', root/'dest'
            stage.mkdir(); dest.mkdir()
            (stage/'a.txt').write_text('new')
            (dest/'a.txt').write_text('old')
            plan = SafeFilePlan(stage, dest, root)
            self.assertEqual(plan.preview()[0]['action'], 'replace')
            with self.assertRaises(PermissionError):
                plan.apply(authorized=False, backup_root=root/'backups')
            self.assertEqual((dest/'a.txt').read_text(), 'old')
            result = plan.apply(authorized=True, backup_root=root/'backups')
            self.assertEqual((dest/'a.txt').read_text(), 'new')
            self.assertTrue((Path(result['backup'])/'a.txt').exists())

    def test_block_secret_and_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); stage=root/'stage'; stage.mkdir()
            (stage/'.env').write_text('secret')
            with self.assertRaises(UnsafeOperation):
                SafeFilePlan(stage, root/'dest', root)

    def test_outside_root(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            with self.assertRaises(UnsafeOperation):
                SafeFilePlan(Path(a), Path(b), Path(a))

    def test_queue_no_worker_until_start(self):
        q = TaskQueue()
        self.assertIsNone(q.worker)
        q.stop()

if __name__ == '__main__':
    unittest.main()
