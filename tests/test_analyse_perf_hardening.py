"""analyse_perf: hostile header text, --convert process hygiene, untrusted perf lookup, inventory and overview rules."""
import csv, os, re, subprocess, sys, tempfile, time, unittest, zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/marklogic-support/scripts"))
sys.path.insert(0, str(Path(__file__).parent))
import analyse_perf as ap
from test_analyse_perf import build_perf_data, run_main, read_csv, run, FAKE_REPORT, children_report, SCRIPT

CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.d = Path(self.tmp.name)
        (self.d / "in").mkdir(); self.bin = self.d / "bin"; self.bin.mkdir()

    def put(self, name, **kw):
        p = self.d / "in" / name; p.write_bytes(build_perf_data(**kw)); return p

    def summary(self):
        return (self.d / "o" / "SUMMARY.md").read_text(encoding="utf-8")


class HostileTextTest(Base):
    def test_header_strings_are_clean(self):
        h = ap.read_perf_header(build_perf_data(hostname="h\x1b[31m\nEVIL|`x", osrelease="3.10\n## x", arch="x\x07", cmdline=("a\x07", "b|c\nd"),
                                                events=("cpu\x1bclock",)))
        for k in ("hostname", "osrelease", "arch", "cpudesc", "version"):
            self.assertFalse(CTRL.search(h[k]) or "\n" in h[k] or "|" in h[k] or "`" in h[k], k)
        for t in h["cmdline"] + h["events"]:
            self.assertFalse(CTRL.search(t) or "|" in t)
        self.assertEqual(h["cmdline"][1], "b/c?d")

    def test_text_header_values_are_clean(self):
        h = ap.text_header("# os release : 3.10\x1b|x\n# cmdline : perf `record`\x07\n#\n")
        self.assertEqual(h["osrelease"], "3.10?/x")
        self.assertFalse(CTRL.search(h["cmdline"]) or "`" in h["cmdline"])

    def test_overview_row_and_csv_cell_are_clean_and_formulas_prefixed(self):
        self.put("a.data", hostname="h\x1b[31m\nEVIL|x", cmdline=("perf", "record"))
        self.put("b.data", hostname='=HYPERLINK("x")')
        rc, _ = run_main([self.d / "in", "--out", self.d / "o"], path=str(self.bin))
        self.assertEqual(rc, 0)
        s = self.summary()
        self.assertFalse(CTRL.search(s))
        self.assertFalse([l for l in s.splitlines() if l.startswith("EVIL")])
        hosts = [r["host"] for r in read_csv(self.d / "o" / "hosts.csv")]
        self.assertIn("h?[31m?EVIL/x", hosts)
        self.assertIn("'=HYPERLINK(\"x\")", hosts)

    def test_report_symbols_are_clean_and_formula_cells_prefixed(self):
        text = children_report([(5.0, 5.0, "ML", "ML", ".", "a|b`c"), (4.0, 4.0, "ML", "ML", ".", "=cmd()")])
        (self.d / "in" / "r.txt").write_text(text)
        rc, _ = run_main([self.d / "in" / "r.txt", "--out", self.d / "o"], path=str(self.bin))
        self.assertEqual(rc, 0)
        syms = [r["symbol"] for r in read_csv(self.d / "o" / "top-symbols.csv")]
        self.assertEqual(syms, ["a/b'c", "'=cmd()"])
        self.assertNotIn("a|b", self.summary())

    def test_member_name_with_newline_cannot_split_a_heading(self):
        with zipfile.ZipFile(self.d / "t.zip", "w") as zf:
            zf.writestr("x\n## Injected\x1b/r.txt", FAKE_REPORT)
        rc, _ = run_main([self.d / "t.zip", "--out", self.d / "o"], path=str(self.bin))
        self.assertEqual(rc, 0)
        s = self.summary()
        self.assertFalse(CTRL.search(s))
        self.assertFalse([l for l in s.splitlines() if l.startswith("## Injected")])


