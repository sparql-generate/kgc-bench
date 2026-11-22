"""Tests of harness.sandbox: every process in a memory-capped systemd scope.

    python -m unittest discover tests

They need a systemd user session (skipped otherwise) and start a few tiny
processes; none takes more than a few seconds.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

# a slice of their own: the tests' small caps must not become the budget of
# the benchmark's slice
os.environ["KGC_BENCH_SLICE"] = "agents-kgcbenchtest.slice"
os.environ.pop("KGC_BENCH_MEM_TOTAL", None)

from harness import sandbox  # noqa: E402

HAVE_SCOPES = shutil.which("systemd-run") is not None and subprocess.run(
    ["systemd-run", "--user", "--scope", "-q", "true"], capture_output=True).returncode == 0
PY = sys.executable


@unittest.skipUnless(HAVE_SCOPES, "no systemd user session")
class SandboxTest(unittest.TestCase):

    def test_ok_reports_peak_rss(self):
        r = sandbox.run([PY, "-c", "x = bytearray(50 * 2**20); x[::4096] = b'a' * len(x[::4096])"],
                        30, mem_cap="512M")
        self.assertEqual(r["status"], "ok")
        self.assertGreater(r["rss_mb"], 50)
        self.assertEqual(r["mem_cap"], "512M")

    def test_error_status(self):
        r = sandbox.run([PY, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"], 30,
                        mem_cap="512M")
        self.assertEqual((r["status"], r["returncode"]), ("error", 3))
        self.assertIn("boom", r["stderr"])

    def test_over_the_cap_is_oom_with_rss(self):
        r = sandbox.run([PY, "-c", "x = bytearray(400 * 2**20); x[::4096] = b'a' * len(x[::4096])"],
                        30, mem_cap="64M")
        self.assertEqual(r["status"], "oom")
        self.assertIsNotNone(r["rss_mb"])   # /usr/bin/time outlived the engine

    def test_timeout_kills_the_whole_tree(self):
        tag = "kgcb-test-%d" % os.getpid()
        t0 = time.time()
        r = sandbox.run(["sh", "-c", "sleep 300 & sleep 300 & exec -a %s sleep 300" % tag], 1,
                        mem_cap="64M")
        self.assertEqual(r["status"], "timeout")
        self.assertLess(time.time() - t0, 30)
        time.sleep(0.5)
        left = subprocess.run(["pgrep", "-f", tag], capture_output=True, text=True).stdout
        self.assertEqual(left.strip(), "")

    def test_under_agents_slice_with_oom_score(self):
        r = sandbox.run(["sh", "-c", "cat /proc/self/oom_score_adj; cat /proc/self/cgroup"], 30,
                        mem_cap="64M")
        self.assertIn("/agents.slice/agents-kgcbenchtest.slice/", r["stdout"])
        if sandbox.CHOOM:
            self.assertEqual(r["stdout"].split()[0], "1000")

    def test_stdout_to_file(self):
        with tempfile.TemporaryFile("w+") as f:
            r = sandbox.run(["echo", "hello"], 30, mem_cap="64M", stdout=f)
            f.seek(0)
            self.assertEqual((r["status"], f.read()), ("ok", "hello\n"))


@unittest.skipUnless(HAVE_SCOPES, "no systemd user session")
class SliceTest(unittest.TestCase):

    def test_a_small_cap_does_not_lower_the_slice(self):
        sandbox.run(["true"], 30, mem_cap="512M")       # the slice gets a cap
        before = sandbox.slice_cap()
        sandbox._slice_cap = None                         # as a second command would
        sandbox.setup("64M")
        self.assertEqual(sandbox.slice_cap(), before)


class CapTest(unittest.TestCase):

    def test_resolve(self):
        self.assertIsNone(sandbox.resolve("none"))
        self.assertEqual(sandbox.resolve("24g"), "24G")
        self.assertEqual(sandbox.to_bytes("1.5G"), int(1.5 * 2**30))
        with self.assertRaises(ValueError):
            sandbox.resolve("lots")

    def test_uncapped_runs_plainly(self):
        r = sandbox.run(["true"], 30, mem_cap="none")
        self.assertEqual((r["status"], r["mem_cap"], r["unit"]), ("ok", "none", None))


if __name__ == "__main__":
    unittest.main()
