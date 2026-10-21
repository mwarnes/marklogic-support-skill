#!/usr/bin/env python3
"""Summarise a pstack movie (the pstack.log written by pstack.sh) into per-snapshot thread classes and findings.

Usage: analyse_pstack.py PATH... [--out DIR] [--min-samples N] [--min-threads N]
Inputs: a pstack.log (or .txt) with gdb/pstack style blocks `Thread N (Thread 0x... (LWP n)):` / `#k  0x... in func () from lib`,
        a .zip containing one, or a directory (recursed; binary files and files or zip members over 512 MB are skipped with a note).
        A date line (a line outside a thread block with a hh:mm:ss time and a 4-digit year, as written by pstack.sh) starts a snapshot
        and a dated snapshot ends only at the next date line; without date lines a new snapshot starts where the thread numbers restart.
        Text outside thread blocks (a MarkLogic banner, say) is ignored and only counted in the Notes.
Writes: SUMMARY.md findings.json snapshots.csv   (never whole stacks: only counts and the top few signatures; all UTF-8)
Provenance: the maintainer notes (2026-10-21) supply only the three categories to look for (same place across snapshots; waiting in
sleep/poll/synchronisation; identical internal stacks). The specific wait / lock function name lists and the allocator and
CacheListStorage patterns below are the script author's heuristics, derived from one anonymised 2015 customer capture (glibc 2.12,
jemalloc); what a MarkLogic function means is not decided here.
Wait / lock classification: frame names are normalised (`__GI_`, `__libc_`, leading underscores, `je_`, `.constprop.N` / `.isra.N` /
`.part.N` / `.cold` removed) and the first 3 frames are checked. A thread is `waiting` if any of them is a wait name; it is `lock` if
the top frame is a lock name, or a lock name is the frame directly under a wait/futex frame (the wait called from the lock path);
lock wins over waiting only in those two cases. Anything else is `running`.
"""
import argparse, csv, json, re, sys, zipfile
from collections import Counter, defaultdict
from pathlib import Path

MAX_BYTES = 512 * 1024 * 1024
THREAD_RE = re.compile(r"^Thread (\d+) \(.*?\bLWP (\d+)\b")
FRAME_RE = re.compile(r"^#(\d+)\s+(?:0x[0-9a-fA-F]+ in )?(.*?)\s*$")
TIME_RE = re.compile(r"(?<!\d)\d{1,2}:\d\d:\d\d(?!\d)")
YEAR_RE = re.compile(r"(?<!\d)(?:199\d|20\d\d)(?!\d)")

# Names are stored normalised (see norm()): no leading underscores, `GI_`, `libc_` or `je_`.
WAIT = {"sem_wait", "sem_timedwait", "sem_clockwait", "do_futex_wait", "futex", "poll", "ppoll", "select", "pselect6", "epoll_wait",
        "epoll_pwait", "accept", "accept4", "recv", "recvfrom", "recvmsg", "read", "nanosleep", "clock_nanosleep", "sleep", "usleep"}
WAIT_PREFIX = ("pthread_cond_", "futex_wait", "futex_abstimed_wait", "new_sem_wait")
LOCK = {"lll_lock_wait", "lll_lock_wait_private", "pthread_mutex_lock", "pthread_mutex_clocklock", "pthread_mutex_timedlock",
        "pthread_rwlock_rdlock", "pthread_rwlock_wrlock", "sched_yield"}
SUFFIX_RE = re.compile(r"(?:\.(?:constprop|isra|part)\.\d+|\.cold(?:\.\d+)?)+$")


def norm(name):
    """Normalised function name: `__GI___poll` -> `poll`, `do_futex_wait.constprop.1` -> `do_futex_wait`, `je_arena_purge` -> `arena_purge`."""
    n = SUFFIX_RE.sub("", name)
    for pat in (r"^_+", r"^GI_", r"^_+", r"^libc_", r"^je_"):
        t = re.sub(pat, "", n)
        n = t or n
    return n


def is_wait(n):
    return n in WAIT or n.startswith(WAIT_PREFIX)


def is_lock(n):
    return n in LOCK or n.startswith("lll_lock_wait")


