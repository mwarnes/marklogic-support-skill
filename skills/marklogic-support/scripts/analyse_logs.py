#!/usr/bin/env python3
"""Analyse MarkLogic logs into an incident timeline and pattern summary.

Usage: analyse_logs.py PATH... [--out DIR] [--host NAME] [--topology topology.json]
Inputs: ErrorLog*, TaskServer_ErrorLog*, /var/log/messages copies (messages*, syslog*), *AccessLog*, AuditLog*;
        files or directories (recursed), e.g. dump-analysis/<dump>/logs.
Writes: INVENTORY.md TIMELINE.md hosts/<host>/TIMELINE.md PATTERNS.md [ACCESS.md AUDIT.md] events.jsonl
"""
import argparse, json, re, statistics, sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- 1. classifier
ML_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) (\w+): (.*)$")
SYS_RE = re.compile(r"^(\w{3}) +(\d+) (\d\d:\d\d:\d\d) (\S+) ([\w./-]+?)(?:\[\d+\])?: (.*)$")
CLF_RE = re.compile(r'^(\S+) \S+ (\S+) \[([^\]]+)\] "([^"]*)" (\d{3}) (\S+)(?: \S+)*?(?: "([^"]*)")?$')
AUDIT_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) event=([\w-]+);(.*)$")
CODE_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,7}-[A-Z0-9]+\b")
MONTHS = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
KEEP_PROGS = {"kernel", "systemd", "systemd-fsck", "chronyd", "ntpd"}


def classify(path):
    n = path.name
    if n.endswith(".md") or "RequestLog" in n: return "skipped"
    if "AccessLog" in n: return "access"
    if n.startswith("AuditLog"): return "audit"
    if "ErrorLog" in n: return "errorlog"
    if n.startswith(("messages", "syslog")): return "syslog"
    return sniff(path)


def sniff(path):
    try:
        with path.open(errors="replace") as fh:
            head = [l for _, l in zip(range(200), fh) if l.strip()][:20]
    except OSError:
        return "unclassified"
    for l in head:
        if ML_RE.match(l): return "errorlog"
        if AUDIT_RE.match(l): return "audit"
        if SYS_RE.match(l): return "syslog"
        if CLF_RE.match(l.rstrip("\n")): return "access"
    return "unclassified"


