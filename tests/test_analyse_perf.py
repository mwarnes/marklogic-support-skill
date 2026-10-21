import csv, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/marklogic-support/scripts/analyse_perf.py"
FIX = Path(__file__).with_name("fixture_perf") / "perf-report-sample.txt"
sys.path.insert(0, str(SCRIPT.parent))
import analyse_perf as ap


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
        self.assertIn("skipped b.script", (self.d / "o" / "SUMMARY.md").read_text())

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
        (self.d / "a.report").write_text(FIX.read_text()); (self.d / "perf.data").write_bytes(b"PERFILE2\0\0\0" + b"    10.00%  A  B  [.] f\n")
        (self.d / "big.txt").write_text(FIX.read_text())
        locked = self.d / "locked.txt"; locked.write_text(FIX.read_text()); os.chmod(locked, 0)
        self.addCleanup(os.chmod, locked, 0o600)
        old = ap.MAX_BYTES; ap.MAX_BYTES = 50000
        self.addCleanup(setattr, ap, "MAX_BYTES", old)
        (self.d / "big.txt").write_text(FIX.read_text() * 3)
        self.assertGreater((self.d / "big.txt").stat().st_size, 50000)
        notes = []
        files = ap.collect_files([self.d], notes)
        names = [f.name for f in files]
        self.assertIn("a.report", names)
        for n in ("perf.data", "big.txt"):
            self.assertNotIn(n, names)
        joined = "\n".join(notes)
        self.assertIn("perf.data: skipped, binary file", joined)
        self.assertIn("big.txt: skipped, larger than", joined)
        if not os.access(locked, os.R_OK):
            self.assertIn("locked.txt: could not be read", joined)

    def test_outputs_are_utf8_whatever_the_locale(self):
        (self.d / "u.txt").write_bytes(self_report([(40.0, "ML", "ML", ".", "f\u00e9()")]).encode("utf-8"))
        env = {**os.environ, "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0", "LC_ALL": "C"}
        r = subprocess.run([sys.executable, str(SCRIPT), str(self.d / "u.txt"), "--out", str(self.d / "o")], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("f\u00e9()", (self.d / "o" / "top-symbols.csv").read_text(encoding="utf-8"))
        self.assertIn("\u2014", (self.d / "o" / "SUMMARY.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
