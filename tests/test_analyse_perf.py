import contextlib, csv, io, json, os, struct, subprocess, sys, tempfile, unittest, zipfile
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/marklogic-support/scripts/analyse_perf.py"
FIX = Path(__file__).with_name("fixture_perf") / "perf-report-sample.txt"
sys.path.insert(0, str(SCRIPT.parent))
import analyse_perf as ap
import diag_inputs


def run_main(args, path=None):
    """In-process main(); -> (exit code or SystemExit text, stdout). `path` replaces PATH for the call."""
    buf = io.StringIO()
    env = {"PATH": path} if path is not None else {}
    with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(buf):
        try:
            rc = ap.main([str(a) for a in args])
        except SystemExit as e:
            rc = e.code
    return rc, buf.getvalue()


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


HEAD = "# Samples: 10K of event 'cpu-clock'\n# Event count (approx.): 100000000000\n#\n"
CHILDREN = HEAD + "# Children      Self    Command  Shared Object  Symbol\n# ........  ........  .........  ............  ......\n#\n"
SELF_ONLY = HEAD + "# Overhead  Command  Shared Object  Symbol\n# ........  .........  ............  ......\n#\n"


def children_report(entries):
    return CHILDREN + "".join(f"    {c:5.2f}%  {s:5.2f}%  {cmd}  {dso}  [{k}] {sym}\n            |\n            --- {sym}\n\n"
                              for c, s, cmd, dso, k, sym in entries)


def self_report(entries):
    return SELF_ONLY + "".join(f"    {s:5.2f}%  {cmd}  {dso}  [{k}] {sym}\n" for s, cmd, dso, k, sym in entries)


class ParseTest(unittest.TestCase):
    def write(self, text):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        p = Path(self.tmp.name) / "r.txt"; p.write_text(text); return p

    def test_children_view_header_and_entries(self):
        meta, rows = ap.parse(self.write(children_report([(66.5, 0.01, "MarkLogic", "libc-2.12.so", ".", "madvise")])))
        self.assertEqual((meta["samples"], meta["event"], meta["count"], meta["children_mode"]), ("10K", "cpu-clock", 100000000000, True))
        self.assertEqual(rows[0], {"children": 66.5, "self": 0.01, "command": "MarkLogic", "dso": "libc-2.12.so", "kind": ".", "symbol": "madvise"})

    def test_self_only_view_has_no_children_values(self):
        meta, rows = ap.parse(self.write(self_report([(40.0, "MarkLogic", "MarkLogic", ".", "xdmp::Foo::bar(unsigned int)")])))
        self.assertFalse(meta["children_mode"])
        self.assertEqual((rows[0]["children"], rows[0]["self"], rows[0]["symbol"]), (None, 40.0, "xdmp::Foo::bar(unsigned int)"))

    def test_callgraph_lines_are_not_entries(self):
        _, rows = ap.parse(self.write(children_report([(10.0, 1.0, "A", "a.so", ".", "f"), (5.0, 2.0, "B", "b.so", ".", "g")])))
        self.assertEqual([r["symbol"] for r in rows], ["f", "g"])


