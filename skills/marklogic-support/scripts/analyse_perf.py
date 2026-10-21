#!/usr/bin/env python3
"""Summarise a `perf report --stdio` text report (children or self view) into hot spots and findings.

Usage: analyse_perf.py PATH... [--out DIR] [--top N]
Input:  the .report file written by `perf report --header -I --stdio > <host>.<date>.report` (see performance-data-requests.md);
        files or directories (recursed; binary files such as perf.data and files over 512 MB are skipped with a note).
        Only the top-level entry lines are read (call-graph detail is skipped), so large reports are fine. A report with several events
        (one `# Samples:` header each) is analysed once per event. The column header (Overhead/Children/Self/Samples/Command/Shared Object/Symbol)
        is read when present, so `--sort dso,sym` and `-n` reports parse; an unrecognised layout is noted and the default parse is used.
Writes: SUMMARY.md findings.json top-symbols.csv   (UTF-8)
Thresholds are the constants below; the findings state what the numbers show, not why (kernel symbols are often unresolved addresses).
The thresholds and the allocator / wrapper symbol lists are the script author's heuristics (derived from one anonymised 2015 customer
capture), not maintainer-note content, and what a MarkLogic function means is not decided here.
"""
import argparse, csv, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

MAX_BYTES = 512 * 1024 * 1024
SAMPLES_RE = re.compile(r"^# Samples: (\S+) of event '([^']+)'")
COUNT_RE = re.compile(r"^# Event count \(approx\.\): (\d+)")
ENTRY_RE = re.compile(r"^\s+(\d+\.\d+)%(?:\s+(\d+\.\d+)%)?\s+(\S+)\s+(\S+)\s+\[(.)\]\s+(.*?)\s*$")
ENTRYISH_RE = re.compile(r"^\s*\d+\.\d+%")
HEADER_RE = re.compile(r"^#\s+(?:Overhead|Children)\b")
TAIL_RE = re.compile(r"^(?:(?P<head>.*?)\s+)?\[(?P<k>.)\]\s+(?P<sym>.*?)\s*$")
NUM_COLS = ("Overhead", "Children", "Self", "Samples")
UNRESOLVED_RE = re.compile(r"^(0x[0-9a-fA-F]+|\[unknown\]|0+)$")

KERNEL_DOMINANT = 50.0        # % of all samples in kernel code of the busiest command
SYSCALL_INCLUSIVE = 25.0      # % inclusive under a user-space wrapper whose own (self) share is small
SYSCALL_SELF_MAX = 1.0
UNRESOLVED_KERNEL = 50.0      # % of kernel self time with only an address
USER_HOTSPOT = 5.0            # % self for one user-space symbol
ALLOCATOR = 5.0               # % self in allocator code
ALLOC_DSO = ("jemalloc", "tcmalloc")
ALLOC_SYMS = {"malloc", "free", "calloc", "realloc", "operator new", "operator delete"}
ALLOC_PREFIX = ("je_", "tc_", "arena_", "tcache_")
IDLE_CMDS = ("swapper", "idle")
ENTRY_POINTS = {"start_thread", "clone", "__clone", "clone3", "__libc_start_main", "__libc_start_call_main", "_start", "main"}
MAX_WRAPPERS = 2


