import tempfile
import unittest
import zipfile
from pathlib import Path
from yaa_lite.smart_actions_v310 import Workspace, ActionError, PinVault, ApprovalGate, LearningPreferences

class SmartActionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = Workspace([self.root], self.root / 'stage')

    def test_zip_stage_and_diff(self):
        archive = self.root / 'update.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('folder/a.txt', 'new')
            z.writestr('.env', 'TOPSECRET')
        result = self.workspace.stage_zip(archive)
        diff = self.workspace.compare(Path(result['staging']), self.root / 'project')
        self.assertEqual(diff['added'], ['folder/a.txt'])
        self.assertEqual(diff['blocked'], ['.env'])
        self.assertFalse((self.root / 'project').exists())

    def test_zip_traversal_blocked(self):
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('../escape.txt', 'bad')
        with self.assertRaises(ActionError):
            self.workspace.stage_zip(archive)
        self.assertFalse((self.root / 'escape.txt').exists())

    def test_workspace_boundary(self):
        with self.assertRaises(ActionError):
            self.workspace.check(self.root.parent / 'other')

    def test_pin_bound_one_time(self):
        vault = PinVault(self.root / 'private' / 'pin.json')
        vault.enroll('123456')
        gate = ApprovalGate(vault)
        gate.request('git_push', {'repo': 'A', 'branch': 'main'})
        self.assertFalse(gate.authorize('git_push', {'repo': 'B', 'branch': 'main'}, '123456'))
        self.assertFalse(gate.authorize('git_push', {'repo': 'A', 'branch': 'main'}, '000000'))
        self.assertTrue(gate.authorize('git_push', {'repo': 'A', 'branch': 'main'}, '123456'))
        self.assertFalse(gate.authorize('git_push', {'repo': 'A', 'branch': 'main'}, '123456'))

    def test_learning_requires_confirmation(self):
        store = LearningPreferences(self.root / 'memory.json')
        with self.assertRaises(ActionError):
            store.remember('default_repo', 'example')
        store.remember('default_repo', 'example', confirmed=True)
        self.assertEqual(store.read()['default_repo'], 'example')
        store.forget('default_repo')
        self.assertEqual(store.read(), {})

if __name__ == '__main__':
    unittest.main()