class ConvertProcessTest(Base):
    def fake(self, body):
        f = self.bin / "perf"; f.write_text("#!/bin/sh\n" + body); os.chmod(f, 0o755)
        return f"{self.bin}{os.pathsep}{os.defpath}"

    def pids(self, pidfile):
        return [int(x) for x in pidfile.read_text().split()]

    def assert_gone(self, pids):
        for pid in pids:
            for _ in range(60):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.1)
            else:
                os.kill(pid, 9)
                self.fail(f"process {pid} of the perf session is still running")

    def script(self, pidfile):
        return f"sleep 30 &\necho $! > {pidfile}\necho $$ >> {pidfile}\nsleep 30\n"

    def test_timeout_kills_the_children_too(self):
        pidfile = self.d / "pids"
        path = self.fake(self.script(pidfile))
        p = self.put("n.data")
        with mock.patch.object(ap, "CONVERT_TIMEOUT", 1):
            rc, _ = run_main([p, "--convert", "--out", self.d / "o"], path=path)
        self.assertEqual(rc, 0)
        self.assertIn("timed out", self.summary())
        self.assert_gone(self.pids(pidfile))

    def test_an_exception_or_interrupt_in_the_poll_loop_kills_the_whole_session(self):
        for exc in (RuntimeError("boom"), KeyboardInterrupt()):
            with self.subTest(exc=type(exc).__name__):
                pidfile = self.d / f"pids-{type(exc).__name__}"
                path = self.fake(self.script(pidfile))
                p = self.put("n.data")

                def poll_then_raise(_p):
                    for _ in range(50):
                        if pidfile.exists() and len(pidfile.read_text().split()) == 2:
                            break
                        time.sleep(0.1)
                    raise exc
                with mock.patch.object(ap.os.path, "getsize", side_effect=poll_then_raise):
                    with self.assertRaises(type(exc)):
                        run_main([p, "--convert", "--out", self.d / "o"], path=path)
                self.assert_gone(self.pids(pidfile))

    def test_normal_exit_still_reaps_leftover_children(self):
        pidfile = self.d / "pids"
        path = self.fake(f"sleep 30 &\necho $! > {pidfile}\ncat <<'EOF'\n{FAKE_REPORT}EOF\n")
        rc, _ = run_main([self.put("n.data"), "--convert", "--out", self.d / "o"], path=path)
        self.assertEqual(rc, 0)
        self.assert_gone(self.pids(pidfile))


class UntrustedPerfTest(Base):
    def test_perf_in_the_current_directory_via_a_dot_path_entry_is_not_run(self):
        cwd = self.d / "cwd"; cwd.mkdir()
        log = self.d / "ran"
        (cwd / "perf").write_text(f"#!/bin/sh\necho x >> {log}\ncat <<'EOF'\n{FAKE_REPORT}EOF\n"); os.chmod(cwd / "perf", 0o755)
        old = os.getcwd(); os.chdir(cwd); self.addCleanup(os.chdir, old)
        rc, _ = run_main([self.put("n.data"), "--convert", "--out", self.d / "o"], path=".")
        self.assertEqual(rc, 0)
        self.assertIn("perf found at a relative/untrusted PATH entry; not run", self.summary())
        self.assertFalse(log.exists())

    def test_perf_inside_an_input_folder_is_not_run(self):
        log = self.d / "ran"
        b = self.d / "in" / "bin"; b.mkdir()
        (b / "perf").write_text(f"#!/bin/sh\necho x >> {log}\n"); os.chmod(b / "perf", 0o755)
        self.put("n.data")
        rc, _ = run_main([self.d / "in", "--convert", "--out", self.d / "o"], path=str(b))
        self.assertEqual(rc, 0)
        self.assertIn("perf found at a relative/untrusted PATH entry; not run", self.summary())
        self.assertFalse(log.exists())

    def test_perf_in_a_relative_path_entry_is_not_run(self):
        (self.bin / "perf").write_text("#!/bin/sh\nexit 0\n"); os.chmod(self.bin / "perf", 0o755)
        old = os.getcwd(); os.chdir(self.d); self.addCleanup(os.chdir, old)
        rc, _ = run_main([self.put("n.data"), "--convert", "--out", self.d / "o"], path="bin")
        self.assertEqual(rc, 0)
        self.assertIn("relative/untrusted PATH entry", self.summary())


