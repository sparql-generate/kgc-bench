"""A public progress log of the campaigns (KGC_BENCH_PUBLIC_LOG=<file>): one short line
per event, appended, never truncated, each line written by one write(2) on a file
opened with O_APPEND (atomic for lines this short). The file is meant to be served
publicly: a line holds the time, the campaign, the step and facts (load, scale,
engine, status, median time, peak memory), never a path, a user or a host name.

    2026-11-27T01:31:02+01:00 campaign=2026-11-27-table4 event=run workload=gtfs scale=10 engine=sg-java status=ok median_s=8.67 mem_mb=3226 load=0.42

``python -m harness.publiclog key=value ...`` writes a line (scripts/campaign.sh,
night.sh).
"""

import datetime
import os
import re
import sys

KEYS_ORDER = ("campaign", "event", "step", "workload", "scale", "engine", "status",
              "median_s", "mem_mb", "load", "note")
_SAFE = re.compile(r"[^A-Za-z0-9._:+=,()<>-]")


def _clean(value):
    """One token, without spaces, slashes or anything that could be a path."""
    v = str(value).strip()
    v = v.replace("/", "_").replace("\\", "_")
    return _SAFE.sub("_", v)[:80]


def line(**fields):
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    keys = [k for k in KEYS_ORDER if k in fields] + sorted(k for k in fields if k not in KEYS_ORDER)
    parts = ["%s=%s" % (k, _clean(fields[k])) for k in keys if fields[k] not in (None, "")]
    return now + " " + " ".join(parts) + "\n"


def event(**fields):
    """Append one line to KGC_BENCH_PUBLIC_LOG, if set; never raises."""
    path = os.environ.get("KGC_BENCH_PUBLIC_LOG")
    if not path:
        return
    fields.setdefault("campaign", os.environ.get("KGC_BENCH_CAMPAIGN", ""))
    if "load" not in fields:
        try:
            fields["load"] = open("/proc/loadavg").read().split()[0]
        except OSError:
            pass
    data = line(**fields).encode("utf-8")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
    except OSError:
        pass


def main(argv=None):
    fields = {}
    for a in (argv if argv is not None else sys.argv[1:]):
        k, _, v = a.partition("=")
        fields[k] = v
    event(**fields)
    return 0


if __name__ == "__main__":
    sys.exit(main())
