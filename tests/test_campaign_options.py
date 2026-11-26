"""Tests of the campaign options for a dedicated machine: the public progress log
(KGC_BENCH_PUBLIC_LOG), the CPU list (KGC_BENCH_CPUS), memory limits of 24G, and a
time limit by scale (--timeout-at, LIMIT_TIME_S_AT).

    python -m unittest discover tests
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

os.environ["KGC_BENCH_SLICE"] = "agents-kgcbenchtest.slice"

from harness import perf, publiclog, sandbox  # noqa: E402

HAVE_SCOPES = shutil.which("systemd-run") is not None and subprocess.run(
    ["systemd-run", "--user", "--scope", "-q", "true"], capture_output=True).returncode == 0


class PublicLog(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.path = os.path.join(self.d, "benchmark.log")
        os.environ["KGC_BENCH_PUBLIC_LOG"] = self.path

    def tearDown(self):
        os.environ.pop("KGC_BENCH_PUBLIC_LOG", None)
        shutil.rmtree(self.d)

    def test_lines_appended_without_paths(self):
        publiclog.event(campaign="c1", event="run", workload="gtfs", scale=10, engine="sg-java",
                        status="ok", median_s=8.67, mem_mb=3226.0, note="/home/someone/x y")
        publiclog.event(campaign="c1", event="campaign-end")
        lines = open(self.path).read().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("campaign=c1 event=run workload=gtfs scale=10 engine=sg-java status=ok "
                      "median_s=8.67 mem_mb=3226.0", lines[0])
        self.assertNotIn("/", lines[0].split(" ", 1)[1])
        self.assertNotIn(" y", lines[0])
        self.assertIn("load=", lines[1])
        publiclog.main(["campaign=c1", "event=step-start", "step=perf-gtfs"])
        self.assertEqual(len(open(self.path).read().splitlines()), 3)

    def test_unset_writes_nothing(self):
        os.environ.pop("KGC_BENCH_PUBLIC_LOG")
        publiclog.event(event="run")
        self.assertFalse(os.path.exists(self.path))


class TimeLimits(unittest.TestCase):
    def test_by_scale(self):
        args = SimpleNamespace(timeout=600, timeout_at=["1000=3600"])
        self.assertEqual(perf.time_limit(args, 100), 600)
        self.assertEqual(perf.time_limit(args, 1000), 3600)
        self.assertEqual(perf.time_limit(SimpleNamespace(timeout=600), 1000), 600)

    def test_viability_against_the_row_limit(self):
        row = {"status": "ok", "wall_s": "2000", "rss_mb": "100", "mem_cap": "16G"}
        self.assertEqual(perf.viability(dict(row)), "time")
        self.assertEqual(perf.viability(dict(row, time_limit_s="3600")), "")


class Translation(unittest.TestCase):
    def test_columns(self):
        self.assertEqual(perf.translation_columns([3.1, 2.9, 3.4]),
                         {"translation_s": 3.1, "translation_min_s": 2.9, "translation_max_s": 3.4})
        self.assertEqual(perf.translation_columns([])["translation_s"], "")

    def test_row_or_old_note(self):
        self.assertEqual(perf.row_translation_s({"translation_s": "2.5"}), 2.5)
        self.assertEqual(perf.row_translation_s({"note": "translation 3.06s (untimed) x"}), 3.06)
        self.assertIsNone(perf.row_translation_s({"note": ""}))

    def test_report_shows_the_total(self):
        from harness import report
        rows = [{"workload": "gtfs", "scale": "1", "engine": "sg-java-translated", "status": "ok",
                 "wall_s": "3.0", "rss_mb": "800", "triples": "10", "equivalent": "yes",
                 "mem_cap": "16G", "note": "translation 2.00s (untimed)", "version": "v"}]
        md = "\n".join(report.perf_md(rows, []))
        self.assertIn("3.0s + 2.00s = 5.00s", md)


class MemCap24(unittest.TestCase):
    def test_heap_of_24g(self):
        old = os.environ.get("KGC_BENCH_MEM_CAP")
        os.environ["KGC_BENCH_MEM_CAP"] = "24G"
        try:
            self.assertEqual(perf.default_xmx(), "18432m")
        finally:
            if old is None:
                os.environ.pop("KGC_BENCH_MEM_CAP")
            else:
                os.environ["KGC_BENCH_MEM_CAP"] = old

    @unittest.skipUnless(HAVE_SCOPES, "no systemd user session")
    def test_scope_of_24g(self):
        r = sandbox.run(["sh", "-c", "cat /sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)/memory.max"],
                        30, mem_cap="24G")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(int(r["stdout"].strip()), 24 * 2**30)


class Cpus(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("KGC_BENCH_CPUS", None)

    def test_affinity(self):
        os.environ["KGC_BENCH_CPUS"] = "0"
        self.assertEqual(sandbox.affinity(["x"])[:3], ["taskset", "-c", "0"])
        os.environ["KGC_BENCH_CPUS"] = "0; rm"
        self.assertRaises(ValueError, sandbox.affinity, ["x"])
        os.environ.pop("KGC_BENCH_CPUS")
        self.assertEqual(sandbox.affinity(["x"]), ["x"])

    @unittest.skipUnless(HAVE_SCOPES and shutil.which("taskset"), "no systemd scope or taskset")
    def test_engine_runs_on_the_cpus(self):
        os.environ["KGC_BENCH_CPUS"] = "0"
        r = sandbox.run(["sh", "-c", "grep Cpus_allowed_list /proc/self/status"], 30, mem_cap="1G")
        self.assertIn("\t0", r["stdout"])


if __name__ == "__main__":
    unittest.main()
