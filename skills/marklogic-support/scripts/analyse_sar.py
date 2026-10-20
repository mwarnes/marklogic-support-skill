#!/usr/bin/env python3
"""Analyse Linux SAR (sysstat) output into a saturation summary.

Usage: analyse_sar.py PATH... [--out DIR] [--min-samples N]
Inputs: `sar -A` / `sar -u -r -d ...` text output (files or directories, recursed); a binary sa## file is
        converted with the local `sar -A -f` when sysstat is installed (otherwise ask the customer for the
        text output: LC_ALL=C S_TIME_FORMAT=ISO sar -A -f /var/log/sa/saDD > saDD.txt).
Writes: SUMMARY.md findings.json series-<host>.csv
Thresholds are the RULES table below; a finding needs --min-samples (default 2) consecutive samples.
"""
import argparse, csv, json, os, re, shutil, statistics, subprocess, sys
from collections import defaultdict, namedtuple
from datetime import datetime, timedelta
from pathlib import Path

HEADER_RE = re.compile(r"^Linux (\S+) \(([^)]+)\)\s+(\S+)(?:\s+_\S+_)?(?:\s+\((\d+) CPU\))?")
TIME_RE = re.compile(r"^(\d{1,2}):(\d\d):(\d\d)(?: ([AP]M))?\s+(.*)$")
KEYED = {"CPU", "DEV", "IFACE", "FILESYS", "TTY", "INTR", "BUS", "FAN", "TEMP", "IN", "MHz", "DEVICE"}
ALIAS = {"%usr": "%user", "%sys": "%system"}
NET_ERR = ("rxerr/s", "txerr/s", "coll/s", "rxdrop/s", "txdrop/s", "txcarr/s", "rxfram/s", "rxfifo/s", "txfifo/s")

Rule = namedtuple("Rule", "name severity op threshold unit value meaning")


def _all_cpu(col):
    return lambda m, k, n: m.get(col) if k == "all" else None


def _cpu_busy(m, k, n):
    if k != "all" or "%user" not in m or "%system" not in m:
        return None
    return m["%user"] + m["%system"] + m.get("%nice", 0.0)


def _runq(m, k, n):
    return m["runq-sz"] / n if "runq-sz" in m and n else None


def _swap(m, k, n):
    return m["pswpin/s"] + m["pswpout/s"] if "pswpin/s" in m and "pswpout/s" in m else None


def _mem_avail(m, k, n):
    if all(c in m for c in ("kbavail", "kbmemfree", "kbmemused")):
        total = m["kbmemfree"] + m["kbmemused"]
        return 100.0 * m["kbavail"] / total if total else None
    return None


def _per_dev(col):
    return lambda m, k, n: m.get(col) if k and "%util" in m else None


def _net_err(m, k, n):
    if not k or "rxerr/s" not in m:
        return None
    return sum(m.get(c, 0.0) for c in NET_ERR)


# severity: 0 = likely cause of a MarkLogic slowdown, 1 = contributing / check
RULES = [
    Rule("cpu_iowait", 0, ">", 20.0, "% iowait", _all_cpu("%iowait"), "CPUs idle while waiting on disk I/O"),
    Rule("disk_await", 0, ">", 50.0, "ms await", _per_dev("await"), "disk requests queue and complete slowly"),
    Rule("disk_util", 0, ">", 80.0, "% util", _per_dev("%util"), "device close to saturation"),
    Rule("swap_io", 0, ">", 1.0, "pages/s", _swap, "memory pressure: pages moved to/from swap"),
    Rule("mem_available", 0, "<", 10.0, "% avail", _mem_avail, "little memory available to the OS"),
    Rule("direct_reclaim", 0, ">", 1.0, "pgscand/s", lambda m, k, n: m.get("pgscand/s"),
         "processes reclaiming memory directly (stalls)"),
    Rule("cpu_busy", 1, ">", 90.0, "% user+sys", _cpu_busy, "CPU saturated"),
    Rule("run_queue", 1, ">", 2.0, "x CPUs", _runq, "more runnable tasks than CPUs can serve"),
    Rule("cpu_steal", 1, ">", 5.0, "% steal", _all_cpu("%steal"), "hypervisor taking CPU (noisy neighbour / throttling)"),
    Rule("major_faults", 1, ">", 100.0, "majflt/s", lambda m, k, n: m.get("majflt/s"), "pages read from disk on demand"),
    Rule("net_errors", 1, ">", 0.0, "errors+drops/s", _net_err, "network interface errors or drops"),
]


def is_num(t):
    try:
        float(t)
        return True
    except ValueError:
        return False


def parse_date(s):
    """-> (date, ambiguous). ISO, MM/DD/YYYY, DD/MM/YYYY, with 2- or 4-digit years."""
    m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", s)
    if m:
        return datetime(int(m[1]), int(m[2]), int(m[3])), False
    m = re.fullmatch(r"(\d\d)/(\d\d)/(\d{2}|\d{4})", s)
    if not m:
        return None, False
    a, b, y = int(m[1]), int(m[2]), int(m[3])
    y += 2000 if y < 100 else 0
    if a > 12:
        return datetime(y, b, a), False
    return datetime(y, a, b), b <= 12 and a != b


