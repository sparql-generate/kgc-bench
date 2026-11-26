"""Every process that the harness starts runs in a memory-capped transient
systemd scope, so that no engine can exhaust the machine.

    systemd-run --user --scope --slice=agents-kgcbench.slice
                -p MemoryMax=<cap> -p MemorySwapMax=0 -p OOMPolicy=continue
                choom -n 1000 -- /usr/bin/time -v -o <report> <command>

- the scope puts the process tree in a cgroup of its own: ``MemoryMax`` caps
  it (page cache included, which the kernel reclaims first), and
  ``MemorySwapMax=0`` forbids swapping, so that an engine that outgrows the
  cap is killed at once by the kernel instead of thrashing the machine (and
  setting systemd-oomd off on the whole user session);
- ``OOMPolicy=continue`` keeps the scope alive when the engine is killed:
  ``/usr/bin/time -v``, inside it, outlives the engine and still reports its
  peak resident memory;
- every scope is placed in one slice, ``agents-kgcbench.slice``, whose own
  ``MemoryMax`` bounds the sum of the processes run in parallel (the
  conformance harness runs several at once, and several harness commands may
  run side by side); its name puts it under ``agents.slice``, which, on a
  machine shared with other jobs, bounds the sum of all of them (elsewhere
  systemd creates it without a limit);
- the OOM score of the command is raised to 1000 (``choom``): if the kernel
  runs out of memory anyway, it kills the engine, not the desktop;
- a run over its time budget has its whole scope killed (``systemctl --user
  kill``), with every process the engine started.

A run killed by the cap has the status ``oom``. The cap is the ``--mem-cap``
option of each harness command, else ``KGC_BENCH_MEM_CAP``, else 16G. The
slice cap is set by ``KGC_BENCH_MEM_TOTAL``; without it, a slice that has no
cap yet gets 20G, and a slice that has one keeps it (a command with a small
per-process cap never lowers the budget of a campaign running beside it).
``none`` disables the scopes (an engine can then exhaust the machine).

``python -m harness.sandbox [--mem-cap 24G] -- command ...`` runs any command
under the same cap (builds, ad hoc runs).
"""

import argparse
import itertools
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

DEFAULT_CAP = "16G"      # the memory limit of one run: over it, not viable
DEFAULT_TOTAL = "20G"
SLICE = os.environ.get("KGC_BENCH_SLICE", "agents-kgcbench.slice")
CHOOM = ["choom", "-n", "1000", "--"] if shutil.which("choom") else []
_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMGT]?)i?B?\s*$", re.I)
_counter = itertools.count()
_lock = threading.Lock()
_slice_cap = None
_slice_cgroup = None


class CapError(RuntimeError):
    """The memory cap cannot be applied on this machine."""


def resolve(cap=None):
    """The cap in force: the argument, else KGC_BENCH_MEM_CAP, else 16G;
    None when disabled ("none")."""
    v = cap or os.environ.get("KGC_BENCH_MEM_CAP") or DEFAULT_CAP
    if str(v).lower() in ("none", "off", "0"):
        return None
    to_bytes(v)  # validates
    return str(v).upper().replace("IB", "").replace("B", "")


def to_bytes(size):
    m = _SIZE.match(str(size))
    if not m:
        raise ValueError("not a memory size: %r (e.g. 24G, 512M)" % size)
    return int(float(m.group(1)) * 1024 ** "BKMGT".index((m.group(2) or "B").upper()))


def _total(cap):
    return resolve(os.environ.get("KGC_BENCH_MEM_TOTAL")) or cap


