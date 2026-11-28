"""harness.perf.drop_short_outputs: runs whose lines were not counted are timings."""
import unittest

from harness.perf import drop_short_outputs


def run(lines, wall):
    return {"status": "ok", "lines": lines, "wall_s": wall}


class ShortOutputs(unittest.TestCase):
    def test_uncounted_runs_are_kept(self):
        row = {"note": ""}
        ok = drop_short_outputs([run(454661, 2.0)] + [run(None, w) for w in (1.8, 1.9, 1.7, 2.1)], row)
        self.assertEqual(len(ok), 5)
        self.assertEqual(row["note"], "")

    def test_a_short_counted_run_is_dropped(self):
        row = {"note": ""}
        ok = drop_short_outputs([run(100, 1.0), run(40, 0.5), run(None, 1.1)], row)
        self.assertEqual([r["wall_s"] for r in ok], [1.0, 1.1])
        self.assertIn("unstable output", row["note"])

    def test_nothing_counted(self):
        self.assertEqual(len(drop_short_outputs([run(None, 1.0), run(None, 2.0)], {"note": ""})), 2)


if __name__ == "__main__":
    unittest.main()