class LayoutTest(unittest.TestCase):
    def seg(self, text):
        segs = ap.parse_text(text)
        self.assertEqual(len(segs), 1)
        return segs[0]

    def test_sort_dso_sym_has_no_command_column(self):
        text = HEAD + "# Overhead  Shared Object  Symbol\n# ........  ............  ......\n#\n" \
            "    40.00%  libc-2.12.so  [.] madvise\n    10.00%  [kernel.kallsyms]  [k] 0xffffffff81000000\n"
        meta, rows = self.seg(text)
        self.assertEqual([(r["command"], r["dso"], r["kind"], r["symbol"], r["self"]) for r in rows],
                         [("?", "libc-2.12.so", ".", "madvise", 40.0), ("?", "[kernel.kallsyms]", "k", "0xffffffff81000000", 10.0)])
        self.assertEqual(meta["notes"], [])

    def test_samples_column_from_dash_n(self):
        text = HEAD + "# Children      Self       Samples  Command  Shared Object  Symbol\n#\n" \
            "    66.49%     0.01%         63175  MarkLogic  libc-2.12.so  [.] madvise\n"
        meta, rows = self.seg(text)
        self.assertTrue(meta["children_mode"])
        self.assertEqual((rows[0]["children"], rows[0]["self"], rows[0]["command"], rows[0]["dso"], rows[0]["symbol"]),
                         (66.49, 0.01, "MarkLogic", "libc-2.12.so", "madvise"))
        text = HEAD + "# Overhead       Samples  Command  Shared Object  Symbol\n#\n    40.00%         4000  ML  ML  [.] f\n"
        self.assertEqual(self.seg(text)[1][0]["self"], 40.0)

    def test_command_with_a_space_is_parsed_from_the_columns(self):
        text = SELF_ONLY + "    40.00%  Web Content  libxul.so  [.] f\n"
        _, rows = self.seg(text)
        self.assertEqual((rows[0]["command"], rows[0]["dso"]), ("Web Content", "libxul.so"))

    def test_unrecognised_header_falls_back_with_a_note(self):
        text = HEAD + "# Overhead  Source:Line  Command  Shared Object  Symbol\n#\n    40.00%  ML  libc.so  [.] f\n"
        meta, rows = self.seg(text)
        self.assertTrue(any("layout" in n and "not recognised" in n for n in meta["notes"]), meta["notes"])
        self.assertEqual(rows[0]["symbol"], "f")

    def test_unparsed_entry_lines_are_counted(self):
        text = SELF_ONLY + "    40.00%  ML  libc.so  [.] f\n    12.00%  this line is not an entry\n     3.00%  ML\n"
        meta, rows = self.seg(text)
        self.assertEqual(len(rows), 1)
        self.assertIn("2 entry lines could not be parsed", meta["notes"])

    def test_two_events_are_split_at_each_samples_header(self):
        text = ("# Samples: 10K of event 'cpu-clock'\n# Event count (approx.): 1\n#\n# Overhead  Command  Shared Object  Symbol\n#\n"
                "    40.00%  ML  ML  [.] f\n# Samples: 2K of event 'page-faults'\n# Event count (approx.): 2\n#\n"
                "# Overhead  Command  Shared Object  Symbol\n#\n    70.00%  ML  ML  [.] g\n")
        segs = ap.parse_text(text)
        self.assertEqual([(m["event"], m["samples"], [r["symbol"] for r in rows]) for m, rows in segs],
                         [("cpu-clock", "10K", ["f"]), ("page-faults", "2K", ["g"])])