def make_layout(line):
    """-> (entry parser or None, children_mode, note or None) from a column header line."""
    cols = [c for c in re.split(r"\s{2,}", line.lstrip("#").strip()) if c]
    num = [c for c in cols if c in NUM_COLS]
    rest = cols[len(num):]
    ok = cols[:len(num)] == num and all(c in ("Command", "Shared Object", "Symbol") for c in rest) \
        and ("Symbol" not in rest or rest[-1] == "Symbol") and ("Overhead" in num or "Self" in num)
    if not ok:
        return None, "Children" in cols, "perf report column layout not recognised; the default parse was used"
    mid = [c for c in rest if c != "Symbol"]
    pat = re.compile(r"^\s*" + r"\s+".join(r"(\d+)" if c == "Samples" else r"(\d+\.\d+)%" for c in num) + r"\s+(?P<rest>\S.*?)\s*$")

    def parse_entry(text):
        m = pat.match(text)
        t = TAIL_RE.match(m["rest"]) if m else None
        if not t:
            return None
        head = (t["head"] or "").strip()
        command = dso = "?"
        if mid == ["Command", "Shared Object"]:
            parts = re.split(r"\s{2,}", head) if head else []
            if len(parts) != 2:
                parts = head.split()
            if len(parts) != 2:
                return None
            command, dso = parts
        elif mid == ["Command"] or mid == ["Shared Object"]:
            if not head:
                return None
            command, dso = (head, "?") if mid == ["Command"] else ("?", head)
        elif head:
            return None
        vals = dict(zip((c for c in num), (float(v) if c != "Samples" else None for c, v in zip(num, m.groups()))))
        return {"children": vals.get("Children"), "self": vals.get("Self", vals.get("Overhead")), "command": command, "dso": dso,
                "kind": t["k"], "symbol": t["sym"]}
    return parse_entry, "Children" in cols, None


def default_entry(text):
    m = ENTRY_RE.match(text)
    if not m:
        return None
    children, selfp = (float(m[1]), float(m[2])) if m[2] is not None else (None, float(m[1]))
    return {"children": children, "self": selfp, "command": m[3], "dso": m[4], "kind": m[5], "symbol": m[6]}


def parse_lines(lines):
    """-> list of (meta, rows), one per `# Samples:` event header. meta["notes"] holds layout / unparsed-line notes."""
    segs = []

    def new():
        segs.append({"meta": {"samples": None, "event": None, "count": None, "children_mode": False, "notes": []},
                     "rows": [], "entry": default_entry, "layout": False, "unparsed": 0})
        return segs[-1]
    cur = new()
    for line in lines:
        if line.startswith("#"):
            m = SAMPLES_RE.match(line)
            if m:
                if cur["meta"]["samples"] is not None:
                    cur = new()
                cur["meta"]["samples"], cur["meta"]["event"] = m[1], m[2]
            m = COUNT_RE.match(line)
            if m:
                cur["meta"]["count"] = int(m[1])
            if HEADER_RE.match(line) and not cur["layout"]:
                cur["layout"] = True
                parser, children, note = make_layout(line)
                if parser:
                    cur["entry"] = parser
                if children:
                    cur["meta"]["children_mode"] = True
                if note:
                    cur["meta"]["notes"].append(note)
            elif line.startswith("# Children") or "  Children " in line:
                cur["meta"]["children_mode"] = True
            continue
        row = cur["entry"](line)
        if row:
            cur["rows"].append(row)
        elif ENTRYISH_RE.match(line):
            cur["unparsed"] += 1
    out = []
    for c in segs:
        if c["unparsed"]:
            c["meta"]["notes"].append(f"{c['unparsed']} entry lines could not be parsed")
        out.append((c["meta"], c["rows"]))
    return out


def parse_text(text):
    return parse_lines(text.splitlines())