def setup(cap):
    """Make sure the slice exists with a cap on the sum of its processes; once
    per process. The slice is shared by every harness command running at the
    same time: its cap is set from KGC_BENCH_MEM_TOTAL when that is given, or
    to DEFAULT_TOTAL when the slice has none yet, and is otherwise left as it is (a
    command with a small per-process cap must not lower the budget of a
    campaign running beside it). Raises CapError when systemd cannot cap
    memory here."""
    global _slice_cap, _slice_cgroup
    with _lock:
        if _slice_cap is not None:
            return
        if not shutil.which("systemd-run"):
            raise CapError("systemd-run not found: cannot cap memory "
                           "(--mem-cap none to run uncapped)")
        explicit = resolve(os.environ.get("KGC_BENCH_MEM_TOTAL")) if os.environ.get(
            "KGC_BENCH_MEM_TOTAL") else None
        current = subprocess.run(["systemctl", "--user", "show", "-p", "MemoryMax", "--value",
                                  SLICE], capture_output=True, text=True).stdout.strip()
        total = explicit or (DEFAULT_TOTAL if current in ("", "infinity") else None)
        if total:
            r = subprocess.run(["systemctl", "--user", "set-property", "--runtime", SLICE,
                                "MemoryMax=" + total, "MemorySwapMax=0"],
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise CapError("cannot set the cap of %s: %s" % (SLICE, r.stderr.strip()))
        r = subprocess.run(["systemctl", "--user", "show", "-p", "ControlGroup", "--value",
                            SLICE], capture_output=True, text=True)
        _slice_cgroup = r.stdout.strip() or None
        _slice_cap = total or current


def slice_cap():
    """The cap of the slice in force (bytes, or 'infinity')."""
    return subprocess.run(["systemctl", "--user", "show", "-p", "MemoryMax", "--value", SLICE],
                          capture_output=True, text=True).stdout.strip()


def unit_name():
    return "kgcb-%d-%d-%d" % (os.getpid(), next(_counter), int(time.time() * 1000) % 10**6)


def cpus():
    """KGC_BENCH_CPUS (a CPU list, e.g. 2-11): the CPUs the engines run on (taskset), so
    that the others stay free for the services of the machine; None: all."""
    v = os.environ.get("KGC_BENCH_CPUS", "").strip()
    if v and not re.fullmatch(r"[0-9,\-]+", v):
        raise ValueError("KGC_BENCH_CPUS: not a CPU list: %r" % v)
    return v or None


def affinity(cmd):
    """cmd run on the CPUs of KGC_BENCH_CPUS, if set."""
    c = cpus()
    return (["taskset", "-c", c] + list(cmd)) if c and shutil.which("taskset") else list(cmd)


def wrap(cmd, cap, unit):
    """The command line that runs cmd in a capped scope named unit (on the CPUs of
    KGC_BENCH_CPUS)."""
    return ["systemd-run", "--user", "--scope", "-q", "--unit=" + unit,
            "--slice=" + SLICE, "-p", "MemoryMax=" + cap, "-p", "MemorySwapMax=0",
            "-p", "OOMPolicy=continue", "--"] + CHOOM + affinity(cmd)


def _cgroup_dir(proc, unit):
    """/sys/fs/cgroup/... of the scope, once systemd-run has moved into it."""
    try:
        with open("/proc/%d/cgroup" % proc.pid) as f:
            path = f.read().strip().split("::", 1)[-1]
    except OSError:
        return None
    if path.endswith("/" + unit + ".scope"):
        return "/sys/fs/cgroup" + path
    return None


class _Watch(threading.Thread):
    """Polls memory.events (oom_kill), memory.peak and the anonymous memory of
    memory.stat (the private memory of every process of the scope together,
    without the page cache) of a scope while it runs."""

    def __init__(self, proc, unit):
        super().__init__(daemon=True)
        self.proc, self.unit = proc, unit
        self.oom_kill, self.peak, self.anon = 0, None, 0
        self.done = threading.Event()

    def run(self):
        d = None
        while not self.done.is_set() and self.proc.poll() is None:
            d = d or _cgroup_dir(self.proc, self.unit)
            if d:
                try:
                    ev = _read(os.path.join(d, "memory.events"))
                    m = re.search(r"^oom_kill (\d+)", ev, re.M)
                    self.oom_kill = max(self.oom_kill, int(m.group(1)) if m else 0)
                    self.peak = int(_read(os.path.join(d, "memory.peak")))
                    m = re.search(r"^anon (\d+)", _read(os.path.join(d, "memory.stat")), re.M)
                    self.anon = max(self.anon, int(m.group(1)) if m else 0)
                except (OSError, ValueError):
                    pass
            self.done.wait(0.2)


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _kill_scope(proc, unit):
    subprocess.run(["systemctl", "--user", "kill", "--signal=SIGKILL", unit + ".scope"],
                   capture_output=True)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass


def run(cmd, timeout, cwd=None, env=None, mem_cap=None, stdout=None):
    """Run cmd as a cold process under the cap and /usr/bin/time -v.

    Returns a dict: status ("ok", "error", "timeout", "oom"), returncode,
    wall_s, rss_mb (peak resident set of the largest process, GNU time),
    cg_peak_mb (peak of the scope's cgroup, page cache included, polled),
    anon_peak_mb (peak anonymous memory of the scope: all its processes, polled),
    mem_cap, stdout, stderr (the command's own; time's report apart).
    stdout: a file object to write the command's standard output to (else
    captured)."""
    cap = resolve(mem_cap)
    fd, report = tempfile.mkstemp(prefix="kgcb-time-", suffix=".txt")
    os.close(fd)
    full = ["/usr/bin/time", "-v", "-o", report] + list(cmd)
    unit = None
    if not cap:
        full = affinity(full)
    if cap:
        setup(cap)
        unit = unit_name()
        full = wrap(full, cap, unit)
    t0 = time.perf_counter()
    proc = subprocess.Popen(full, cwd=cwd, env=env, stdout=stdout or subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    watch = None
    if unit:
        watch = _Watch(proc, unit)
        watch.start()
    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if unit:
            _kill_scope(proc, unit)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
    wall = time.perf_counter() - t0
    if watch:
        watch.done.set()
        watch.join(1)
    try:
        rep = _read(report)
        os.unlink(report)
    except OSError:
        rep = ""
    m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", rep)
    rss = round(int(m.group(1)) / 1024, 1) if m else None
    killed9 = "terminated by signal 9" in rep or proc.returncode in (137, -9)
    res = {"returncode": proc.returncode, "wall_s": round(wall, 3), "rss_mb": rss,
           "cg_peak_mb": round(watch.peak / 2**20, 1) if watch and watch.peak else None,
           # the sum over the processes of the scope (a multi-process engine:
           # Morph-KGC), polled every 0.2 s; rss_mb is the largest process only
           "anon_peak_mb": round(watch.anon / 2**20, 1) if watch and watch.anon else None,
           "mem_cap": cap or "none", "stdout": out or "", "stderr": err or "",
           "unit": unit}
    if unit and watch.oom_kill:
        # the kernel killed a process at the cap, even if the run then hung until
        # the time limit (Morph-KGC: a pool worker killed, the pool waits for ever)
        res["status"] = "oom"
    elif timed_out:
        res["status"] = "timeout"
    elif unit and killed9:
        # SIGKILL that is not ours: the kernel, at the cap of the scope or of
        # the slice (or systemd-oomd, which kills the whole scope: no report)
        res["status"] = "oom"
    elif proc.returncode == 0:
        res["status"] = "ok"
    else:
        res["status"] = "error"
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run a command under the memory cap of the harness.")
    ap.add_argument("--mem-cap", help="default: KGC_BENCH_MEM_CAP, else %s" % DEFAULT_CAP)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)
    cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    if not cmd:
        ap.error("no command")
    cap = resolve(args.mem_cap)
    if not cap:
        os.execvp(cmd[0], cmd)
    setup(cap)
    full = wrap(cmd, cap, unit_name())
    os.execvp(full[0], full)


if __name__ == "__main__":
    sys.exit(main())