class RuleTest(unittest.TestCase):
    def findings(self, rows, children=True):
        meta = {"children_mode": children}
        r = ap.analyse(meta, rows, 5)
        return {f["rule"]: f for f in r["findings"]}, r

    def row(self, children, self_, cmd, dso, kind, sym):
        return {"children": children, "self": self_, "command": cmd, "dso": dso, "kind": kind, "symbol": sym}

    def test_kernel_dominant_and_wrapper_and_unresolved(self):
        rows = [self.row(66.0, 0.01, "ML", "libc-2.12.so", ".", "madvise"), self.row(60.0, 60.0, "ML", "[kernel.kallsyms]", "k", "0xffffffff81036c36"),
                self.row(10.0, 10.0, "ML", "ML", ".", "xdmp::Foo::bar()"), self.row(20.0, 20.0, "idle", "[kernel.kallsyms]", "k", "0xffffffff8104301b")]
        f, r = self.findings(rows)
        self.assertEqual(set(f), {"kernel_dominant", "time_under_user_wrapper", "unresolved_kernel_symbols", "user_hotspot"})
        self.assertEqual(r["target"], "ML")
        self.assertAlmostEqual(r["t_kernel"], 60.0)

    def test_resolved_kernel_symbols_are_not_flagged_unresolved(self):
        rows = [self.row(None, 70.0, "ML", "[kernel.kallsyms]", "k", "_raw_spin_lock"), self.row(None, 5.0, "ML", "ML", ".", "f()")]
        f, _ = self.findings(rows, children=False)
        self.assertIn("kernel_dominant", f)
        self.assertNotIn("unresolved_kernel_symbols", f)
        self.assertNotIn("time_under_user_wrapper", f)

    def test_allocator_share_counts_jemalloc_and_malloc_family(self):
        rows = [self.row(None, 3.0, "ML", "libjemalloc.so.1", ".", "arena_dalloc"), self.row(None, 3.0, "ML", "libc-2.12.so", ".", "free"),
                self.row(None, 40.0, "ML", "ML", ".", "x()")]
        f, _ = self.findings(rows, children=False)
        self.assertAlmostEqual(f["allocator_share"]["value"], 6.0)

    def test_thread_entry_points_are_not_wrappers_but_a_real_wrapper_is(self):
        rows = [self.row(95.0, 0.0, "ML", "libpthread-2.12.so", ".", "start_thread"), self.row(95.0, 0.0, "ML", "libc-2.12.so", ".", "__clone"),
                self.row(95.0, 0.0, "ML", "libc-2.12.so", ".", "clone"), self.row(95.0, 0.0, "ML", "libc-2.12.so", ".", "__libc_start_main"),
                self.row(95.0, 0.0, "ML", "ML", ".", "main"), self.row(95.0, 0.0, "ML", "ML", ".", "_start"),
                self.row(60.0, 0.01, "ML", "libc-2.12.so", ".", "madvise"),
                self.row(60.0, 60.0, "ML", "[kernel.kallsyms]", "k", "0xffffffff81036c36")]
        _, r = self.findings(rows)
        wr = [f for f in r["findings"] if f["rule"] == "time_under_user_wrapper"]
        self.assertEqual(len(wr), 1)
        self.assertIn("`madvise`", wr[0]["detail"])
        self.assertIn("kernel", wr[0]["detail"])

    def test_at_most_two_wrappers_and_no_kernel_claim_without_kernel_time(self):
        rows = [self.row(60.0 - i, 0.0, "ML", "libc-2.12.so", ".", f"wrap{i}") for i in range(3)] + [self.row(30.0, 30.0, "ML", "ML", ".", "f()")]
        _, r = self.findings(rows)
        wr = [f for f in r["findings"] if f["rule"] == "time_under_user_wrapper"]
        self.assertEqual([f["detail"].split("`")[1] for f in wr], ["wrap0", "wrap1"])
        self.assertIn("in the functions it calls", wr[0]["detail"])
        self.assertNotIn("kernel", wr[0]["detail"])

    def test_idle_commands_are_not_the_target(self):
        rows = [self.row(None, 50.0, "swapper", "[kernel.kallsyms]", "k", "default_idle"), self.row(None, 8.0, "idle", "[kernel.kallsyms]", "k", "x"),
                self.row(None, 20.0, "ML", "[kernel.kallsyms]", "k", "0xffffffff81036c36"), self.row(None, 10.0, "ML", "ML", ".", "f()"),
                self.row(None, 12.0, "init", "[kernel.kallsyms]", "k", "y")]
        _, r = self.findings(rows, children=False)
        self.assertEqual(r["target"], "ML")
        rows = [self.row(None, 50.0, "swapper", "[kernel.kallsyms]", "k", "default_idle"), self.row(None, 12.0, "init", "init", ".", "f()"),
                self.row(None, 15.0, "init", "[kernel.kallsyms]", "k", "y")]
        _, r = self.findings(rows, children=False)
        self.assertEqual(r["target"], "init")
        rows = [self.row(None, 50.0, "swapper", "[kernel.kallsyms]", "k", "default_idle")]
        _, r = self.findings(rows, children=False)
        self.assertEqual(r["target"], "swapper")

    def test_allocator_share_counts_prefixed_symbols(self):
        rows = [self.row(None, 2.0, "ML", "ML", ".", "je_malloc"), self.row(None, 2.0, "ML", "ML", ".", "tc_free"),
                self.row(None, 1.0, "ML", "ML", ".", "arena_purge"), self.row(None, 1.0, "ML", "ML", ".", "tcache_bin_flush_small"),
                self.row(None, 40.0, "ML", "ML", ".", "x()")]
        f, _ = self.findings(rows, children=False)
        self.assertAlmostEqual(f["allocator_share"]["value"], 6.0)

    def test_nothing_flagged_for_a_flat_profile(self):
        rows = [self.row(None, 2.0, "ML", "ML", ".", f"f{i}()") for i in range(10)]
        f, _ = self.findings(rows, children=False)
        self.assertEqual(f, {})


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.out = Path(cls.tmp.name) / "out"
        r = run(FIX, "--out", cls.out)
        assert r.returncode == 0, r.stderr
        cls.stdout = r.stdout
        cls.findings = {f["rule"]: f for f in json.loads((cls.out / "findings.json").read_text())}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_madvise_dominates_and_is_kernel_time(self):
        self.assertEqual(set(self.findings), {"kernel_dominant", "time_under_user_wrapper", "unresolved_kernel_symbols"})
        self.assertAlmostEqual(self.findings["time_under_user_wrapper"]["value"], 66.49)
        self.assertIn("`madvise`", self.findings["time_under_user_wrapper"]["detail"])
        self.assertGreater(self.findings["kernel_dominant"]["value"], 60)

    def test_summary_tables_and_limits(self):
        s = (self.out / "SUMMARY.md").read_text()
        for needle in ("Samples: 95K of event `cpu-clock`", "children + self view", "busiest command `MarkLogic`", "### Top 15 by self",
                       "### Top 15 by inclusive", "| 39.16 |", "[unverified — confirm]"):
            self.assertIn(needle, s, needle)
        self.assertLess(len(s.splitlines()), 90)

    def test_csv_rows_are_sorted_by_self(self):
        with (self.out / "top-symbols.csv").open() as fh:
            rows = list(csv.DictReader(fh))
        selfs = [float(r["self"]) for r in rows]
        self.assertEqual(selfs, sorted(selfs, reverse=True))
        self.assertEqual(rows[0]["symbol"], "0xffffffff81036c36")


class InputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.d = Path(self.tmp.name)

    def test_directory_input_skips_non_reports(self):
        (self.d / "a.report").write_text(FIX.read_text()); (self.d / "b.script").write_text("MarkLogic 1234 [000] 1.0: cpu-clock:\n")
        r = run(self.d, "--out", self.d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 file(s) skipped, not a perf report", (self.d / "o" / "SUMMARY.md").read_text())

    def test_errors(self):
        (self.d / "x.txt").write_text("nothing\n")
        r = run(self.d / "x.txt", "--out", self.d / "o")
        self.assertNotEqual(r.returncode, 0); self.assertIn("no perf report entries", r.stderr)
        r = run(self.d / "missing")
        self.assertNotEqual(r.returncode, 0); self.assertIn("path not found", r.stderr)
        self.assertEqual(run(FIX, "--top", 0).returncode, 2)

    def test_multi_event_report_is_analysed_per_event(self):
        text = (self_report([(40.0, "ML", "ML", ".", "f()")]) + "# Samples: 2K of event 'page-faults'\n# Event count (approx.): 2\n#\n"
                + "# Overhead  Command  Shared Object  Symbol\n#\n    70.00%  ML  ML  [.] g()\n")
        (self.d / "two.txt").write_text(text)
        r = run(self.d / "two.txt", "--out", self.d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = (self.d / "o" / "SUMMARY.md").read_text()
        self.assertIn("## two.txt — cpu-clock", s)
        self.assertIn("## two.txt — page-faults", s)
        self.assertIn("2 events in two.txt", s)
        self.assertIn("2 report(s)", r.stdout)
        inputs = {f["input"] for f in json.loads((self.d / "o" / "findings.json").read_text())}
        self.assertEqual(inputs, {"two.txt — cpu-clock", "two.txt — page-faults"})

    def test_layout_and_unparsed_notes_reach_the_summary(self):
        (self.d / "a.txt").write_text(SELF_ONLY + "    40.00%  ML  ML  [.] f()\n    5.00%  garbage\n")
        r = run(self.d / "a.txt", "--out", self.d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 entry lines could not be parsed", (self.d / "o" / "SUMMARY.md").read_text())

    def test_oversize_file_binary_file_and_unreadable_file_get_notes(self):
        (self.d / "a.report").write_text(FIX.read_text()); (self.d / "blob.bin").write_bytes(b"\x7fELF\0\0\0" + b"    10.00%  A  B  [.] f\n")
        locked = self.d / "locked.txt"; locked.write_text(FIX.read_text()); os.chmod(locked, 0)
        self.addCleanup(os.chmod, locked, 0o600)
        (self.d / "big.txt").write_text(FIX.read_text() * 3)
        with mock.patch.object(diag_inputs, "MAX_MEMBER", 50000):
            self.assertGreater((self.d / "big.txt").stat().st_size, 50000)
            r = run_main([self.d, "--out", self.d / "o"])
        self.assertEqual(r[0], 0)
        s = (self.d / "o" / "SUMMARY.md").read_text()
        self.assertIn("blob.bin: skipped, binary file", s)
        self.assertIn("big.txt: skipped, larger than", s)
        if not os.access(locked, os.R_OK):
            self.assertIn("locked.txt: could not be read", s)

    def test_outputs_are_utf8_whatever_the_locale(self):
        (self.d / "u.txt").write_bytes(self_report([(40.0, "ML", "ML", ".", "f\u00e9()")]).encode("utf-8"))
        env = {**os.environ, "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0", "LC_ALL": "C"}
        r = subprocess.run([sys.executable, str(SCRIPT), str(self.d / "u.txt"), "--out", str(self.d / "o")], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("f\u00e9()", (self.d / "o" / "top-symbols.csv").read_text(encoding="utf-8"))
        self.assertIn("\u2014", (self.d / "o" / "SUMMARY.md").read_text(encoding="utf-8"))


def build_perf_data(hostname="host61", osrelease="3.10.0-1062.18.1.el7.x86_64", arch="x86_64", cpus=(16, 16), mem_kb=32 * 1048576,
                    cmdline=("/usr/bin/perf", "record", "-F", "99", "-ag", "--", "sleep", "60"), events=("cpu-clock",),
                    times=(1000000000, 61000000000), features=None, table_drop=0, big=None, magic=b"PERFILE2"):
    """A minimal synthetic PERFILE2 (little endian): header, 16 bytes of data, feature table, feature sections."""
    def s(t):
        b = t.encode() + b"\0"; b += b"\0" * (-len(b) % 4)
        return struct.pack("<I", len(b)) + b
    payload = {3: s(hostname), 4: s(osrelease), 5: s("#1 SMP"), 6: s(arch), 7: struct.pack("<II", *cpus), 8: s("Some CPU @ 2.0GHz"), 9: s("x86 family 6"),
               10: struct.pack("<Q", mem_kb), 11: struct.pack("<I", len(cmdline)) + b"".join(s(c) for c in cmdline),
               12: struct.pack("<II", len(events), 8) + b"".join(b"\0" * 8 + struct.pack("<I", 1) + s(e) + struct.pack("<Q", 7) for e in events),
               21: struct.pack("<QQ", *times), 2: b"ignored", 13: b"ignored too"}
    if features is not None:
        payload = {k: v for k, v in payload.items() if k in features}
    if big is not None:
        payload[big] = b"\0" * (1048576 + 1)
    bits = sorted(payload)
    bitmap = [0, 0, 0, 0]
    for b in bits:
        bitmap[b // 64] |= 1 << (b % 64)
    hdr_len, data_off, data_size = 104, 104, 16
    tab_off = data_off + data_size
    entries = bits[:len(bits) - table_drop] if table_drop else bits
    sec_off = tab_off + 16 * len(entries)
    table, body = b"", b""
    for b in entries:
        table += struct.pack("<QQ", sec_off + len(body), len(payload[b])); body += payload[b]
    head = magic + struct.pack("<8Q", hdr_len, 136, hdr_len, 0, data_off, data_size, 0, 0) + struct.pack("<4Q", *bitmap)
    return head + b"\x00" * data_size + table + body


class PerfHeaderTest(unittest.TestCase):
    def test_all_fields(self):
        h = ap.read_perf_header(build_perf_data())
        self.assertEqual((h["hostname"], h["osrelease"], h["arch"], h["cpus"], h["cpus_online"]), ("host61", "3.10.0-1062.18.1.el7.x86_64", "x86_64", 16, 16))
        self.assertEqual((h["mem_kb"], h["cmdline"], h["events"], h["data_size"]), (32 * 1048576, ["/usr/bin/perf", "record", "-F", "99", "-ag", "--", "sleep", "60"], ["cpu-clock"], 16))
        self.assertEqual(h["window_s"], 60.0)
        self.assertEqual(h["cpudesc"], "Some CPU @ 2.0GHz")
        self.assertIn("SMP", h["version"])

    def test_two_events_and_missing_features_are_none(self):
        h = ap.read_perf_header(build_perf_data(events=("cpu-clock", "page-faults"), features={3}))
        self.assertEqual(h["hostname"], "host61")
        self.assertEqual(h["events"], [])
        for k in ("osrelease", "cpus", "mem_kb", "window_s", "arch", "cpudesc"):
            self.assertIsNone(h[k], k)
        self.assertEqual(ap.read_perf_header(build_perf_data(events=("cpu-clock", "page-faults")))["events"], ["cpu-clock", "page-faults"])

    def test_wrong_magic_and_truncation_raise_value_error(self):
        good = build_perf_data()
        for bad in (build_perf_data(magic=b"PERFILE1"), b"", good[:8], good[:60], good[:110], b"\x00" * 200):
            with self.assertRaises(ValueError):
                ap.read_perf_header(bad)

    def test_truncated_inside_the_feature_sections_never_raises_anything_else(self):
        good = build_perf_data()
        for n in range(0, len(good), 7):
            try:
                ap.read_perf_header(good[:n])
            except ValueError:
                pass

    def test_oversize_feature_section_is_ignored(self):
        h = ap.read_perf_header(build_perf_data(big=30))
        self.assertEqual(h["hostname"], "host61")

    def test_bitmap_bits_without_table_entries_are_ignored(self):
        h = ap.read_perf_header(build_perf_data(table_drop=2))
        self.assertEqual(h["hostname"], "host61")
        self.assertIsNone(h["window_s"])

    def test_garbage_feature_section_raises_value_error(self):
        raw = bytearray(build_perf_data(features={3}))
        raw[-12:-8] = b"\xff\xff\xff\x7f"   # string length far beyond the section
        with self.assertRaises(ValueError):
            ap.read_perf_header(bytes(raw))

    def test_implausible_sample_window_is_none(self):
        self.assertIsNone(ap.read_perf_header(build_perf_data(times=(5, 1)))["window_s"])


class GlibcAliasTest(unittest.TestCase):
    def test_gi_prefixed_entry_points_are_not_wrappers(self):
        rows = [{"children": 95.0, "self": 0.0, "command": "ML", "dso": "libc-2.17.so", "kind": ".", "symbol": s}
                for s in ("__GI___clone", "__GI_clone", "_GI_clone")]
        rows += [{"children": 60.0, "self": 0.01, "command": "ML", "dso": "libc-2.17.so", "kind": ".", "symbol": "madvise"}]
        r = ap.analyse({"children_mode": True}, rows, 5)
        self.assertEqual([f["detail"].split("`")[1] for f in r["findings"] if f["rule"] == "time_under_user_wrapper"], ["madvise"])


FAKE_REPORT = children_report([(66.5, 0.01, "MarkLogic", "libc-2.17.so", ".", "madvise"), (60.0, 60.0, "MarkLogic", "[kernel.kallsyms]", "k", "0xffffffff81036c36"),
                               (10.0, 10.0, "MarkLogic", "MarkLogic", ".", "xdmp::Foo::bar()")])


class RawPerfDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.d = Path(self.tmp.name)
        self.bin = self.d / "bin"; self.bin.mkdir()
        self.empty = self.d / "empty"; self.empty.mkdir()
        self.log = self.d / "perf-calls.log"

    def fake_perf(self, body=None):
        body = body if body is not None else "cat <<'EOF'\n" + FAKE_REPORT + "EOF\n"
        f = self.bin / "perf"
        f.write_text(f'#!/bin/sh\necho "$@" >> {self.log}\n[ -f "$3" ] || exit 9\nstat_mode=$(ls -l "$3" | cut -c1-10)\necho "$stat_mode" >> {self.log}\n{body}')
        os.chmod(f, 0o755)
        return f"{self.bin}{os.pathsep}{os.defpath}"

    def put(self, name, **kw):
        p = self.d / "in" / name; p.parent.mkdir(exist_ok=True); p.write_bytes(build_perf_data(**kw)); return p

    def test_single_raw_perf_data_gives_inventory_notes_and_exit_0_without_running_perf(self):
        p = self.put("m61perf.data")
        rc, out = run_main([p, "--out", self.d / "o"], path=f"{self.bin}")
        self.assertEqual(rc, 0)
        s = (self.d / "o" / "SUMMARY.md").read_text()
        for needle in ("host61", "3.10.0-1062.18.1.el7.x86_64", "x86_64", "`cpu-clock`", "60", "sleep 60", "32.0 GiB", "perf report -i <file> --stdio",
                       "[unverified — confirm]", "--convert", "customer data"):
            self.assertIn(needle, s, needle)
        self.assertNotIn("## Hosts", s)
        self.assertFalse(self.log.exists())
        self.assertEqual(json.loads((self.d / "o" / "findings.json").read_text()), [])
        self.assertIn("1 perf.data", out)

    def test_unreadable_header_is_noted_and_alone_is_not_usable(self):
        p = self.d / "bad.data"; p.write_bytes(build_perf_data()[:90])
        rc, _ = run_main([p, "--out", self.d / "o"], path=f"{self.bin}")
        self.assertNotEqual(rc, 0)
        self.assertIn("no perf report entries found", str(rc))

    def test_unreadable_header_with_another_usable_input(self):
        (self.d / "in").mkdir(); (self.d / "in" / "bad.data").write_bytes(build_perf_data()[:90]); self.put("ok.data")
        rc, _ = run_main([self.d / "in", "--out", self.d / "o"], path=f"{self.bin}")
        self.assertEqual(rc, 0)
        self.assertIn("unreadable perf.data header", (self.d / "o" / "SUMMARY.md").read_text())

    def test_convert_runs_local_perf_on_a_private_temp_file_and_cleans_up(self):
        p = self.put("m61perf.data")
        path = self.fake_perf()
        rc, out = run_main([p, "--convert", "--out", self.d / "o"], path=path)
        self.assertEqual(rc, 0, out)
        calls = self.log.read_text().splitlines()
        self.assertEqual(len(calls), 2)
        args = calls[0].split()
        self.assertEqual((args[0], args[1], args[3]), ("report", "-i", "--stdio"))
        tmpfile = args[2]
        self.assertTrue(calls[1].startswith("-rw-------"), calls[1])
        self.assertFalse(os.path.exists(tmpfile))
        self.assertFalse(os.path.exists(os.path.dirname(tmpfile)))
        s = (self.d / "o" / "SUMMARY.md").read_text()
        self.assertIn("(converted with local perf)", s)
        self.assertIn("kernel_dominant", s)
        self.assertIn("host61", s)
        self.assertNotIn("perf not installed", s)

    def test_convert_without_perf_on_path_notes_the_command(self):
        p = self.put("m61perf.data")
        rc, _ = run_main([p, "--convert", "--out", self.d / "o"], path=str(self.empty))
        self.assertEqual(rc, 0)
        s = (self.d / "o" / "SUMMARY.md").read_text()
        self.assertIn("perf not installed here: raw perf.data cannot be analysed; run on a Linux host with the same perf: `perf report -i <file> --stdio`", s)
        self.assertIn("references/performance-data-requests.md", s)

    def test_convert_non_zero_exit_is_noted_and_other_files_continue(self):
        self.put("a.data", hostname="host61"); self.put("b.data", hostname="host62")
        path = self.fake_perf('if [ "$(wc -c < "$3")" -gt 0 ] && grep -q host62 "$3"; then echo boom >&2; exit 3; fi\n' + "cat <<'EOF'\n" + FAKE_REPORT + "EOF\n")
        rc, _ = run_main([self.d / "in", "--convert", "--out", self.d / "o"], path=path)
        self.assertEqual(rc, 0)
        s = (self.d / "o" / "SUMMARY.md").read_text()
        self.assertIn("conversion with local perf failed (exit 3)", s)
        rows = read_csv(self.d / "o" / "hosts.csv")
        self.assertEqual({r["host"]: r["analysed"] for r in rows}, {"host61": "yes", "host62": "no"})

    def test_convert_timeout_is_noted_and_the_process_is_killed(self):
        p = self.put("m61perf.data")
        path = self.fake_perf("exec sleep 30\n")
        with mock.patch.object(ap, "CONVERT_TIMEOUT", 1):
            rc, _ = run_main([p, "--convert", "--out", self.d / "o"], path=path)
        self.assertEqual(rc, 0)
        self.assertIn("timed out", (self.d / "o" / "SUMMARY.md").read_text())
        tmpfile = self.log.read_text().split()[2]
        self.assertFalse(os.path.exists(tmpfile))

    def test_convert_output_cap_is_noted(self):
        p = self.put("m61perf.data")
        path = self.fake_perf("yes '    10.00%  A  B  [.] f' | head -c 200000\n")
        with mock.patch.object(ap, "CONVERT_MAX", 1000):
            rc, _ = run_main([p, "--convert", "--out", self.d / "o"], path=path)
        self.assertEqual(rc, 0)
        self.assertIn("output larger than", (self.d / "o" / "SUMMARY.md").read_text())

    def test_perf_data_is_detected_by_magic_not_by_name_and_binary_junk_is_skipped(self):
        (self.d / "in").mkdir()
        (self.d / "in" / "weird.bin").write_bytes(build_perf_data())
        (self.d / "in" / "other.bin").write_bytes(b"\x00\x01\x02" * 100)
        rc, _ = run_main([self.d / "in", "--out", self.d / "o"], path=str(self.empty))
        self.assertEqual(rc, 0)
        s = (self.d / "o" / "SUMMARY.md").read_text()
        self.assertIn("host61", s)
        self.assertIn("other.bin: skipped, binary file", s)


class MultiNodeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.d = Path(self.tmp.name)

    def zip_with(self, members):
        z = self.d / "perfdata.zip"
        with zipfile.ZipFile(z, "w") as zf:
            for n, b in members.items():
                zf.writestr(n, b)
        return z

    def test_zip_of_raw_perf_data_nodes_overview_and_csv(self):
        members = {"perfdata/m61perf.data": build_perf_data(hostname="host61"), "perfdata/m62perf.data": build_perf_data(hostname="host62", osrelease="3.10.0-1160.el7.x86_64", mem_kb=64 * 1048576),
                   "__MACOSX/perfdata/._m61perf.data": b"junk", "perfdata/.DS_Store": b"x", "perfdata/m63perf.data": build_perf_data(hostname="host63")}
        z = self.zip_with(members)
        rc, out = run_main([z, "--out", self.d / "o"], path=str(self.d))
        self.assertEqual(rc, 0)
        s = (self.d / "o" / "SUMMARY.md").read_text()
        lines = s.splitlines()
        self.assertEqual(lines[0], "# perf report analysis")
        self.assertEqual(lines[2], "## Hosts")
        for needle in ("| Host | Input kind | Kernel | CPUs | Memory (GiB) | Window (s) | Capture command | Analysed |", "| host61 | perf.data | 3.10.0-1062.18.1.el7.x86_64 | 16 | 32.0 | 60 |",
                       "| host62 | perf.data | 3.10.0-1160.el7.x86_64 | 16 | 64.0 |", "the nodes were not captured the same way", "kernel versions differ", "macOS metadata file(s) skipped"):
            self.assertIn(needle, s, needle)
        self.assertIn("| /usr/bin/perf record -F 99 -ag -- sle... |", s)
        rows = read_csv(self.d / "o" / "hosts.csv")
        self.assertEqual([r["host"] for r in rows], ["host61", "host62", "host63"])
        self.assertEqual(rows[0]["capture_command"], "/usr/bin/perf record -F 99 -ag -- sleep 60")
        self.assertEqual(rows[0]["analysed"], "no")
        self.assertEqual(rows[0]["kernel_share"], "-")

    def test_same_capture_gives_no_difference_note(self):
        z = self.zip_with({"a.data": build_perf_data(hostname="host61"), "b.data": build_perf_data(hostname="host62")})
        run_main([z, "--out", self.d / "o"], path=str(self.d))
        self.assertNotIn("not captured the same way", (self.d / "o" / "SUMMARY.md").read_text())

    def test_mixed_reports_and_perf_data_order_sev0_first_and_host_from_zip_name(self):
        flat = children_report([(5.0, 5.0, "ML", "ML", ".", "f()")] * 5)
        inner = self.d / "host71.zip"
        with zipfile.ZipFile(inner, "w") as zf:
            zf.writestr("tmp/p.report", FAKE_REPORT)
        outer = self.d / "perfdata.zip"
        with zipfile.ZipFile(outer, "w") as zf:
            zf.write(inner, "host71.zip"); zf.writestr("host72/q.report", flat); zf.writestr("host60/z.data", build_perf_data(hostname="host60"))
        rc, _ = run_main([outer, "--out", self.d / "o"], path=str(self.d))
        self.assertEqual(rc, 0)
        rows = read_csv(self.d / "o" / "hosts.csv")
        self.assertEqual([(r["host"], r["input_kind"], r["analysed"]) for r in rows],
                         [("host71", "report", "yes"), ("host60", "perf.data", "no"), ("host72", "report", "yes")])
        self.assertEqual(rows[0]["top_finding"], "time_under_user_wrapper")
        self.assertEqual(rows[0]["kernel_share"], "60.0")
        self.assertEqual(rows[1]["top_finding"], "-")
        s = (self.d / "o" / "SUMMARY.md").read_text()
        self.assertIn("## perfdata.zip > host71.zip > tmp/p.report", s)

    def test_convert_over_many_nodes(self):
        z = self.zip_with({f"n{i}.data": build_perf_data(hostname=f"host6{i}") for i in range(3)})
        b = self.d / "bin"; b.mkdir()
        (b / "perf").write_text("#!/bin/sh\ncat <<'EOF'\n" + FAKE_REPORT + "EOF\n"); os.chmod(b / "perf", 0o755)
        rc, _ = run_main([z, "--convert", "--out", self.d / "o"], path=f"{b}{os.pathsep}{os.defpath}")
        self.assertEqual(rc, 0)
        rows = read_csv(self.d / "o" / "hosts.csv")
        self.assertEqual([r["analysed"] for r in rows], ["yes"] * 3)
        self.assertEqual(rows[0]["kernel_share"], "60.0")

    def test_duplicate_copies_are_dropped(self):
        b = build_perf_data()
        z = self.zip_with({"a/x.data": b, "b/x.data": b})
        run_main([z, "--out", self.d / "o"], path=str(self.d))
        s = (self.d / "o" / "SUMMARY.md").read_text()
        self.assertIn("duplicate copy(ies)", s)
        self.assertNotIn("## Hosts", s)

    def test_missing_path_error(self):
        rc, _ = run_main([self.d / "nope"])
        self.assertIn("path not found", str(rc))


if __name__ == "__main__":
    unittest.main()
