"""The translation's time limit is set apart from the run's (KGC_BENCH_TRANSLATION_TIMEOUT)."""
import unittest
from unittest import mock

from harness import engines


class TranslationTimeout(unittest.TestCase):
    def test_default(self):
        with mock.patch.dict("os.environ", {}, clear=False) as env:
            env.pop("KGC_BENCH_TRANSLATION_TIMEOUT", None)
            self.assertEqual(engines.translation_timeout(), 600)

    def test_from_environment(self):
        with mock.patch.dict("os.environ", {"KGC_BENCH_TRANSLATION_TIMEOUT": "3600"}):
            self.assertEqual(engines.translation_timeout(), 3600)

    def test_passed_to_the_translation_run(self):
        seen = {}

        def run(*args, **kw):
            seen["timeout"] = kw["timeout"]
            return {"ok": False, "error": "stop"}

        with mock.patch.dict("os.environ", {"KGC_BENCH_TRANSLATION_TIMEOUT": "1234"}), \
                mock.patch.object(engines.sgcli, "run", run), \
                mock.patch.object(engines, "install_translator"), \
                mock.patch.object(engines.shutil, "copy"), \
                mock.patch.object(engines.os, "makedirs"):
            with self.assertRaises(RuntimeError):
                engines.translate_mapping({"rml_relative": "m.ttl", "rml_base": "http://b/"}, "/w", "sg-java-translated")
        self.assertEqual(seen["timeout"], 1234)


if __name__ == "__main__":
    unittest.main()