def sniff(path):
    try:
        raw = path.read_bytes()[:4096]
    except OSError:
        return None
    if b"\0" in raw:
        return "binary"
    text = raw.decode("utf-8", "replace")
    return "text" if re.search(r"^Linux \S+ \(", text, re.M) and re.search(TIME_RE.pattern, text, re.M) else None


def binary_to_text(path):
    sar = shutil.which("sar")
    if not sar:
        sys.exit(f"analyse_sar: {path} is a binary sa file and sysstat's `sar` is not installed here. Ask the customer "
                 "for text output: LC_ALL=C S_TIME_FORMAT=ISO sar -A -f /var/log/sa/saDD > saDD.txt")
    env = dict(os.environ, LC_ALL="C", S_TIME_FORMAT="ISO")
    r = subprocess.run([sar, "-A", "-f", str(path)], capture_output=True, text=True, env=env)
    if r.returncode or not r.stdout.strip():
        sys.exit(f"analyse_sar: `sar -A -f {path}` failed ({r.stderr.strip() or 'no output'}); the file was probably "
                 "written by a different sysstat version. Ask the customer for text output (see --help).")
    return r.stdout


def parse(text, fallback_host, notes):
    """Yield sample dicts and restart markers from one sar text output."""
    host, ncpu, base, day, prev, cols, keyed = fallback_host, None, None, None, None, None, False
    rows, restarts = [], []
    for line in text.splitlines():
        h = HEADER_RE.match(line)
        if h:
            host, ncpu = h[2], int(h[4]) if h[4] else ncpu
            base, amb = parse_date(h[3])
            day = base
            if amb:
                notes.add(f"{host}: date '{h[3]}' is ambiguous; read as MM/DD/YYYY (ask for S_TIME_FORMAT=ISO output)")
            prev, cols = None, None
            continue
        if not line.strip():
            cols, prev, day = None, None, base                    # each sar section restarts at the first sample time
            continue
        m = TIME_RE.match(line)
        if not m or day is None:
            continue
        hh, mm, ss, ap, rest = int(m[1]), int(m[2]), int(m[3]), m[4], m[5].split()
        if ap:
            hh = hh % 12 + (12 if ap == "PM" else 0)
        secs = hh * 3600 + mm * 60 + ss
        if prev is not None and secs < prev - 3600:
            day += timedelta(days=1)
        prev = secs
        ts = day + timedelta(seconds=secs)
        if rest[:2] == ["LINUX", "RESTART"]:
            restarts.append((host, ts)); cols = None
            continue
        if not any(is_num(t) for t in rest):                       # a column-header line
            keyed = rest[0] in KEYED
            cols = [ALIAS.get(c, c) for c in (rest[1:] if keyed else rest)]
            prev, day = None, base
            continue
        if cols is None:
            continue
        key, vals = (rest[0], rest[1:]) if keyed else ("", rest)
        if len(vals) != len(cols) or not all(is_num(v) for v in vals):
            continue
        rows.append({"host": host, "ncpu": ncpu, "ts": ts, "key": key, "m": dict(zip(cols, map(float, vals)))})
    return rows, restarts


def find(rows, min_samples):
    runs, out = {}, []

    def close(k):
        run = runs.pop(k, None)
        if run and len(run) >= min_samples:
            rule = next(r for r in RULES if r.name == k[1])
            pick = max if rule.op == ">" else min
            peak = pick(run, key=lambda s: s[1])
            out.append({"host": k[0], "rule": rule.name, "key": k[2], "severity": rule.severity,
                        "start": run[0][0].isoformat(" "), "end": run[-1][0].isoformat(" "),
                        "samples": len(run), "peak": round(peak[1], 2), "peak_at": peak[0].isoformat(" "),
                        "threshold": rule.threshold, "op": rule.op, "unit": rule.unit, "meaning": rule.meaning})

    for r in sorted(rows, key=lambda r: r["ts"]):
        for rule in RULES:
            v = rule.value(r["m"], r["key"], r["ncpu"])
            if v is None:
                continue
            k = (r["host"], rule.name, r["key"])
            if (v > rule.threshold) if rule.op == ">" else (v < rule.threshold):
                runs.setdefault(k, []).append((r["ts"], v))
            else:
                close(k)
    for k in list(runs):
        close(k)
    return sorted(out, key=lambda f: (f["severity"], -f["samples"], f["host"], f["start"]))


def inventory(rows, restarts):
    by = defaultdict(list)
    for r in rows:
        by[r["host"]].append(r)
    inv = {}
    for host, rs in by.items():
        stamps = sorted({r["ts"] for r in rs})
        deltas = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:])]
        interval = statistics.median(deltas) if deltas else None
        gaps = [(a, b) for a, b in zip(stamps, stamps[1:]) if interval and (b - a).total_seconds() > 3 * interval]
        inv[host] = {"ncpu": rs[0]["ncpu"], "start": stamps[0], "end": stamps[-1], "samples": len(stamps),
                     "interval": interval, "gaps": gaps, "restarts": [t for h, t in restarts if h == host]}
    return inv


