#!/usr/bin/env python3
"""Summarise `perf report --stdio` text reports (children or self view) into hot spots and findings, and inventory raw perf.data files.

Usage: analyse_perf.py PATH... [--out DIR] [--top N] [--convert]
Input:  the .report file written by `perf report --header -I --stdio > <host>.<date>.report` (see performance-data-requests.md);
        files, folders and zips (zips in zips too, one file per node; see diag_inputs.py: nothing is extracted to disk, macOS junk and
        duplicate copies are skipped, files over 512 MB and other binary files are skipped with a note).
        A RAW perf.data (magic PERFILE2) is recognised by content: its file header is parsed in pure Python (host, kernel, CPUs, memory,
        capture command, events, sample window) and listed in an inventory. Samples cannot be read without a local `perf`: only with
        --convert is `perf report -i <temp copy> --stdio` run (no shell, 600 s timeout, output capped at 512 MB; the copy is a 0600 file
        in a private temp dir removed afterwards; perf runs in its own session and the whole process group is killed at the end, on a timeout,
        on the cap and on an error or Ctrl-C; a `perf` found at a relative PATH entry or inside the current directory or an input folder is
        not run) and its text analysed like a report. --convert runs an external tool on customer data,
        so it is never the default. Without --convert a note gives the exact command to run on a Linux host instead.
        With more than one input SUMMARY.md starts with a per-host overview table (also hosts.csv).
        Only the top-level entry lines are read (call-graph detail is skipped), so large reports are fine. A report with several events
        (one `# Samples:` header each) is analysed once per event. The column header (Overhead/Children/Self/Samples/Command/Shared Object/Symbol)
        is read when present, so `--sort dso,sym` and `-n` reports parse; an unrecognised layout is noted and the default parse is used.
Names and header strings from the input are made safe for markdown and CSV (diag_inputs.safe_label / csv_cell). With more than 20 analysed
inputs the per-input sections are printed only for inputs with a finding (the overview table and top-symbols.csv hold all of them).
Memory: a report or perf.data is read whole into memory, so a very large file (hundreds of MB) can need several GB of RAM `[unverified — confirm]`.
Writes: SUMMARY.md findings.json top-symbols.csv (hosts.csv with several inputs)   (UTF-8)
Thresholds are the constants below; the findings state what the numbers show, not why (kernel symbols are often unresolved addresses).
The thresholds and the allocator / wrapper symbol lists are the script author's heuristics (derived from one anonymised 2015 customer
capture), not maintainer-note content, and what a MarkLogic function means is not decided here.
"""
import argparse, csv, json, os, re, shutil, signal, struct, subprocess, sys, tempfile, time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diag_inputs

SEP = diag_inputs.SEP
S = diag_inputs.safe_label
MAX_SECTIONS = 20
PERF_MAGIC = b"PERFILE2"
CONVERT_TIMEOUT = 600
CONVERT_MAX = 512 * 1024 * 1024
MAX_FEATURE = 1024 * 1024
SNIFF = 64 * 1024
CONVERTED = " (converted with local perf)"
TEXT_HDR_RE = re.compile(r"^# (hostname|os release|nrcpus online|total memory|cmdline)\s*:\s*(.*?)\s*$")
GI_RE = re.compile(r"^_{1,2}GI_")
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
                cur["meta"]["samples"], cur["meta"]["event"] = S(m[1], 40), S(m[2], 80)
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
            for k in ("command", "dso", "symbol"):
                row[k] = S(row[k], 300)
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
                    and GI_RE.sub("", r["symbol"].split("(")[0].strip()) not in ENTRY_POINTS]
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


def _u32(buf, pos):
    return struct.unpack_from("<I", buf, pos)[0]


def _string(buf, pos):
    """A perf string (u32 length, bytes NUL padded) -> (text, next position); ValueError when it runs past the section."""
    n = _u32(buf, pos)
    if pos + 4 + n > len(buf):
        raise ValueError("string runs past its section")
    return buf[pos + 4:pos + 4 + n].split(b"\0", 1)[0].decode("utf-8", errors="replace"), pos + 4 + n


