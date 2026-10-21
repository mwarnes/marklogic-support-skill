"""analyse_pstack: hardening against hostile names and odd inputs, notes on failure, date order, overview limits."""
import contextlib, csv, io, os, re, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/marklogic-support/scripts"))
sys.path.insert(0, str(Path(__file__).parent))
import analyse_pstack as ap
import diag_inputs as di
from test_analyse_pstack import run, thread, IDLE, BUSY, dated_log

CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.d = Path(self.tmp.name)

    def summary(self, out="o"):
        return (self.d / out / "SUMMARY.md").read_text(encoding="utf-8")


class FailureTest(Base):
    def test_sniff_matches_but_nothing_parses_is_a_clean_error(self):
        (self.d / "p.log").write_text("Thread 1 (foo):\n#0  0x1 in poll ()\n")
        r = run(self.d / "p.log", "--out", self.d / "o")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("no parseable pstack snapshots", r.stderr)
        self.assertIn("LWP", r.stderr)

    def test_notes_are_printed_to_stderr_when_nothing_is_usable(self):
        import io as _io
        b = _io.BytesIO()
        with zipfile.ZipFile(b, "w") as zf:
            zf.writestr("secret.log", "x")
        data = bytearray(b.getvalue()); i = data.index(b"PK\x01\x02"); data[i + 8] |= 1
        (self.d / "o.zip").write_bytes(bytes(data))
        r = run(self.d / "o.zip", "--out", self.d / "o")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("password-protected", r.stderr)
        self.assertIn("no pstack data", r.stderr)

    def test_unparseable_case_prints_notes_too(self):
        (self.d / "p.log").write_text("Thread 1 (foo):\n#0  0x1 in poll ()\nnoise\n")
        (self.d / "bin").write_bytes(b"\0\0\0")
        r = run(self.d, "--out", self.d / "o")
        self.assertIn("1 binary file(s) skipped", r.stderr)

    def test_close_all_runs_even_when_main_exits_early(self):
        (self.d / "x.txt").write_text("nothing\n")
        with mock.patch.object(di, "close_all") as ca, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                ap.main([str(self.d / "x.txt"), "--out", str(self.d / "o")])
        ca.assert_called_once()