def write_series(rows, out):
    by = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        m, k, n, d = r["m"], r["key"], r["ncpu"], by[r["host"]][r["ts"]]
        for name, col in (("cpu_busy", None), ("iowait", "%iowait"), ("steal", "%steal"), ("runq", "runq-sz"),
                          ("ldavg1", "ldavg-1"), ("pgscand", "pgscand/s")):
            v = _cpu_busy(m, k, n) if name == "cpu_busy" else (m.get(col) if col else None)
            if v is not None and (k in ("all", "") or name == "cpu_busy"):
                d[name] = v
        for rule, name in ((RULES[3], "swap_io"), (RULES[4], "mem_avail_pct")):
            v = rule.value(m, k, n)
            if v is not None:
                d[name] = v
        for col, name in (("%util", "disk_util_max"), ("await", "disk_await_max")):
            if k and col in m:
                d[name] = max(d.get(name, 0.0), m[col])
        v = _net_err(m, k, n)
        if v is not None:
            d["net_err"] = d.get("net_err", 0.0) + v
    cols = ["cpu_busy", "iowait", "steal", "runq", "ldavg1", "swap_io", "mem_avail_pct", "pgscand",
            "disk_util_max", "disk_await_max", "net_err"]
    for host, series in by.items():
        with (out / f"series-{host}.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["time"] + cols)
            for ts in sorted(series):
                w.writerow([ts.isoformat(" ")] + [round(series[ts][c], 2) if c in series[ts] else "" for c in cols])


def write_summary(inv, findings, notes, out):
    L = ["# SAR analysis", "", "## Hosts", "",
         "| Host | CPUs | From | To | Samples | Interval | Restarts | Gaps |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for host, i in sorted(inv.items()):
        iv = f"{i['interval'] / 60:g} min" if i["interval"] else "n/a"
        L.append(f"| {host} | {i['ncpu'] or '?'} | {i['start']} | {i['end']} | {i['samples']} | {iv} | "
                 f"{', '.join(str(t) for t in i['restarts']) or '-'} | {len(i['gaps'])} |")
    L += ["", "## Findings (ranked: likely cause first)", ""]
    if findings:
        L += ["| Host | Finding | Where | Window | Samples | Peak | Meaning |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for f in findings:
            tag = "likely cause" if f["severity"] == 0 else "check"
            cond = f"{f['op']} {f['threshold']:g} {f['unit']}"
            L.append(f"| {f['host']} | {f['rule']} ({tag}) | {f['key'] or '-'} | {f['start']} to {f['end']} | {f['samples']} | "
                     f"{f['peak']:g} at {f['peak_at']} (threshold {cond}) | {f['meaning']} |")
    else:
        L.append("No sustained saturation found at the default thresholds.")
    for host, i in sorted(inv.items()):
        for a, b in i["gaps"][:5]:
            L.append(f"\n- {host}: no samples between {a} and {b} (sar was not collecting, or the host was down).")
    L += ["", "## What SAR cannot show", "",
          "- Which process or MarkLogic task caused the load (use pidstat, the ErrorLog and Monitoring History).",
          "- Anything between samples: a 10-minute interval hides short stalls.",
          "- Whether a threshold is abnormal for this system: compare with a quiet period or baseline."]
    if notes:
        L += ["", "## Notes", ""] + [f"- {n}" for n in sorted(notes)]
    (out / "SUMMARY.md").write_text("\n".join(L) + "\n")


def load(paths, notes):
    rows, restarts = [], []
    files = []
    for p in map(Path, paths):
        files += sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [p]
    used = 0
    for f in files:
        kind = sniff(f)
        if kind is None:
            continue
        text = binary_to_text(f) if kind == "binary" else f.read_text(errors="replace")
        r, rs = parse(text, f.stem, notes)
        rows += r; restarts += rs; used += 1
    return rows, restarts, used


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out")
    ap.add_argument("--min-samples", type=int, default=2)
    a = ap.parse_args(argv)
    notes = set()
    rows, restarts, used = load(a.paths, notes)
    if not rows:
        sys.exit("analyse_sar: no SAR data found (expected `sar -A` text output with a 'Linux ... (N CPU)' header).")
    out = Path(a.out) if a.out else Path("sar-analysis") / Path(a.paths[0]).stem
    out.mkdir(parents=True, exist_ok=True)
    findings, inv = find(rows, a.min_samples), inventory(rows, restarts)
    (out / "findings.json").write_text(json.dumps(findings, indent=2) + "\n")
    write_series(rows, out)
    write_summary(inv, findings, notes, out)
    print(f"wrote {out}: {used} files, {len(inv)} hosts, {len(rows)} samples, {len(findings)} findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