def collect(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            for f in sorted(x for x in p.rglob("*") if x.is_file()):
                files.append({"path": f, "root": p, "kind": classify(f)})
        elif p.is_file():
            files.append({"path": p, "root": p.parent, "kind": classify(p)})
        else:
            print(f"WARNING: {p} not found", file=sys.stderr)
    return files


def short(h): return h.lower().split(".")[0]


def resolve_host(entry, args_host, syslog_host, known):
    if args_host: return short(args_host)
    p = entry["path"]
    if p.parent != entry["root"] and p.parent.name: return short(p.parent.name)
    if syslog_host: return short(syslog_host)
    m = re.match(r"(?:messages|syslog)[_-]([A-Za-z0-9-]+)", p.name)
    if m:
        tok = m.group(1).lower()
        return next((k for k in known if tok.startswith(k)), tok)
    for tok in re.split(r"[_.\-]", p.stem.lower()):
        if tok in known: return tok
    return "unknown"


# ---------------------------------------------------------------- 2. normaliser
def ev(ts, host, source, level, msg, path, line):
    m = CODE_RE.search(msg)
    return {"ts": ts, "host": host, "source": source, "level": level, "code": m.group(0) if m else None,
            "msg": msg, "file": str(path), "line": line}


def parse_errorlog(path, host):
    events, source = [], "taskserver" if "TaskServer" in path.name else "errorlog"
    with path.open(errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            line = line.rstrip("\n")
            m = ML_RE.match(line)
            if m: events.append(ev(m.group(1), host, source, m.group(2), m.group(3), path, n))
            elif events and line.strip(): events[-1]["msg"] += " ⏎ " + line.strip()
    return events


def parse_syslog(path, year):
    """Return (events, per-program counts, hostname seen). Host on events is filled in by the caller."""
    events, progs, seen_host = [], Counter(), None
    with path.open(errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            m = SYS_RE.match(line.rstrip("\n"))
            if not m: continue
            mon, day, tod, host, prog, msg = m.groups()
            seen_host = seen_host or host
            progs[prog] += 1
            if prog != "MarkLogic" and prog not in KEEP_PROGS: continue
            try:
                ts = f"{year}-{MONTHS.get(mon, 1):02d}-{int(day):02d} {tod}.000"
            except ValueError:
                continue
            level = "unknown"
            if prog == "MarkLogic":
                lm = re.match(r"^(Debug|Info|Notice|Warning|Error|Critical|Alert|Emergency): (.*)$", msg)
                if lm: level, msg = lm.groups()
                events.append(ev(ts, None, "syslog-ml", level, msg, path, n))
            else:
                events.append(ev(ts, None, "syslog", level, f"{prog}: {msg}", path, n))
    return events, progs, seen_host


def load_all(args):
    """Classify, attribute hosts, parse. Returns (files, events, notes)."""
    files, notes = collect(args.paths), []
    known = set()
    try:
        topo = json.loads(Path(args.topology).read_text()) if args.topology else {}
    except (OSError, json.JSONDecodeError):
        topo = {}
    known = {short(h["name"]) for h in topo.get("hosts", {}).values() if h.get("name")}
    errorlogs = [f for f in files if f["kind"] == "errorlog"]
    for f in errorlogs:
        f["host"] = resolve_host(f, args.host, None, known)
        f["events"] = parse_errorlog(f["path"], f["host"])
    years = {e["ts"][:4] for f in errorlogs for e in f["events"]}
    year, year_note = (max(years), "inferred from ErrorLog") if years else (None, "from file mtime")
    for f in files:
        f.setdefault("events", []); f.setdefault("host", "-"); f["progs"] = Counter(); f["note"] = ""
        if f["kind"] == "syslog":
            y = year or datetime.fromtimestamp(f["path"].stat().st_mtime).year
            evs, progs, seen = parse_syslog(f["path"], y)
            f["host"] = resolve_host(f, args.host, seen, known)
            for e in evs: e["host"] = f["host"]
            f["events"], f["progs"], f["note"] = evs, progs, f"year {y} {year_note}"
        elif f["kind"] in ("access", "audit"):
            f["host"] = resolve_host(f, args.host, None, known)
        if known and f["kind"] in ("errorlog", "syslog") and f["host"] not in known:
            f["note"] = (f["note"] + "; " if f["note"] else "") + f"host {f['host']} not in topology"
    events = sorted((e for f in files for e in f["events"]), key=lambda e: e["ts"])
    return files, events, notes


def write_inventory(files, out):
    L = ["# Log inventory", "", "| file | kind | host | lines | events | first | last | notes |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    progs = Counter()
    for f in files:
        rel = f["path"].relative_to(f["root"]) if f["path"] != f["root"] else f["path"].name
        try: lines = sum(1 for _ in f["path"].open(errors="replace"))
        except OSError: lines = "?"
        evs = f["events"]
        L.append(f"| {rel} | {f['kind']} | {f['host']} | {lines} | {len(evs)} | {evs[0]['ts'] if evs else ''} | {evs[-1]['ts'] if evs else ''} | {f['note']} |")
        progs.update(f["progs"])
    if progs:
        L += ["", "## syslog lines per program (only MarkLogic/kernel/systemd/chronyd/ntpd become events)", "", "| program | lines |", "| --- | --- |"]
        L += [f"| {p} | {n} |" for p, n in progs.most_common(30)]
    (out / "INVENTORY.md").write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------- 3. catalogue + collapse
CATALOGUE = [  # (kind, severity, regex, reference) — first match wins
    ("restart", "high", r"Starting MarkLogic Server|Started MarkLogic", "cluster-hosts-groups.md"),
    ("shutdown", "high", r"Shutting down|Stopp(ing|ed) MarkLogic|Failed to start MarkLogic|MarkLogic.*failed with result", "cluster-hosts-groups.md"),
    ("quorum", "high", r"\bquorum\b|XDMP-NOQUORUM", "cluster-hosts-groups.md"),
    ("host-state", "high", r"XDMP-HOSTOFFLINE|XDMP-HOSTDOWN|Host .* is (offline|online)|Disconnecting from domestic host|Connected to domestic host", "cluster-hosts-groups.md"),
    ("xdqp", "medium", r"Restart\w* XDQP|XDQP\w*.*([Tt]imeout|[Rr]estart)|XDMP-XDQP", "cluster-hosts-groups.md"),
    ("clock-skew", "medium", r"XDMP-CLOCKSKEW|(chronyd|ntpd).*(step|jump|adjust)", "cluster-hosts-groups.md"),
    ("memory", "high", r"Memory low|XDMP-MEMCANCELED|Linux Huge Pages: detected 0|Out of memory|oom-killer|Killed process", "memory-and-os.md"),
    ("failover", "high", r"\bfail(?:over|ing over| over)\b|open replica|sync replicating|wait replication", "ha-backup-failover.md"),
    ("forest-mount", "medium", r"Mounted forest|Unmounted forest|XDMP-FORESTMNT|Forest .* state changed", "databases-forests.md"),
    ("storage", "high", r"Detecting indexes.*slow|Slow (utime|fsync|fdatasync|read|write|open|close|stat)\b|XDMP-FORESTNOSPACE|XDMP-DISKFULL|I/O error|XFS \(.*\).*(error|corrupt)|EXT4-fs error", "databases-forests.md"),
    ("merge-reindex", "low", r"\bMerged\b|\bReindex|reindexer", "databases-forests.md"),
    ("backup", "low", r"[Bb]ackup|Restoring|XDMP-BACKUP", "ha-backup-failover.md"),
    ("security", "medium", r"\bSEC-[A-Z]+|XDMP-AUTH|Invalid login|not authorized|XDMP-PERMDENIED", "security.md"),
    ("appserver", "low", r"SVC-SOCBIND|SVC-SOCACC|XDMP-EXTIME|XDMP-MODNOTFOUND", "app-servers.md"),
]
CATALOGUE_RE = [(k, s, re.compile(rx), ref) for k, s, rx, ref in CATALOGUE]
ERROR_LEVELS = {"Critical", "Error", "Alert", "Emergency"}
SEVN = {"high": 0, "medium": 1, "low": 2}


def catalogue(e):
    for kind, sev, rx, ref in CATALOGUE_RE:
        if rx.search(e["msg"]): return kind, sev, ref
    if e["level"] in ERROR_LEVELS: return "error-line", "medium", ""
    return None


def annotate(events, topo):
    """Suffix forest names with their database from topology.json (parse_dump.py output)."""
    f2db = {f["name"]: f.get("database_name") for f in topo.get("forests", {}).values() if f.get("name")}
    if not f2db: return
    rx = re.compile(r"\b(" + "|".join(map(re.escape, sorted(f2db, key=len, reverse=True))) + r")\b")
    for e in events:
        m = rx.search(e["msg"])
        if m and f2db.get(m.group(1)): e["msg"] += f" (db: {f2db[m.group(1)]})"


def template(msg):
    return re.sub(r"0x[0-9a-f]+|\d+", "N", re.sub(r"/[\w./-]+", "/PATH", msg))[:120]


def collapse(events, window=60):
    """Events with the same (host, kind, template) within window s of that key's previous event → one row (keeps first ts)."""
    rows, last = [], {}
    for e in events:
        key = (e["host"], e["kind"], template(e["msg"]))
        t = datetime.strptime(e["ts"], "%Y-%m-%d %H:%M:%S.%f")
        r = last.get(key)
        if r and (t - r["last_t"]).total_seconds() <= window:
            r["n"] += 1; r["last_t"] = t; r["last"] = e["ts"]
        else:
            r = {"key": key, "n": 1, "last_t": t, "last": e["ts"], "e": e}; rows.append(r); last[key] = r
    return rows


def fmt_row(r):
    e = r["e"]; msg = e["msg"].replace("|", "/")
    if r["n"] > 1:
        # Show full timestamp if span crosses day boundary
        start_day, last_day = e["ts"][:10], r["last"][:10]
        if start_day != last_day:
            msg += f"  ×{r['n']} ({e['ts'][11:19]}…{r['last'][:19]})"
        else:
            msg += f"  ×{r['n']} ({e['ts'][11:19]}…{r['last'][11:19]})"
    return f"| {e['ts'][:19]} | {e['host']} | {e['source']} | {e['kind']} | {e['sev']} | {msg[:300]} |"


def write_timeline(events, path, title):
    rows, window, note = [], 60, ""
    for window in (60, 300, 1800, 3600, 6 * 3600, 86400):
        rows = collapse(events, window)
        if len(rows) <= 500: break
    if window != 60: note = f"> {len(events)} events; repeats collapsed within {window // 60} min windows so the whole span fits in {len(rows)} rows. Per-host timelines and events.jsonl keep finer detail.\n\n"
    if len(rows) > 500:
        dropped = []
        for sev in ("low", "medium"):
            if len(rows) > 500:
                rows = [r for r in rows if r["e"]["sev"] != sev]; dropped.append(sev)
        note = f"> even at 24 h collapse the span needs more than 500 rows; dropped {' and '.join(dropped)} severity rows" + ("; truncated to 500" if len(rows) > 500 else "") + " — see hosts/<host>/TIMELINE.md and events.jsonl.\n\n"
        rows = rows[:500]
    L = [f"# {title}", "", note + "| time | host | src | kind | sev | message |", "| --- | --- | --- | --- | --- | --- |"] + [fmt_row(r) for r in rows]
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text("\n".join(L) + "\n")


def write_timelines(events, out):
    cat = [e for e in events if e.get("kind")]
    write_timeline(cat, out / "TIMELINE.md", "Incident timeline (all hosts, times as written in each source)")
    for h in sorted({e["host"] for e in cat}):
        write_timeline([e for e in cat if e["host"] == h], out / "hosts" / h / "TIMELINE.md", f"Timeline — {h}")


# ---------------------------------------------------------------- 4. patterns / access / audit
def bursts(hours):
    """Hours with ≥20 events and >5× the median non-zero hour."""
    vals = [n for n in hours.values() if n]
    if len(vals) < 3: return []
    med = statistics.median(vals)
    return [h for h, n in hours.items() if n >= 20 and n > 5 * med]


def hour_table(hours, title):
    b = set(bursts(hours))
    L = ["", f"| {title} | events | |", "| --- | --- | --- |"]
    L += [f"| {h} | {n} | {'**burst**' if h in b else ''} |" for h, n in sorted(hours.items())]
    return L


def write_patterns(events, out):
    L = ["# Patterns", "", "Level counts, top codes and hourly bursts per host and source. Times as written in each source.", ""]
    groups = defaultdict(list)
    for e in events: groups[(e["host"], e["source"])].append(e)
    for (host, src), evs in sorted(groups.items()):
        levels = Counter(e["level"] for e in evs)
        codes = {}
        for e in evs:
            if e["code"]:
                d = codes.setdefault(e["code"], {"n": 0, "first": e["ts"], "last": e["ts"], "sample": e["msg"][:140].replace("|", "/"), "hours": Counter()})
                d["n"] += 1; d["last"] = e["ts"]; d["hours"][e["ts"][:13]] += 1
        restarts = [e["ts"] for e in evs if e.get("kind") == "restart" and "Starting MarkLogic Server" in e["msg"]]
        L += [f"## {host} / {src}", "", f"- {len(evs)} events · {evs[0]['ts']} → {evs[-1]['ts']}",
              f"- Restarts: {len(restarts)}" + (f" ({', '.join(restarts[:5])}{'…' if len(restarts) > 5 else ''})" if restarts else ""), "",
              "| Level | Lines |", "| --- | --- |"] + [f"| {l} | {n} |" for l, n in levels.most_common()]
        L += ["", "| Code | Count | First | Last | Sample |", "| --- | --- | --- | --- | --- |"]
        top = sorted(codes.items(), key=lambda x: -x[1]["n"])[:20]
        L += [f"| {c} | {d['n']} | {d['first']} | {d['last']} | {d['sample']} |" for c, d in top]
        for c, d in top[:10]:
            if bursts(d["hours"]): L += hour_table(d["hours"], f"{c} by hour")
        L.append("")
    (out / "PATTERNS.md").write_text("\n".join(L) + "\n")


def write_access(files, out):
    acc = [f for f in files if f["kind"] == "access"]
    if not acc: return
    L = ["# Access logs", "", "Request volume and failures per app-server port. Consult only for access/availability tickets.", ""]
    for f in acc:
        m = re.match(r"(\d+)_", f["path"].name); port = m.group(1) if m else f["path"].name
        total, classes, fails, hours, agents = 0, Counter(), Counter(), Counter(), Counter()
        with f["path"].open(errors="replace") as fh:
            for line in fh:
                mm = CLF_RE.match(line.rstrip("\n"))
                if not mm: continue
                _, user, when, req, status, _size, agent = mm.groups()
                total += 1; classes[status[0] + "xx"] += 1; agents[agent or "-"] += 1
                try: hours[datetime.strptime(when.split()[0], "%d/%b/%Y:%H:%M:%S").strftime("%Y-%m-%d %H")] += 1
                except ValueError: pass
                if status[0] in "45": fails[(status, " ".join(req.split()[:2]).split("?")[0])] += 1
        L += [f"## {f['host']} / port {port}", "", f"- {total} requests", "", "| class | count |", "| --- | --- |"]
        L += [f"| {c} | {n} |" for c, n in sorted(classes.items())]
        L += ["", "| status | request | count |", "| --- | --- | --- |"] + [f"| {s} | {r} | {n} |" for (s, r), n in fails.most_common(10)]
        L += hour_table(hours, "hour") + ["", "| user agent | count |", "| --- | --- |"] + [f"| {a.replace('|', '/')} | {n} |" for a, n in agents.most_common(5)] + [""]
    (out / "ACCESS.md").write_text("\n".join(L) + "\n")


def write_audit(files, out):
    aud = [f for f in files if f["kind"] == "audit"]
    if not aud: return
    L = ["# Audit logs", "", "Security-relevant events. Consult only for security/permission tickets.", ""]
    for f in aud:
        events, fails, users, uris, hours = Counter(), 0, Counter(), Counter(), Counter()
        with f["path"].open(errors="replace") as fh:
            for line in fh:
                m = AUDIT_RE.match(line.rstrip("\n"))
                if not m: continue
                ts, kind, rest = m.groups(); events[kind] += 1; hours[ts[:13]] += 1
                kv = dict(p.strip().split("=", 1) for p in rest.split(";") if "=" in p)
                if kv.get("success") == "false":
                    fails += 1; users[kv.get("user", "?")] += 1; uris[kv.get("uri", "?")] += 1
        L += [f"## {f['host']} / {f['path'].name}", "", f"- {sum(events.values())} events · success=false: {fails}", "",
              "| event | count |", "| --- | --- |"] + [f"| {k} | {n} |" for k, n in events.most_common()]
        L += ["", "| failing user | count |", "| --- | --- |"] + [f"| {u} | {n} |" for u, n in users.most_common(10)]
        L += ["", "| failing uri | count |", "| --- | --- |"] + [f"| {u.replace('|', '/')} | {n} |" for u, n in uris.most_common(10)]
        L += hour_table(hours, "hour") + [""]
    (out / "AUDIT.md").write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+"); ap.add_argument("--out"); ap.add_argument("--host"); ap.add_argument("--topology")
    a = ap.parse_args(argv)
    if not a.topology:                                   # auto-detect dump-analysis/<x>/topology.json
        for p in map(Path, a.paths):
            for anc in [p] + list(p.parents)[:3]:
                if (anc / "topology.json").exists(): a.topology = str(anc / "topology.json"); break
            if a.topology: break
    out = Path(a.out) if a.out else Path("log-analysis") / Path(a.paths[0]).name
    out.mkdir(parents=True, exist_ok=True)
    files, events, notes = load_all(a)
    write_inventory(files, out)
    try:
        topo = json.loads(Path(a.topology).read_text()) if a.topology else {}
    except (OSError, json.JSONDecodeError):
        topo = {}
    for e in events:
        c = catalogue(e); e["kind"], e["sev"], e["ref"] = c if c else (None, None, None)
    events = [e for e in events if e["kind"] or e["source"] != "syslog"]   # kernel/systemd lines only when catalogued
    annotate(events, topo)
    (out / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    write_timelines(events, out)
    write_patterns(events, out); write_access(files, out); write_audit(files, out)
    print(f"wrote {out}: {len(files)} files, {len(events)} events, {sum(1 for e in events if e['kind'])} catalogued, hosts {sorted({e['host'] for e in events})}")
    return 0


if __name__ == "__main__":
    sys.exit(main())