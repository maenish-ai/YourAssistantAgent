import unittest
from unittest.mock import patch
from yaa_lite.windows_discovery_v400 import discover_apps, describe_apps

class DiscoveryTests(unittest.TestCase):
    def test_no_windows_no_scan(self):
        with patch('yaa_lite.windows_discovery_v400.os.name', 'posix'):
            self.assertEqual(discover_apps(), [])
    def test_describe_does_not_grant_access(self):
        text = describe_apps([{'name': 'Word', 'source': 'installed'}])
        self.assertIn('Word', text)
        self.assertIn('لا يمنح', text)
if __name__ == '__main__':
    unittest.main()