def read_perf_header(data):
    """Facts from the file header of a raw perf.data (PERFILE2, little endian); ValueError when it cannot be read.
    -> dict: hostname osrelease version arch cpus cpus_online cpudesc mem_kb cmdline events window_s data_size (None / [] when absent)."""
    try:
        if data[:8] != PERF_MAGIC:
            raise ValueError("not a perf.data file (magic is not PERFILE2)")
        _, _, _, _, _, data_off, data_size, _, _ = struct.unpack_from("<9Q", data, 0)
        bitmap = struct.unpack_from("<4Q", data, 72)
        if data_off + data_size > len(data):
            raise ValueError("perf.data is truncated or its sizes are implausible")
        feats = [i for i in range(256) if bitmap[i // 64] >> (i % 64) & 1]
        h = {"hostname": None, "osrelease": None, "version": None, "arch": None, "cpus": None, "cpus_online": None, "cpudesc": None,
             "mem_kb": None, "cmdline": [], "events": [], "window_s": None, "data_size": data_size}
        table = data_off + data_size
        for k, feat in enumerate(feats):
            if table + 16 * (k + 1) > len(data):
                break   # bitmap bits without a table entry
            off, size = struct.unpack_from("<QQ", data, table + 16 * k)
            if size > MAX_FEATURE or off + size > len(data) or feat not in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 21):
                continue
            sec = data[off:off + size]
            if feat in (3, 4, 5, 6, 8):
                h[{3: "hostname", 4: "osrelease", 5: "version", 6: "arch", 8: "cpudesc"}[feat]] = S(_string(sec, 0)[0])
            elif feat == 7:
                h["cpus"], h["cpus_online"] = struct.unpack_from("<II", sec, 0)
            elif feat == 10:
                h["mem_kb"] = struct.unpack_from("<Q", sec, 0)[0]
            elif feat == 11:
                pos = 4
                for _ in range(_u32(sec, 0)):
                    t, pos = _string(sec, pos)
                    h["cmdline"].append(S(t))
            elif feat == 12:
                n, attr_size = struct.unpack_from("<II", sec, 0)
                pos = 8
                for _ in range(n):
                    nr_ids = _u32(sec, pos + attr_size)
                    name, pos = _string(sec, pos + attr_size + 4)
                    pos += 8 * nr_ids
                    if pos > len(sec):
                        raise ValueError("event description runs past its section")
                    h["events"].append(S(name))
            elif feat == 21:
                start, end = struct.unpack_from("<QQ", sec, 0)
                h["window_s"] = (end - start) / 1e9 if end >= start else None
        return h
    except (struct.error, IndexError, OverflowError, MemoryError) as e:
        raise ValueError(f"unreadable perf.data header ({type(e).__name__})") from e


def classify(head):
    """'perf.data' | 'report' | 'binary' | None (not perf data) from the first bytes of a source."""
    if head.startswith(PERF_MAGIC):
        return "perf.data"
    if b"\0" in head[:4096]:
        return "binary"
    text = head.decode("utf-8", errors="replace")
    if "# Samples:" in text or any(ENTRYISH_RE.match(line) for line in text.splitlines()):
        return "report"
    return None


def text_header(text):
    """Header facts from the `# hostname : ...` comment lines of a `perf report --header` text (kernel, cpus, mem_kb, cmdline)."""
    out = {}
    for line in text[:200000].splitlines():
        m = TEXT_HDR_RE.match(line)
        if m:
            out[m[1]] = m[2]
        elif line and not line.startswith("#"):
            break
    mem = re.match(r"(\d+)\s*kB", out.get("total memory", ""))
    cpus = re.match(r"(\d+)", out.get("nrcpus online", ""))
    return {"osrelease": S(out["os release"]) if "os release" in out else None, "cpus": int(cpus[1]) if cpus else None,
            "mem_kb": int(mem[1]) if mem else None, "cmdline": S(out["cmdline"]) if "cmdline" in out else None}


def find_perf(roots, notes):
    """The `perf` to run, or None with a note: not installed, or found at a relative PATH entry / inside the current directory or an input folder."""
    perf = shutil.which("perf")
    if perf is None:
        notes.add(NO_PERF_NOTE)
        return None
    trusted = os.path.isabs(perf)
    if trusted:
        real = os.path.realpath(perf)
        for r in [os.getcwd(), *roots]:
            r = os.path.realpath(r)
            if real == r or real.startswith(r.rstrip(os.sep) + os.sep):
                trusted = False
    if not trusted:
        notes.add(UNTRUSTED_PERF_NOTE)
        return None
    return perf


def kill_session(proc):
    """SIGKILL perf's whole process group (it was started in its own session), then reap it; safe to call twice."""
    try:
        if hasattr(os, "killpg"):
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except OSError:       # ProcessLookupError (nothing left), PermissionError
        pass
    proc.wait()


def convert_with_perf(data, label, notes, roots=()):
    """Run the local `perf report -i <private temp copy> --stdio` on raw perf.data bytes -> text, or None with a note."""
    perf = find_perf(roots, notes)
    if perf is None:
        return None
    with tempfile.TemporaryDirectory(prefix="analyse-perf-") as d:
        src, outp = os.path.join(d, "perf.data"), os.path.join(d, "report.txt")
        fd = os.open(src, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        status, rc = "ok", None
        try:
            with open(outp, "wb") as of:
                proc = subprocess.Popen([perf, "report", "-i", src, "--stdio"], stdin=subprocess.DEVNULL, stdout=of, stderr=subprocess.DEVNULL,
                                        start_new_session=True)
                try:
                    deadline = time.monotonic() + CONVERT_TIMEOUT
                    while True:
                        try:
                            rc = proc.wait(timeout=max(0.01, min(0.1, deadline - time.monotonic())))
                            break
                        except subprocess.TimeoutExpired:
                            pass
                        if os.path.getsize(outp) > CONVERT_MAX:
                            status = "cap"
                        elif time.monotonic() >= deadline:
                            status = "timeout"
                        if status != "ok":
                            break
                finally:
                    kill_session(proc)
        except OSError as e:
            notes.add(f"{label}: conversion with local perf failed ({type(e).__name__})")
            return None
        if status == "ok" and os.path.getsize(outp) > CONVERT_MAX:
            status = "cap"
        if status == "cap":
            notes.add(f"{label}: perf report output larger than {CONVERT_MAX / 1048576:g} MB, conversion stopped")
        elif status == "timeout":
            notes.add(f"{label}: conversion with local perf timed out after {CONVERT_TIMEOUT:g} s")
        elif rc != 0:
            notes.add(f"{label}: conversion with local perf failed (exit {rc})")
        else:
            with open(outp, "rb") as fh:
                return fh.read().decode("utf-8", errors="replace")
    return None


UNTRUSTED_PERF_NOTE = "perf found at a relative/untrusted PATH entry; not run"
NO_PERF_NOTE = ("perf not installed here: raw perf.data cannot be analysed; run on a Linux host with the same perf: `perf report -i <file> --stdio`, "
                "or ask for the text report from the request in references/performance-data-requests.md")
RAW_NOTE = ("{n} raw perf.data file(s): only the file header is read here; the samples need `perf report -i <file> --stdio` run on a Linux host with the same perf "
            "(kernel and MarkLogic symbols may not resolve on a different host from the one that recorded the data `[unverified — confirm]`), "
            "or the text report from the request in references/performance-data-requests.md; `--convert` runs the local `perf` on customer data")


def fmt(r, key):
    sym = r["symbol"] if len(r["symbol"]) <= 90 else r["symbol"][:87] + "..."
    return f"| {r[key]:.2f} | {r['command']} | {r['dso'][:30]} | {r['kind']} | `{sym}` |"


def section(e, top, full):
    meta, rows, r, label = e["meta"], e["rows"], e["r"], e["label"]
    L = [f"## {label}", "",
         f"Samples: {meta['samples'] or '?'} of event `{meta['event'] or '?'}`; event count {meta['count'] or '?'}; "
         f"{'children + self view' if meta['children_mode'] else 'self view'}; {len(rows)} top-level entries; busiest command `{r['target']}`.",
         "", "### Findings (likely cause first)", ""]
    L += [f"- **{x['rule']}**: {x['detail']}" for x in r["findings"]] or ["- No threshold was met."]
    L += ["", "### Where the samples are (self %)", "",
          f"- Kernel code (all commands): {r['kernel']:.1f}%; `{r['target']}` kernel {r['t_kernel']:.1f}%, `{r['target']}` user space {r['t_user']:.1f}%",
          "- By command: " + ", ".join(f"{c} {v:.1f}%" for c, v in r["by_cmd"].most_common(5)),
          "- By shared object: " + ", ".join(f"{d} {v:.1f}%" for d, v in r["by_dso"].most_common(6)), ""]
    if full:
        L += [f"### Top {top} by self", "", "| Self % | Command | Shared object | K/U | Symbol |", "| --- | --- | --- | --- | --- |"]
        L += [fmt(x, "self") for x in r["top_self"]]
        if r["top_children"]:
            L += ["", f"### Top {top} by inclusive (children) %", "", "| Children % | Command | Shared object | K/U | Symbol |", "| --- | --- | --- | --- | --- |"]
            L += [fmt(x, "children") for x in r["top_children"]]
        L.append("")
    return L


def inventory_block(label, h):
    gib = f"{h['mem_kb'] / 1048576:.1f} GiB" if h["mem_kb"] else "?"
    cpus = f"{h['cpus']} ({h['cpus_online']} online)" if h["cpus"] is not None else "?"
    return [f"## {label}", "", "### perf.data header (raw file, samples not read)", "",
            f"- Host: {h['hostname'] or '?'}", f"- Kernel: {h['osrelease'] or '?'}; architecture {h['arch'] or '?'}",
            f"- CPUs: {cpus}; {h['cpudesc'] or '?'}", f"- Memory: {gib}",
            f"- Capture command: `{' '.join(h['cmdline']) or '?'}`", "- Events: " + (", ".join(f"`{x}`" for x in h["events"]) or "?"),
            f"- Sample window: {h['window_s']:g} s" if h["window_s"] is not None else "- Sample window: ?",
            f"- Sample data in the file: {h['data_size']} bytes", ""]


HOST_COLS = ["host", "input_kind", "kernel", "cpus", "memory_gib", "window_s", "capture_command", "analysed", "kernel_share", "top_finding", "label"]


def host_row(x):
    h = x["header"] or {}
    cmd = h.get("cmdline") or ""
    cmd = " ".join(cmd) if isinstance(cmd, list) else cmd
    mem = h.get("mem_kb")
    w = h.get("window_s")
    r = x["result"]
    cpus = h.get("cpus_online") if x["kind"] == "perf.data" else h.get("cpus")
    return {"host": x["host"], "input_kind": x["kind"], "kernel": h.get("osrelease") or "-", "cpus": cpus if cpus is not None else "-",
            "memory_gib": f"{mem / 1048576:.1f}" if mem else "-", "window_s": f"{w:g}" if w is not None else "-", "capture_command": cmd or "-",
            "analysed": "yes" if r else "no", "kernel_share": f"{r['t_kernel']:.1f}" if r else "-",
            "top_finding": (r["findings"][0]["rule"] if r["findings"] else "-") if r else "-", "label": x["label"],
            "_sev0": bool(r) and any(f["severity"] == 0 for f in r["findings"])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--convert", action="store_true",
                    help="run the local `perf report -i <copy> --stdio` on raw perf.data files (an external tool on customer data)")
    a = ap.parse_args(argv)
    if a.top < 1:
        ap.error("--top must be at least 1")
    notes = set()
    try:
        sources = diag_inputs.walk(a.paths, notes)
    except FileNotFoundError as e:
        sys.exit(f"analyse_perf: path not found: {e.filename}")
    try:
        return run(a, sources, notes)
    finally:
        diag_inputs.close_all(sources)


def run(a, sources, notes):
    keep, skipped, binary = [], 0, 0
    roots = [str(p) for p in a.paths if os.path.isdir(p)]
    for src in sources:
        try:
            kind = classify(src.head(SNIFF))
        except diag_inputs.READ_ERRORS as e:
            notes.add(f"{src.label}: could not be read ({type(e).__name__})")
            continue
        if kind == "binary":
            binary += 1
        elif kind is None:
            skipped += 1
        else:
            keep.append(src)
    if binary:
        notes.add(f"{binary} binary file(s) skipped")
    if skipped:
        notes.add(f"{skipped} file(s) skipped, not a perf report (no `# Samples:` header or entry lines)")
    try:
        keep = diag_inputs.dedupe(keep, notes)
    except diag_inputs.READ_ERRORS as e:
        notes.add(f"duplicate check failed ({type(e).__name__}); duplicates not removed")
    infos, sections, all_findings, csv_rows, used, raw = [], [], [], [], 0, 0
    for src in keep:
        try:
            data = src.read()
        except diag_inputs.READ_ERRORS as e:
            notes.add(f"{src.label}: could not be read ({type(e).__name__})")
            continue
        info = {"label": src.label, "host": None, "kind": "report", "header": None, "result": None, "usable": False}
        text, label = None, src.label
        if data.startswith(PERF_MAGIC):
            raw += 1
            info["kind"] = "perf.data"
            try:
                hdr = read_perf_header(data)
                if hdr["hostname"] or hdr["cmdline"] or hdr["events"] or hdr["window_s"] is not None:
                    info["header"], info["usable"], info["host"] = hdr, True, hdr["hostname"]
                else:
                    notes.add(f"{src.label}: perf.data header has no usable fields")
            except ValueError:
                notes.add(f"{src.label}: unreadable perf.data header")
            if a.convert:
                text, label = convert_with_perf(data, src.label, notes, roots), src.label + CONVERTED
        else:
            text = data.decode("utf-8", errors="replace")
            info["header"] = text_header(text)
        info["host"] = S(info["host"] or diag_inputs.host_hint(src) or SEP.join(src.parts[-2:]))
        info["src_label"] = src.label
        if text is not None:
            segs = parse_lines(text.splitlines())
            multi = len(segs) > 1
            if multi:
                notes.add(f"{len(segs)} events in {label}; each event was analysed separately")
            for meta, rows in segs:
                elabel = f"{label} \u2014 {meta['event'] or '?'}" if multi else label
                for n in meta["notes"]:
                    notes.add(f"{elabel}: {n}")
                if not rows:
                    notes.add(f"skipped {elabel}: no perf report entries")
                    continue
                used += 1
                info["usable"] = True
                r = analyse(meta, rows, a.top)
                sections.append({"label": elabel, "meta": meta, "rows": rows, "r": r})
                info["result"] = info["result"] or r
                all_findings += [{**x, "input": elabel} for x in r["findings"]]
                csv_rows += [{k: diag_inputs.csv_cell(v) for k, v in {"input": elabel, **x}.items()}
                             for x in sorted(rows, key=lambda x: -x["self"])[:200]]
        infos.append(info)
    if raw:
        notes.add(RAW_NOTE.format(n=raw))
    if not any(i["usable"] for i in infos):
        diag_inputs.print_notes(notes)
        sys.exit("analyse_perf: no perf report entries found (expected `perf report --stdio` text with lines like '  12.34%  0.56%  Command  Shared  [k] symbol', "
                 "or a raw perf.data).")
    out = Path(a.out) if a.out else Path("perf-analysis") / Path(a.paths[0]).stem
    out.mkdir(parents=True, exist_ok=True)
    usable = [i for i in infos if i["usable"]]
    diag_inputs.disambiguate(usable)
    many = len(usable) > 1
    shown = sections
    L = ["# perf report analysis", ""]
    if many:
        hosts = sorted((host_row(i) for i in infos if i["usable"]), key=lambda h: (not h["_sev0"], h["host"].lower(), h["label"]))
        with (out / "hosts.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=HOST_COLS); w.writeheader()
            for h in hosts:
                w.writerow({c: diag_inputs.csv_cell(h[c]) for c in HOST_COLS})
        short = lambda c: c if len(c) <= 40 else c[:37] + "..."
        L += ["## Hosts", "", "| Host | Input kind | Kernel | CPUs | Memory (GiB) | Window (s) | Capture command | Analysed | Kernel share of target command (%) | Top finding |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        L += [f"| {h['host']} | {h['input_kind']} | {h['kernel']} | {h['cpus']} | {h['memory_gib']} | {h['window_s']} | {short(h['capture_command'])} | "
              f"{h['analysed']} | {h['kernel_share']} | {h['top_finding']} |" for h in hosts]
        L += ["", "Hosts with a severity-0 finding come first. Kernel share is the kernel part of the busiest command, in % of all samples. "
                  "CPUs is the online CPU count (for a perf.data the header's online count, as in the text report header). "
                  "Raw perf.data rows show header facts only unless converted. The captures are not simultaneous `[unverified — confirm]`.", ""]
        if len(usable) > MAX_SECTIONS:
            shown = [e for e in sections if e["r"]["findings"]]
            L += [f"More than {MAX_SECTIONS} inputs: per-input sections are shown only for the {len({e['label'] for e in shown})} input(s) with at least one "
                  "finding; all inputs are in the table above and in top-symbols.csv and findings.json.", ""]
        diff = [what for what, vals in (("kernel versions differ", {h["kernel"] for h in hosts} - {"-"}),
                                         ("capture commands differ", {h["capture_command"] for h in hosts} - {"-"})) if len(vals) > 1]
        if diff:
            notes.add("the nodes were not captured the same way: " + "; ".join(diff) + " (compare them with care)")
    elif raw and usable and usable[0]["kind"] == "perf.data" and usable[0]["header"]:
        L += inventory_block(usable[0]["label"], usable[0]["header"])
    for i, e in enumerate(shown):
        L += section(e, a.top, not many or i == 0)
    if many and len(shown) > 1:
        L += ["Top-symbol tables of the inputs after the first are not repeated here; their rows are in top-symbols.csv.", ""]
    L += ["## How to read this", "",
          "- `perf` samples the process (statistical, lighter than pstack). Self % is time in that symbol itself; children % includes the functions it calls.",
          f"- Thresholds: kernel-dominant {KERNEL_DOMINANT:g}%, time under a user wrapper {SYSCALL_INCLUSIVE:g}% inclusive with at most {SYSCALL_SELF_MAX:g}% self, unresolved kernel {UNRESOLVED_KERNEL:g}%, user hotspot {USER_HOTSPOT:g}%, allocator {ALLOCATOR:g}%.",
          "- What a MarkLogic function means, and why the kernel is busy, is not decided by this tool `[unverified — confirm]`."]
    if notes:
        L += ["", "## Notes", ""] + [f"- {n}" for n in sorted(notes)]
    (out / "SUMMARY.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (out / "findings.json").write_text(json.dumps(all_findings, indent=2) + "\n", encoding="utf-8")
    with (out / "top-symbols.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["input", "children", "self", "command", "dso", "kind", "symbol"]); w.writeheader()
        w.writerows(csv_rows)
    inv = sum(1 for i in infos if i["kind"] == "perf.data" and i["header"] is not None)
    print(f"wrote {out}: {used} report(s), {len(all_findings)} finding(s)" + (f", {inv} perf.data header(s)" if inv else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