def parse(path):
    """(meta, rows) of the first event in the report at path."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_lines(line.rstrip("\r\n") for line in fh)[0]


def collect_files(paths, notes):
    """Files to read from the inputs; adds a note for each one skipped (too large, binary, unreadable)."""
    files = []
    for p in map(Path, paths):
        if not p.exists():
            sys.exit(f"analyse_perf: path not found: {p}")
        for f in (sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]):
            try:
                if f.stat().st_size > MAX_BYTES:
                    notes.append(f"{f.name}: skipped, larger than {MAX_BYTES / 1048576:g} MB")
                    continue
                with open(f, "rb") as fh:
                    if b"\0" in fh.read(4096):
                        notes.append(f"{f.name}: skipped, binary file")
                        continue
            except OSError as e:
                notes.append(f"{f.name}: could not be read ({type(e).__name__})")
                continue
            files.append(f)
    return files


def analyse(meta, rows, top):
    total_self = sum(r["self"] for r in rows) or 1.0
    by_cmd, by_dso = Counter(), Counter()
    for r in rows:
        by_cmd[r["command"]] += r["self"]
        by_dso[r["dso"]] += r["self"]
    kernel_only = {c for c in by_cmd if all(r["kind"] == "k" for r in rows if r["command"] == c)}
    idle = lambda c: c.split("/")[0] in IDLE_CMDS or (c == "init" and c in kernel_only)
    busy = [(c, v) for c, v in by_cmd.most_common() if not idle(c)]
    target = busy[0][0] if busy else (by_cmd.most_common(1)[0][0] if by_cmd else None)
    kernel = sum(r["self"] for r in rows if r["kind"] == "k")
    t_kernel = sum(r["self"] for r in rows if r["command"] == target and r["kind"] == "k")
    t_user = sum(r["self"] for r in rows if r["command"] == target and r["kind"] != "k")
    unresolved_k = sum(r["self"] for r in rows if r["kind"] == "k" and UNRESOLVED_RE.match(r["symbol"]))
    findings = []
    if target and t_kernel >= KERNEL_DOMINANT:
        findings.append({"rule": "kernel_dominant", "severity": 0, "value": round(t_kernel, 2),
                         "detail": f"{t_kernel:.1f}% of all samples are kernel code of `{target}` (user-space code of `{target}`: {t_user:.1f}%, other commands: {total_self - t_kernel - t_user:.1f}%)"})
    if meta["children_mode"]:
        wrappers = [r for r in sorted(rows, key=lambda r: -(r["children"] or 0))
                    if (r["children"] or 0) - r["self"] >= SYSCALL_INCLUSIVE and r["self"] <= SYSCALL_SELF_MAX and r["kind"] == "."
                    and (r["dso"].startswith(("libc", "libpthread")) or r["dso"] == "[vdso]")
                    and r["symbol"].split("(")[0].strip() not in ENTRY_POINTS]
        for r in wrappers[:MAX_WRAPPERS]:
            where = (f", and kernel code of `{target}` is {t_kernel:.1f}% of samples" if t_kernel >= KERNEL_DOMINANT else "")
            findings.append({"rule": "time_under_user_wrapper", "severity": 0, "value": r["children"],
                             "detail": f"{r['children']:.1f}% of samples are under `{r['symbol']}` ({r['dso']}) but only {r['self']:.2f}% is its own code, so the time is in the functions it calls{where}"})
    if kernel and unresolved_k / kernel * 100 >= UNRESOLVED_KERNEL:
        findings.append({"rule": "unresolved_kernel_symbols", "severity": 1, "value": round(unresolved_k, 2),
                         "detail": f"{unresolved_k:.1f}% of samples are kernel addresses without a symbol name, so the kernel function cannot be named from this report; whether kernel symbols were available depends on how and where perf was run `[unverified — confirm]`"})
    users = sorted((r for r in rows if r["kind"] == "." and not UNRESOLVED_RE.match(r["symbol"])), key=lambda r: -r["self"])
    if users and users[0]["self"] >= USER_HOTSPOT:
        findings.append({"rule": "user_hotspot", "severity": 1, "value": users[0]["self"],
                         "detail": f"`{users[0]['symbol']}` ({users[0]['dso']}) is {users[0]['self']:.1f}% of samples"})
    alloc = sum(r["self"] for r in rows if any(k in r["dso"] for k in ALLOC_DSO)
                or r["symbol"].split("(")[0].strip() in ALLOC_SYMS or r["symbol"].startswith(ALLOC_PREFIX))
    if alloc >= ALLOCATOR:
        findings.append({"rule": "allocator_share", "severity": 1, "value": round(alloc, 2),
                         "detail": f"allocator code (jemalloc/tcmalloc/malloc/free/new/delete and je_/tc_/arena_/tcache_ symbols) is {alloc:.1f}% of samples"})
    findings.sort(key=lambda f: (f["severity"], -f["value"]))
    return {"total_self": total_self, "target": target, "kernel": kernel, "t_kernel": t_kernel, "t_user": t_user,
            "by_cmd": by_cmd, "by_dso": by_dso, "findings": findings,
            "top_self": sorted(rows, key=lambda r: -r["self"])[:top],
            "top_children": sorted((r for r in rows if r["children"] is not None), key=lambda r: -r["children"])[:top]}


def fmt(r, key):
    sym = r["symbol"] if len(r["symbol"]) <= 90 else r["symbol"][:87] + "..."
    return f"| {r[key]:.2f} | {r['command']} | {r['dso'][:30]} | {r['kind']} | `{sym}` |"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out")
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args(argv)
    if a.top < 1:
        ap.error("--top must be at least 1")
    notes = []
    files = collect_files(a.paths, notes)
    out = Path(a.out) if a.out else Path("perf-analysis") / Path(a.paths[0]).stem
    out.mkdir(parents=True, exist_ok=True)
    L, all_findings, csv_rows, used = ["# perf report analysis", ""], [], [], 0
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                segs = parse_lines(line.rstrip("\r\n") for line in fh)
        except OSError as e:
            notes.append(f"{f.name}: could not be read ({type(e).__name__})")
            continue
        multi = len(segs) > 1
        if multi:
            notes.append(f"{len(segs)} events in {f.name}; each event was analysed separately")
        for meta, rows in segs:
            label = f"{f.name} \u2014 {meta['event'] or '?'}" if multi else f.name
            notes += [f"{label}: {n}" for n in meta["notes"]]
            if not rows:
                notes.append(f"skipped {label}: no perf report entries")
                continue
            used += 1
            r = analyse(meta, rows, a.top)
            L += [f"## {label}", "",
                  f"Samples: {meta['samples'] or '?'} of event `{meta['event'] or '?'}`; event count {meta['count'] or '?'}; "
                  f"{'children + self view' if meta['children_mode'] else 'self view'}; {len(rows)} top-level entries; busiest command `{r['target']}`.",
                  "", "### Findings (likely cause first)", ""]
            L += [f"- **{x['rule']}**: {x['detail']}" for x in r["findings"]] or ["- No threshold was met."]
            L += ["", f"### Where the samples are (self %)", "",
                  f"- Kernel code (all commands): {r['kernel']:.1f}%; `{r['target']}` kernel {r['t_kernel']:.1f}%, `{r['target']}` user space {r['t_user']:.1f}%",
                  "- By command: " + ", ".join(f"{c} {v:.1f}%" for c, v in r["by_cmd"].most_common(5)),
                  "- By shared object: " + ", ".join(f"{d} {v:.1f}%" for d, v in r["by_dso"].most_common(6)), "",
                  f"### Top {a.top} by self", "", "| Self % | Command | Shared object | K/U | Symbol |", "| --- | --- | --- | --- | --- |"]
            L += [fmt(x, "self") for x in r["top_self"]]
            if r["top_children"]:
                L += ["", f"### Top {a.top} by inclusive (children) %", "", "| Children % | Command | Shared object | K/U | Symbol |", "| --- | --- | --- | --- | --- |"]
                L += [fmt(x, "children") for x in r["top_children"]]
            L.append("")
            all_findings += [{**x, "input": label} for x in r["findings"]]
            csv_rows += [{"input": label, **x} for x in sorted(rows, key=lambda x: -x["self"])[:200]]
    if not used:
        sys.exit("analyse_perf: no perf report entries found (expected `perf report --stdio` text with lines like '  12.34%  0.56%  Command  Shared  [k] symbol').")
    L += ["## How to read this", "",
          "- `perf` samples the process (statistical, lighter than pstack). Self % is time in that symbol itself; children % includes the functions it calls.",
          f"- Thresholds: kernel-dominant {KERNEL_DOMINANT:g}%, time under a user wrapper {SYSCALL_INCLUSIVE:g}% inclusive with at most {SYSCALL_SELF_MAX:g}% self, unresolved kernel {UNRESOLVED_KERNEL:g}%, user hotspot {USER_HOTSPOT:g}%, allocator {ALLOCATOR:g}%.",
          "- What a MarkLogic function means, and why the kernel is busy, is not decided by this tool `[unverified — confirm]`."]
    if notes:
        L += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    (out / "SUMMARY.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (out / "findings.json").write_text(json.dumps(all_findings, indent=2) + "\n", encoding="utf-8")
    with (out / "top-symbols.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["input", "children", "self", "command", "dso", "kind", "symbol"]); w.writeheader()
        w.writerows(csv_rows)
    print(f"wrote {out}: {used} report(s), {len(all_findings)} finding(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
