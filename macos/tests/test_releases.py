import importlib.util, pathlib, unittest
spec = importlib.util.spec_from_file_location('releases', pathlib.Path(__file__).parents[1]/'releases.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
class Releases(unittest.TestCase):
    def test_order(self):
        self.assertEqual(r.latest([{'tag_name':'v0.9.9'},{'tag_name':'v0.10.0'},{'tag_name':'v1.0.0','prerelease':True},{'tag_name':'v3.0.0','draft':True}]), 'v0.10.0')
    def test_reject_unstable(self):
        for tag in ('v1.0.0-rc.1','latest','v01.0.0','v1.2','1.2.3+build'):
            self.assertIsNone(r.version(tag))
    def test_empty_fails_closed(self):
        with self.assertRaises(ValueError): r.latest([])
if __name__ == '__main__': unittest.main()