class InventoryTest(Base):
    def test_single_inventory_uses_the_first_usable_file(self):
        (self.d / "in" / "a_bad.data").write_bytes(build_perf_data()[:90])
        self.put("b_ok.data", hostname="host77")
        rc, _ = run_main([self.d / "in", "--out", self.d / "o"], path=str(self.bin))
        self.assertEqual(rc, 0)
        s = self.summary()
        self.assertIn("### perf.data header (raw file, samples not read)", s)
        self.assertIn("- Host: host77", s)

    def test_header_without_any_usable_field_is_not_usable(self):
        (self.d / "in" / "z.data").write_bytes(b"PERFILE2" + b"\0" * 300)
        r = run(self.d / "in", "--out", self.d / "o")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no perf report entries", r.stderr)
        self.assertIn("perf.data header has no usable fields", r.stderr)

    def test_unusable_header_next_to_a_usable_one_is_not_inventoried(self):
        (self.d / "in" / "z.data").write_bytes(b"PERFILE2" + b"\0" * 300)
        self.put("ok.data")
        rc, out = run_main([self.d / "in", "--out", self.d / "o"], path=str(self.bin))
        self.assertEqual(rc, 0)
        self.assertIn("1 perf.data header(s)", out)
        self.assertIn("perf.data header has no usable fields", self.summary())


class OverviewTest(Base):
    def test_cpus_column_is_the_online_count_and_the_footnote_says_so(self):
        self.put("a.data", hostname="host61", cpus=(16, 8)); self.put("b.data", hostname="host62", cpus=(4, 4))
        rc, _ = run_main([self.d / "in", "--out", self.d / "o"], path=str(self.bin))
        self.assertEqual(rc, 0)
        self.assertEqual({r["host"]: r["cpus"] for r in read_csv(self.d / "o" / "hosts.csv")}, {"host61": "8", "host62": "4"})
        s = self.summary()
        self.assertIn("| host61 | perf.data |", s)
        self.assertRegex(s, r"CPUs[^\n]*online")

    def test_clashing_hosts_get_a_disambiguator(self):
        self.put("a.data", hostname="host61", cmdline=("perf", "a")); self.put("b.data", hostname="host61", cmdline=("perf", "b"))
        run_main([self.d / "in", "--out", self.d / "o"], path=str(self.bin))
        self.assertEqual(sorted(r["host"] for r in read_csv(self.d / "o" / "hosts.csv")), ["host61 (a.data)", "host61 (b.data)"])
        self.assertIn("| host61 (a.data) |", self.summary())

    def test_binary_files_are_one_note_line(self):
        self.put("a.data")
        for n in ("x.bin", "y.bin"):
            (self.d / "in" / n).write_bytes(b"\x00\x01\x02" * 50)
        run_main([self.d / "in", "--out", self.d / "o"], path=str(self.bin))
        s = self.summary()
        self.assertIn("2 binary file(s) skipped", s)
        self.assertNotIn("x.bin", s)

    def test_more_than_20_inputs_show_sections_only_for_inputs_with_findings(self):
        for i in range(25):
            text = FAKE_REPORT if i == 7 else children_report([(2.0, 2.0, "ML", f"lib{i}.so", ".", "f()")] * 5)
            (self.d / "in" / f"h{i:02d}.report").write_text(text)
        rc, _ = run_main([self.d / "in", "--out", self.d / "o"], path=str(self.bin))
        self.assertEqual(rc, 0)
        s = self.summary()
        self.assertEqual(len([l for l in s.splitlines() if re.match(r"\| h\d\d\.report \|", l)]), 25)
        self.assertEqual(s.count("### Findings"), 1)
        self.assertIn("## h07.report", s)
        self.assertIn("per-input sections are shown only for the 1 input(s) with at least one finding", s)
        self.assertEqual(len({r["input"] for r in read_csv(self.d / "o" / "top-symbols.csv")}), 25)


class StderrNotesTest(Base):
    def test_notes_are_printed_when_nothing_is_usable(self):
        (self.d / "in" / "x.txt").write_text("nothing\n")
        r = run(self.d / "in", "--out", self.d / "o")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("1 file(s) skipped, not a perf report", r.stderr)


if __name__ == "__main__":
    unittest.main()
