import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("select_plume", Path(__file__).parents[1] / "select-plume.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PlumeSelectionTests(unittest.TestCase):
    def dockerfile(self, tag):
        return f"https://github.com/bitxeno/PlumeImpactor/releases/download/{tag}/plumesign.tar.gz"

    def test_reviewed_stable_base_uses_authentication_candidate(self):
        self.assertEqual(module.select("v0.7.3", self.dockerfile("v2.7.1-patch.3")), "v2.7.1-patch.4")

    def test_future_upstream_dependency_is_not_downgraded(self):
        self.assertEqual(module.select("v0.7.4", self.dockerfile("v2.8.0-patch.1")), "v2.8.0-patch.1")

    def test_changed_dependency_on_same_base_is_respected(self):
        self.assertEqual(module.select("v0.7.3", self.dockerfile("v2.7.1-patch.5")), "v2.7.1-patch.5")

    def test_missing_upstream_dependency_fails_build(self):
        with self.assertRaises(ValueError):
            module.select("v0.7.3", "no engine tag")
