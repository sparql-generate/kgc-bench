"""The harness as a package for the workloads of other repositories: KGC_BENCH_ROOT, the
extension point of the workloads (harness.workloads.load_external), the scales a workload
gives, the normalised fingerprint (harness/ntnormalise.py)."""
import os
import subprocess
import sys

import pytest

from harness import ROOT
from harness import workloads as W


class Fake:
    def __init__(self, name):
        self.name = name
        self.default_scales = [2, 5]

    def job(self, scale, work):
        return {}


@pytest.fixture
def clean_all():
    saved = dict(W.ALL)
    yield
    W.ALL.clear()
    W.ALL.update(saved)


def test_env_module(tmp_path, monkeypatch, clean_all):
    (tmp_path / "extwl.py").write_text(
        "from tests.test_extension import Fake\n"
        "WORKLOADS = [Fake('ext-a'), Fake('ext-b')]\n"
        "def more():\n    return Fake('ext-c')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    added = W.load_external({"KGC_BENCH_WORKLOADS": "extwl, extwl:more"})
    assert added == ["ext-a", "ext-b", "ext-c"]
    assert W.ALL["ext-c"].name == "ext-c" and "gtfs" in W.ALL


def test_entry_points(monkeypatch, clean_all):
    import importlib.metadata as md

    class EP:
        def load(self):
            return lambda: [Fake("ep-a")]

    monkeypatch.setattr(md, "entry_points", lambda group: [EP()] if group == "kgc_bench.workloads" else [])
    assert W.load_external({}) == ["ep-a"]


def test_name_clash(clean_all):
    with pytest.raises(ValueError):
        W.ALL["ext-x"] = Fake("ext-x")
        import types
        mod = types.ModuleType("clash")
        mod.WORKLOADS = [Fake("ext-x")]
        sys.modules["clash"] = mod
        W.load_external({"KGC_BENCH_WORKLOADS": "clash"})


def test_default_scales_of_a_workload(tmp_path, clean_all):
    """harness.perf takes the scales a workload gives (default_scales)."""
    code = ("import sys; sys.path.insert(0, %r); sys.path.insert(0, %r)\n"
            "from harness import perf; print(perf.DEFAULT_SCALES['ext-a'])") % (str(tmp_path), ROOT)
    (tmp_path / "extwl2.py").write_text(
        "class F:\n    name = 'ext-a'\n    default_scales = [2, 5]\n    def job(self, s, w): return {}\n"
        "WORKLOADS = [F()]\n")
    env = dict(os.environ, KGC_BENCH_WORKLOADS="extwl2")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=ROOT)
    assert out.stdout.strip() == "[2, 5]", out.stderr[-500:]


def test_root_from_environment(tmp_path):
    """The engines, the suites and the pins of a checkout given by KGC_BENCH_ROOT."""
    (tmp_path / "versions.env").write_text(open(os.path.join(ROOT, "versions.env")).read())
    env = dict(os.environ, KGC_BENCH_ROOT=str(tmp_path))
    out = subprocess.run([sys.executable, "-c", "import harness; print(harness.ROOT, harness.ENGINES)"],
                         env=env, capture_output=True, text=True, cwd=ROOT)
    assert out.stdout.split() == [str(tmp_path), os.path.join(str(tmp_path), "engines")]


def test_ntnormalise():
    from harness import ntnormalise as N
    l = '<http://x/P%C3%A9rigord%20v%3Ab> <http://p> "0.000"^^<http://www.w3.org/2001/XMLSchema#double> .\n'
    assert N.line(l) == '<http://x/Périgord%20v%3Ab> <http://p> "0.0E0"^^<http://www.w3.org/2001/XMLSchema#double> .\n'
    assert N.line('<http://x/a> <http://p> "100%C3%A9" .\n') == '<http://x/a> <http://p> "100%C3%A9" .\n'
    assert [N.canonical_double(v) for v in ("150.0", "4.39", "45.40000", "1e-7", "-2", "x")] == \
        ["1.5E2", "4.39E0", "4.54E1", "1.0E-7", "-2.0E0", "x"]


def test_normalised_fingerprint(tmp_path):
    """Two outputs that differ only by the forms ntnormalise.py removes have one normalised
    fingerprint, and two without it."""
    from harness import rdfcompare as R
    if not os.path.exists(R.riot()):
        pytest.skip("Jena riot not installed")
    a, b = tmp_path / "a.nt", tmp_path / "b.nt"
    a.write_text('<http://x/Zo%C3%AB> <http://p> "1.50"^^<http://www.w3.org/2001/XMLSchema#double> .\n')
    b.write_text('<http://x/Zoë> <http://p> "1.5E0"^^<http://www.w3.org/2001/XMLSchema#double> .\n')
    assert R.digest(str(a))["sha256"] != R.digest(str(b))["sha256"]
    assert R.digest(str(a), normalise=True)["sha256"] == R.digest(str(b), normalise=True)["sha256"]


def test_external_module_imports_this_module(tmp_path):
    """An external module that imports names defined anywhere in harness.workloads (here
    to_rml_core, the last function) loads at import time: load_external runs last."""
    (tmp_path / "extwl3.py").write_text(
        "from harness.workloads import GTFS, to_rml_core\n"
        "class F(GTFS):\n    name = 'ext-late'\n"
        "WORKLOADS = [F()]\n")
    env = dict(os.environ, KGC_BENCH_WORKLOADS="extwl3",
               PYTHONPATH=os.pathsep.join([str(tmp_path), ROOT]))
    out = subprocess.run([sys.executable, "-c", "from harness import workloads as W; print('ext-late' in W.ALL)"],
                         env=env, capture_output=True, text=True, cwd=ROOT)
    assert out.stdout.strip() == "True", out.stderr[-800:]
