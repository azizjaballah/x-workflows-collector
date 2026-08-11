import builtins
import importlib
import sys
import unittest


class CollectorImportTests(unittest.TestCase):
    def test_authenticated_path_does_not_import_scrapling(self):
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "scrapling" or name.startswith("scrapling."):
                raise AssertionError("scrapling was imported eagerly")
            return original_import(name, *args, **kwargs)

        sys.modules.pop("x_workflows_collector.collector", None)
        builtins.__import__ = guarded_import
        try:
            collector = importlib.import_module("x_workflows_collector.collector")
        finally:
            builtins.__import__ = original_import

        self.assertEqual(collector.normalize_handle("@sans_isc"), "sans_isc")


if __name__ == "__main__":
    unittest.main()