# name, predicate over (normalised frame names top first, thread class), what the frames literally show
PATTERNS = [
    ("allocator_purge", lambda fr, cls: any(f.startswith(("pages_purge", "arena_purge", "arena_decay")) for f in fr),
     "jemalloc is purging dirty pages (pages_purge / arena_purge / arena_decay, which calls madvise)"),
    ("thread_cache_flush", lambda fr, cls: any(f.startswith(("tcache_bin_flush", "tcache_destroy", "tcache_event", "thread_tcache_flush")) for f in fr),
     "a jemalloc thread cache is being flushed or destroyed (thread exit or an explicit flush)"),
    ("allocator_lock_wait", lambda fr, cls: cls == "lock" and any(f.startswith(("arena_", "tcache_")) for f in fr),
     "waiting on a jemalloc arena lock"),
    ("list_cache_lock_wait", lambda fr, cls: cls == "lock" and any("CacheListStorage" in f for f in fr),
     "waiting on a lock under CacheListStorage (list cache)"),
]


def base(text):
    """Function name of a frame line body: drop ' from lib', the trailing ' ()' and the parameter list."""
    t = re.sub(r"\s+from\s+\S+\s*$", "", text)
    t = re.sub(r"\s+\(\)\s*$", "", t)
    t = re.sub(r"\(.*$", "", t).strip()
    return t.split("@")[0] or "??"


def is_date_line(line):
    """A line outside a thread block (not `Thread `, `#` or indented) with a hh:mm:ss time and a 4-digit year 1990-2099."""
    return bool(line) and not line.startswith(("Thread ", "#")) and not line[0].isspace() \
        and bool(TIME_RE.search(line)) and bool(YEAR_RE.search(line))


def classify(frames):
    """`waiting` / `lock` / `running` from the first 3 frames (a single name is accepted too)."""
    names = [norm(f) for f in ([frames] if isinstance(frames, str) else frames[:3])]
    waits = [is_wait(n) or (n == "syscall" and i + 1 < len(names) and (is_wait(names[i + 1]) or is_lock(names[i + 1])))
             for i, n in enumerate(names)]
    for i, n in enumerate(names):
        if is_lock(n) and (i == 0 or waits[i - 1]):
            return "lock"
    return "waiting" if any(waits) else "running"


def parse_text(text, label, notes):
    """-> list of snapshots: {"date": str|None, "threads": [{"tid","lwp","frames":[base names]}]}"""
    snaps, cur, prev_tid, thread, ignored = [], None, None, None, 0
    for line in text.splitlines():
        if is_date_line(line):
            cur = {"date": line.strip(), "threads": []}
            snaps.append(cur); prev_tid = None; thread = None
            continue
        m = THREAD_RE.match(line)
        if m:
            tid, lwp = int(m[1]), int(m[2])
            if cur is None or (cur["date"] is None and prev_tid is not None and tid > prev_tid):
                cur = {"date": None, "threads": []}
                snaps.append(cur)
            prev_tid = tid
            thread = {"tid": tid, "lwp": lwp, "frames": []}
            cur["threads"].append(thread)
            continue
        f = FRAME_RE.match(line)
        if f and thread is not None:
            thread["frames"].append(base(f[2]))
        elif line.strip():
            ignored += 1
    if ignored:
        notes.add(f"{label}: {ignored} line(s) of text outside thread blocks were ignored")
    return [s for s in snaps if s["threads"]]


def is_binary(head):
    return b"\0" in head


def read_inputs(paths, notes):
    out = []
    for p in map(Path, paths):
        if not p.exists():
            sys.exit(f"analyse_pstack: path not found: {p}")
        files = sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [p]
        for f in files:
            try:
                size = f.stat().st_size
                if size > MAX_BYTES:
                    notes.add(f"{f.name}: skipped, larger than {MAX_BYTES / 1048576:g} MB")
                    continue
                if f.suffix.lower() == ".zip":
                    with zipfile.ZipFile(f) as z:
                        for info in sorted(z.infolist(), key=lambda i: i.filename):
                            name = info.filename
                            if name.endswith("/") or Path(name).suffix.lower() not in (".log", ".txt"):
                                continue
                            if info.file_size > MAX_BYTES:
                                notes.add(f"{f.name}:{name}: skipped, larger than {MAX_BYTES / 1048576:g} MB")
                                continue
                            data = z.read(name).decode("utf-8", errors="replace")
                            if re.search(r"(?m)^Thread \d+ \(", data):
                                out.append((f"{f.name}:{name}", data))
                else:
                    raw = f.read_bytes()
                    if is_binary(raw[:4096]):
                        notes.add(f"{f.name}: skipped, binary file")
                        continue
                    data = raw.decode("utf-8", errors="replace")
                    if re.search(r"(?m)^Thread \d+ \(", data):
                        out.append((f.name, data))
                    else:
                        notes.add(f"{f.name}: skipped, no 'Thread N (...)' blocks")
            except zipfile.BadZipFile:
                notes.add(f"{f.name}: not a readable zip file")
            except OSError as e:
                notes.add(f"{f.name}: could not be read ({type(e).__name__})")
    return out


