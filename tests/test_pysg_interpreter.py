"""The interpreter that runs the exported pysparql-generate (harness.engines.pysg_python):
KGC_BENCH_PYSG_PYTHON when set, else the harness's Python if its DuckDB satisfies the
export, else the venv of REPRODUCE.md, else the harness's with a clear problem; and the
conformance harness stops at once when that interpreter cannot run the export. No
engine is run.

    python -m unittest tests.test_pysg_interpreter
"""

import unittest
from unittest import mock


def setUpModule():
    global engines
    from harness import engines


class PysgPython(unittest.TestCase):

    def setUp(self):
        self.saved = (list(engines._PYSG_PY), dict(engines._PYSG_CHECKED), engines.PYSG_PY_ENV)
        engines._PYSG_PY.clear()

    def tearDown(self):
        engines._PYSG_PY[:] = self.saved[0]
        engines._PYSG_CHECKED.clear()
        engines._PYSG_CHECKED.update(self.saved[1])
        engines.PYSG_PY_ENV = self.saved[2]

    def checked(self, harness_ok, reproduce_ok):
        engines.PYSG_PY_ENV = None
        engines._PYSG_CHECKED[engines.PY] = "" if harness_ok else "duckdb 1.5.6"
        engines._PYSG_CHECKED[engines.PYSG_PY_REPRODUCE] = "" if reproduce_ok else "duckdb 1.5.6"

    def test_environment_first(self):
        self.checked(True, True)
        engines.PYSG_PY_ENV = "/opt/py/bin/python"
        self.assertEqual(engines.pysg_python(), "/opt/py/bin/python")

    def test_harness_python_when_its_duckdb_suffices(self):
        self.checked(True, True)
        self.assertEqual(engines.pysg_python(), engines.PY)

    def test_reproduce_venv_when_only_it_suffices(self):
        self.checked(False, True)
        with mock.patch("os.path.exists", return_value=True):
            self.assertEqual(engines.pysg_python(), engines.PYSG_PY_REPRODUCE)
        self.assertEqual(engines.pysg_interpreter_problem(), "")

    def test_clear_failure_when_none_suffices(self):
        self.checked(False, False)
        with mock.patch("os.path.exists", return_value=True):
            self.assertEqual(engines.pysg_python(), engines.PY)
        self.assertIn("duckdb", engines.pysg_interpreter_problem())
        with self.assertRaises(SystemExit) as e:
            engines.require_pysg_interpreter()
        self.assertIn("pysparql-generate", str(e.exception))


if __name__ == "__main__":
    unittest.main()