class HostileNameTest(Base):
    def test_member_name_and_date_line_cannot_inject_markup(self):
        name = "h\n## Injected\x1b[31m\x07|`x/pstack.log"
        log = "Tue Oct 21 10:00:01 UTC 2026 |evil`\x1b\n" + thread(2, 1, *IDLE) + "Tue Oct 21 10:00:06 UTC 2026\n" + thread(2, 1, *IDLE)
        with zipfile.ZipFile(self.d / "t.zip", "w") as zf:
            zf.writestr(name, log)
        r = run(self.d / "t.zip", "--out", self.d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertFalse(CTRL.search(s))
        self.assertFalse([l for l in s.splitlines() if l.startswith("## Injected")])
        self.assertNotIn("|evil", s)
        with (self.d / "o" / "snapshots.csv").open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertFalse(CTRL.search(rows[0]["input"]) or CTRL.search(rows[0]["date"]))

    def test_formula_host_is_prefixed_in_hosts_csv(self):
        for n, log in (("=HYPERLINK(\"x\")", dated_log("08:33", 11, [thread(2, 1, *IDLE)])), ("plain", dated_log("08:33", 11, [thread(3, 2, *IDLE)]))):
            (self.d / "in" / n).mkdir(parents=True); (self.d / "in" / n / "pstack.log").write_text(log)
        r = run(self.d / "in", "--out", self.d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        with (self.d / "o" / "hosts.csv").open(encoding="utf-8") as fh:
            hosts = [x["host"] for x in csv.DictReader(fh)]
        self.assertIn("'=HYPERLINK(\"x\")", hosts)
        self.assertNotIn("=HYPERLINK(\"x\")", hosts)

    def test_function_names_with_pipes_and_backticks_are_cleaned(self):
        hot = ("xdmp::a|b`c::spin() ()", "xdmp::Bar::eval() ()", "xdmp::AppRequestTask::run() ()")
        (self.d / "p.log").write_text(dated_log("08:33", 5, *([thread(2, 1, *hot)],) * 3))
        r = run(self.d / "p.log", "--out", self.d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertNotIn("a|b", s); self.assertNotIn("b`c", s)
        self.assertIn("a/b'c", s)


class DateOrderTest(Base):
    def spacing(self, dates):
        log = "".join(d + "\n" + thread(2, 1, *IDLE) for d in dates)
        (self.d / "p.log").write_text(log)
        r = run(self.d / "p.log", "--out", self.d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.summary()

    def test_out_of_order_dates_use_sorted_absolute_gaps_and_a_note(self):
        s = self.spacing(["Mon Sep 21 10:00:20 GMT 2020", "Mon Sep 21 10:00:00 GMT 2020", "Mon Sep 21 10:00:10 GMT 2020"])
        self.assertIn("about 10 s apart", s)
        self.assertNotIn("-5 s", s)
        self.assertIn("dates are not in order", s)

    def test_cross_midnight_in_order_keeps_working_without_a_note(self):
        s = self.spacing(["Mon Sep 21 23:59:50 GMT 2020", "Tue Sep 22 00:00:00 GMT 2020", "Tue Sep 22 00:00:10 GMT 2020"])
        self.assertIn("about 10 s apart", s)
        self.assertNotIn("not in order", s)


class AggregateNotesTest(Base):
    def test_binary_files_are_one_note_line(self):
        (self.d / "a.log").write_text(dated_log("08:33", 5, [thread(2, 1, *IDLE)]))
        for n in ("core.1", "core.2", "core.3"):
            (self.d / n).write_bytes(b"\x7fELF\0\0")
        r = run(self.d, "--out", self.d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn("3 binary file(s) skipped", s)
        self.assertNotIn("core.1", s)

    def test_macosx_directory_files_are_counted(self):
        (self.d / "in" / "__MACOSX").mkdir(parents=True)
        (self.d / "in" / "__MACOSX" / "._a").write_text("j"); (self.d / "in" / "__MACOSX" / "b").write_text("j")
        (self.d / "in" / "a.log").write_text(dated_log("08:33", 5, [thread(2, 1, *IDLE)]))
        r = run(self.d / "in", "--out", self.d / "o")
        self.assertIn("2 macOS metadata file(s) skipped", self.summary())


class OverviewTest(Base):
    def test_clashing_hosts_get_a_disambiguator(self):
        for d, n in (("d1", "a.log"), ("d2", "b.log")):
            (self.d / d).mkdir()
            with zipfile.ZipFile(self.d / d / "host9.zip", "w") as zf:
                zf.writestr(n, dated_log("08:33", 5, [thread(2 if n == "a.log" else 3, 1, *IDLE)]))
        r = run(self.d / "d1", self.d / "d2", "--out", self.d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertIn("| host9 (a.log) |", s); self.assertIn("| host9 (b.log) |", s)
        with (self.d / "o" / "hosts.csv").open(encoding="utf-8") as fh:
            self.assertEqual(sorted(x["host"] for x in csv.DictReader(fh)), ["host9 (a.log)", "host9 (b.log)"])

    def test_more_than_20_inputs_show_sections_only_for_inputs_with_findings(self):
        (self.d / "in").mkdir()
        for i in range(25):
            th = [thread(3, 1000 + i, *BUSY)] if i == 7 else [thread(3, 1000 + i, *IDLE)]
            (self.d / "in" / f"h{i:02d}.log").write_text(dated_log("08:33", 5, th, th, th))
        r = run(self.d / "in", "--out", self.d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.summary()
        self.assertEqual(len([l for l in s.splitlines() if re.match(r"\| h\d\d\.log \|", l)]), 25)
        self.assertEqual(s.count("### Findings"), 1)
        self.assertIn("## h07.log", s)
        self.assertIn("per-input sections are shown only for the 1 input(s) with at least one finding", s)
        with (self.d / "o" / "snapshots.csv").open(encoding="utf-8") as fh:
            self.assertEqual(len({x["input"] for x in csv.DictReader(fh)}), 25)

    def test_20_inputs_or_fewer_show_every_section(self):
        (self.d / "in").mkdir()
        for i in range(3):
            th = [thread(3, 1000 + i, *IDLE)]
            (self.d / "in" / f"h{i}.log").write_text(dated_log("08:33", 5, th, th, th))
        run(self.d / "in", "--out", self.d / "o")
        self.assertEqual(self.summary().count("### Findings"), 3)


if __name__ == "__main__":
    unittest.main()