def analyse(snaps, min_samples, min_threads):
    rows, findings = [], []
    for i, s in enumerate(snaps, 1):
        cls = Counter(); pats = Counter()
        for t in s["threads"]:
            fr = t["frames"]
            t["class"] = classify(fr)
            cls[t["class"]] += 1
            nfr = [norm(f) for f in fr]
            for name, pred, _ in PATTERNS:
                if pred(nfr, t["class"]):
                    pats[name] += 1
        s["cls"], s["pats"] = cls, pats
        rows.append({"snapshot": i, "date": s["date"] or "", "threads": len(s["threads"]), "waiting": cls["waiting"],
                     "lock": cls["lock"], "running": cls["running"], **{n: pats[n] for n, _, _ in PATTERNS}})
    # patterns seen in enough threads
    for name, _, meaning in PATTERNS:
        hit = [(i + 1, s["pats"][name]) for i, s in enumerate(snaps) if s["pats"][name] >= min_threads]
        if hit:
            findings.append({"rule": name, "severity": 0 if name.startswith(("allocator", "thread_cache")) else 1,
                             "detail": meaning, "snapshots": [h[0] for h in hit], "threads_per_snapshot": [h[1] for h in hit],
                             "of_snapshots": len(snaps)})
    # bursts: the same pattern present in some snapshots and absent in others
    for name, _, _ in PATTERNS:
        counts = [s["pats"][name] for s in snaps]
        if len(snaps) >= 3 and max(counts) >= min_threads and min(counts) == 0:
            findings.append({"rule": "bursty_" + name, "severity": 1,
                             "detail": f"{name} threads come in bursts: {counts} per snapshot",
                             "snapshots": [i + 1 for i, c in enumerate(counts) if c], "of_snapshots": len(snaps)})
    # non-waiting threads whose top frames do not change across consecutive snapshots
    by_lwp = defaultdict(list)
    for i, s in enumerate(snaps):
        for t in s["threads"]:
            by_lwp[t["lwp"]].append((i, t))
    stuck = []
    for lwp, seen in by_lwp.items():
        run, best = [], []
        for i, t in seen:
            if t["class"] == "waiting":
                run = []
                continue
            sig = tuple(t["frames"][:6])
            if run and run[-1][0] == i - 1 and run[-1][1] == sig:
                run.append((i, sig))
            else:
                run = [(i, sig)]
            if len(run) > len(best):
                best = list(run)
        if len(best) >= min_samples:
            stuck.append((lwp, len(best), " <- ".join(best[0][1][:4])))
    if stuck:
        findings.append({"rule": "same_stack_across_snapshots", "severity": 0,
                         "detail": f"{len(stuck)} non-waiting thread(s) show the same top frames in {min_samples}+ consecutive snapshots",
                         "threads": [{"lwp": a, "snapshots": b, "top": c} for a, b, c in sorted(stuck, key=lambda x: -x[1])[:10]],
                         "of_snapshots": len(snaps)})
    # thread churn
    if len(snaps) >= 3:
        once = sum(1 for lwp, seen in by_lwp.items() if len({i for i, _ in seen}) == 1)
        share = once / len(by_lwp)
        if share >= 0.10:
            findings.append({"rule": "thread_churn", "severity": 1,
                             "detail": f"{once} of {len(by_lwp)} threads ({share:.0%}) appear in only one snapshot (threads created and destroyed between snapshots)",
                             "of_snapshots": len(snaps)})
    findings.sort(key=lambda f: (f["severity"], f["rule"]))
    return rows, findings, by_lwp


def run_kind(frames):
    for f in frames:
        if f.endswith("::run") and f not in ("svc::Thread::run",):
            return f
    return "(other)"


def write_outputs(label_snaps, rows_all, findings_all, out, notes, min_samples, min_threads):
    out.mkdir(parents=True, exist_ok=True)
    (out / "findings.json").write_text(json.dumps(findings_all, indent=2) + "\n", encoding="utf-8")
    cols = ["input", "snapshot", "date", "threads", "waiting", "lock", "running"] + [n for n, _, _ in PATTERNS]
    with (out / "snapshots.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in rows_all:
            w.writerow({c: r.get(c, "") for c in cols})
    L = ["# pstack analysis", ""]
    for label, snaps, rows, findings in label_snaps:
        L += [f"## {label}", "",
              f"{len(snaps)} snapshot(s); threads per snapshot {[len(s['threads']) for s in snaps]}; "
              f"{'sample times from date lines' if any(s['date'] for s in snaps) else 'no date lines: sample times and spacing unknown'}.", "",
              "| Snapshot | Date | Threads | Waiting | Lock wait | Running | " + " | ".join(n for n, _, _ in PATTERNS) + " |",
              "| --- | --- | --- | --- | --- | --- | " + " | ".join("---" for _ in PATTERNS) + " |"]
        for r in rows:
            L.append(f"| {r['snapshot']} | {r['date'] or '-'} | {r['threads']} | {r['waiting']} | {r['lock']} | {r['running']} | "
                     + " | ".join(str(r[n]) for n, _, _ in PATTERNS) + " |")
        L += ["", "### Findings (likely cause first)", ""]
        if findings:
            for f in findings:
                extra = ""
                if "threads_per_snapshot" in f:
                    extra = f" — snapshots {f['snapshots']} had {f['threads_per_snapshot']} thread(s)"
                elif f.get("threads"):
                    extra = " — " + "; ".join(f"LWP {t['lwp']} x{t['snapshots']} ({t['top']})" for t in f["threads"][:5])
                L.append(f"- **{f['rule']}**: {f['detail']}{extra}")
        else:
            L.append("- No pattern met its threshold.")
        run_tops, kinds = Counter(), Counter()
        for s in snaps:
            for t in s["threads"]:
                kinds[run_kind(t["frames"])] += 1
                if t["class"] == "running":
                    run_tops[(t["frames"][0] if t["frames"] else "??")] += 1
        L += ["", "### Top frames of running (non-waiting) threads, all snapshots", ""]
        L += [f"- {n} x `{f[:100]}`" for f, n in run_tops.most_common(8)] or ["- none"]
        L += ["", "### Thread kinds (nearest `::run` frame), all snapshots", ""]
        L += [f"- {n} x `{k[:100]}`" for k, n in kinds.most_common(8)]
        L.append("")
    L += ["## How to read this", "",
          "- Waiting = a sleep/poll/accept/semaphore/condition/futex wait among the first 3 frames; Lock wait = a mutex wait at the top or directly under a wait frame, and `sched_yield` spins; Running = everything else. The three categories come from the maintainer notes (2026-10-21); the function name lists and allocator patterns are the script author's heuristics from one customer capture.",
          f"- Thresholds: a pattern is reported when {min_threads}+ threads match in a snapshot; the same-stack rule needs {min_samples}+ consecutive snapshots.",
          "- What a given MarkLogic function or thread kind means is not decided by this tool `[unverified — confirm]`."]
    if notes:
        L += ["", "## Notes", ""] + [f"- {n}" for n in sorted(notes)]
    (out / "SUMMARY.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out")
    ap.add_argument("--min-samples", type=int, default=3)
    ap.add_argument("--min-threads", type=int, default=3)
    a = ap.parse_args(argv)
    if a.min_samples < 1 or a.min_threads < 1:
        ap.error("--min-samples and --min-threads must be at least 1")
    notes = set()
    inputs = read_inputs(a.paths, notes)
    if not inputs:
        sys.exit("analyse_pstack: no pstack data found (expected blocks starting 'Thread N (Thread 0x... (LWP n)):').")
    label_snaps, rows_all, findings_all = [], [], []
    for label, text in inputs:
        snaps = parse_text(text, label, notes)
        if not snaps:
            continue
        rows, findings, _ = analyse(snaps, a.min_samples, a.min_threads)
        label_snaps.append((label, snaps, rows, findings))
        rows_all += [{**r, "input": label} for r in rows]
        findings_all += [{**f, "input": label} for f in findings]
    out = Path(a.out) if a.out else Path("pstack-analysis") / Path(a.paths[0]).stem
    write_outputs(label_snaps, rows_all, findings_all, out, notes, a.min_samples, a.min_threads)
    print(f"wrote {out}: {len(label_snaps)} input(s), {sum(len(x[1]) for x in label_snaps)} snapshot(s), {len(findings_all)} finding(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
