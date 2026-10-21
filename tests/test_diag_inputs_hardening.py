"""Hardening of diag_inputs: untrusted text, special files, nesting budget, entry-count pre-check, dedupe resilience, host hints."""
import io, os, re, stat, struct, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/marklogic-support/scripts"
sys.path.insert(0, str(SCRIPTS))
import diag_inputs as di
from test_diag_inputs import Base, zbytes

CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class SafeLabelTest(unittest.TestCase):
    def test_controls_pipes_backticks_whitespace_and_limit(self):
        t = di.safe_label("a\r\nb\x1b[31m\x07c\x7fd\x85e|f`g   h\t\ti")
        self.assertFalse(CTRL.search(t), repr(t))
        self.assertNotIn("|", t); self.assertNotIn("`", t); self.assertNotIn("  ", t)
        self.assertEqual(di.safe_label("x|y`z"), "x/y'z")
        self.assertEqual(di.safe_label("a   b   c"), "a b c")
        long = di.safe_label("x" * 60000)
        self.assertEqual(len(long), 200); self.assertTrue(long.endswith("…"))
        self.assertEqual(di.safe_label("x" * 10, limit=10), "x" * 10)
        self.assertEqual(di.safe_label("abcdef", limit=4), "abc…")

    def test_zip_member_name_gives_a_single_clean_bounded_label(self):
        name = "a\r\n## Injected\x1b[31m\x07|`b" + "x" * 60000
        o = self.mk(zbytes({name: b"data"}))
        srcs, notes = o
        self.assertEqual(len(srcs), 1)
        s = srcs[0]
        for text in (s.label, s.name, *s.parts):
            self.assertFalse(CTRL.search(text), repr(text[:80]))
            self.assertNotIn("|", text); self.assertNotIn("`", text)
        self.assertLessEqual(len(s.label), 400)
        self.assertEqual(s.read(), b"data")

    def mk(self, data):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        z = Path(self.tmp.name) / "t.zip"; z.write_bytes(data)
        notes = set(); srcs = di.walk([z], notes); self.addCleanup(di.close_all, srcs)
        return srcs, notes

    def test_host_hint_result_is_safe(self):
        s = di.Source(["bad\nhost|`x\x1b.zip", "pstack.log"], 1, lambda: io.BytesIO(b"x"))
        h = di.host_hint(s)
        self.assertFalse(CTRL.search(h)); self.assertNotIn("|", h)

    def test_csv_cell_formula_injection(self):
        self.assertEqual(di.csv_cell('=HYPERLINK("x")'), '\'=HYPERLINK("x")')
        for t in ("+1", "-1+1", "@SUM(1)"):
            self.assertEqual(di.csv_cell(t), "'" + t)
        self.assertEqual(di.csv_cell("-"), "-")        # the placeholder for 'no value'
        self.assertEqual(di.csv_cell("host"), "host")
        self.assertEqual(di.csv_cell(5), 5)


@unittest.skipUnless(hasattr(os, "mkfifo"), "no mkfifo")
class SpecialFileTest(Base):
    def test_fifo_in_a_folder_and_at_top_level_is_skipped_and_counted_once(self):
        (self.d / "dir").mkdir(); (self.d / "dir" / "ok.log").write_text("x")
        os.mkfifo(self.d / "dir" / "pipe1"); os.mkfifo(self.d / "dir" / "pipe2.zip")
        top = self.d / "top.fifo"; os.mkfifo(top)
        result = {}

        def work():
            result["v"] = self.walk(self.d / "dir", top)
        import threading
        t = threading.Thread(target=work, daemon=True); t.start(); t.join(10)
        self.assertFalse(t.is_alive(), "walk blocked on a FIFO")
        srcs, notes = result["v"]
        self.assertEqual([s.label for s in srcs], ["ok.log"])
        self.assertEqual(notes, {"3 special file(s) skipped"})

    def test_scripts_do_not_hang_on_a_fifo(self):
        os.mkfifo(self.d / "pipe")
        (self.d / "ok.txt").write_text("nothing\n")
        for script in ("analyse_pstack.py", "analyse_perf.py"):
            try:
                r = subprocess.run([sys.executable, str(SCRIPTS / script), str(self.d), "--out", str(self.d / "o")],
                                   capture_output=True, text=True, timeout=30)
            except subprocess.TimeoutExpired:
                self.fail(f"{script} hung on a FIFO")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("1 special file(s) skipped", r.stderr, script)


class NestedBudgetTest(Base):
    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, di, "NESTED_BUDGET", di.NESTED_BUDGET)

    def test_default_budget_is_one_gib(self):
        self.assertEqual(di.NESTED_BUDGET, 1024 ** 3)

    def test_inner_zip_over_budget_is_skipped_with_a_note(self):
        inner = zbytes({"a.log": b"x" * 100})
        o = self.d / "o.zip"; o.write_bytes(zbytes({"i1.zip": inner, "i2.zip": zbytes({"b.log": b"y" * 100}), "ok.log": b"1"}))
        di.NESTED_BUDGET = len(inner) + 10
        srcs, notes = self.walk(o)
        self.assertEqual(sorted(s.name for s in srcs), ["a.log", "ok.log"])
        self.assertEqual(len(notes), 1)
        self.assertRegex(next(iter(notes)), r"^o\.zip > i2\.zip: skipped, nested zips over .* in memory$")

    def test_inner_zip_without_usable_members_is_released(self):
        junk_only = zbytes({"__MACOSX/._x": b"j"})
        o = self.d / "o.zip"; o.write_bytes(zbytes({"i1.zip": junk_only, "i2.zip": junk_only, "i3.zip": zbytes({"c.log": b"1"})}))
        di.NESTED_BUDGET = len(junk_only) + len(zbytes({"c.log": b"1"})) + 5   # two junk zips would not fit if they were kept
        srcs, notes = self.walk(o)
        self.assertEqual([s.name for s in srcs], ["c.log"])
        self.assertFalse([n for n in notes if "nested zips over" in n], notes)


class EntryCountPrecheckTest(Base):
    def test_declared_entries_of_a_normal_and_a_zip64_style_tail(self):
        self.assertEqual(di._declared_entries(zbytes({f"f{i}": b"x" for i in range(5)})), 5)
        rec = b"PK\x06\x06" + struct.pack("<QHHIIQQQQ", 44, 45, 45, 0, 0, 100000, 100000, 0, 0)
        loc = b"PK\x06\x07" + struct.pack("<IQI", 0, 0, 1)
        eocd = b"PK\x05\x06" + struct.pack("<HHHHIIH", 0, 0, 0xFFFF, 0xFFFF, 0, 0, 0)
        self.assertEqual(di._declared_entries(b"junk" + rec + loc + eocd), 100000)
        self.assertIsNone(di._declared_entries(b"no end record here"))
        self.assertIsNone(di._declared_entries(b"PK\x05\x06short"))
        self.assertIsNone(di._declared_entries(b"junk" + loc + eocd))   # zip64 marker without the zip64 record

    def test_zip_declaring_too_many_entries_is_skipped_before_zipfile_is_built(self):
        o = self.d / "o.zip"; o.write_bytes(zbytes({f"f{i}.log": b"x" for i in range(5)}))
        di.MAX_MEMBERS = 3
        with mock.patch.object(di.zipfile, "ZipFile", side_effect=AssertionError("ZipFile constructed")):
            srcs, notes = self.walk(o)
        self.assertEqual(srcs, [])
        self.assertEqual(notes, {"o.zip: stopped reading, more than 3 entries"})

    def test_inner_zip_declaring_too_many_entries_is_skipped(self):
        inner = zbytes({f"f{i}.log": b"x" for i in range(5)})
        o = self.d / "o.zip"; o.write_bytes(zbytes({"i.zip": inner, "ok.log": b"1"}))
        di.MAX_MEMBERS = 4
        srcs, notes = self.walk(o)
        self.assertEqual([s.name for s in srcs], ["ok.log"])
        self.assertEqual(notes, {"o.zip > i.zip: stopped reading, more than 4 entries"})

    def test_when_the_declared_count_is_unknown_the_entry_loop_still_truncates(self):
        o = self.d / "o.zip"; o.write_bytes(zbytes({f"f{i}.log": b"x" for i in range(5)}))
        di.MAX_MEMBERS = 3
        with mock.patch.object(di, "_declared_entries", return_value=None):
            srcs, notes = self.walk(o)
        self.assertEqual([s.name for s in srcs], ["f0.log", "f1.log", "f2.log"])
        self.assertEqual(notes, {"o.zip: stopped reading, more than 3 entries"})


class DedupeResilienceTest(Base):
    def test_one_corrupt_member_does_not_disable_dedupe(self):
        data = bytearray(zbytes({"a.log": b"same-content", "b.log": b"same-content", "bad.log": b"corruptme"}))
        i = data.index(b"corruptme"); data[i + 8] ^= 0x01        # CRC mismatch on read
        o = self.d / "o.zip"; o.write_bytes(bytes(data))
        srcs, notes = self.walk(o)
        self.assertEqual(len(srcs), 3)
        out = di.dedupe(srcs, notes)
        self.assertEqual([s.name for s in out], ["a.log", "bad.log"])
        self.assertIn("1 duplicate copy(ies) of o.zip > a.log skipped", notes)
        self.assertTrue(any("o.zip > bad.log: could not be hashed" in n and "not checked for duplicates" in n for n in notes), notes)


class TextOnlyZipSuffixTest(Base):
    def test_text_log_with_a_zip_appended_is_read_as_text(self):
        p = self.d / "pstack.log"; p.write_bytes(b"Thread 1 (x)\n" + zbytes({"x.log": b"1"}))
        self.assertTrue(zipfile.is_zipfile(p))
        srcs, notes = self.walk(p)
        self.assertEqual([s.label for s in srcs], ["pstack.log"])
        self.assertEqual(srcs[0].head(6), b"Thread")

    def test_zip_suffix_still_uses_zipfile(self):
        p = self.d / "x.zip"; p.write_bytes(b"junk first" + zbytes({"x.log": b"1"}))
        srcs, _ = self.walk(p)
        self.assertEqual([s.label for s in srcs], ["x.zip > x.log"])


class MacosxCountTest(Base):
    def test_zip_and_unzipped_folder_count_the_same_junk(self):
        z = self.d / "t.zip"; z.write_bytes(zbytes({"__MACOSX/x/._a": b"j", "__MACOSX/y/z/._b": b"j", "keep.log": b"ok"}))
        f = self.d / "folder"; (f / "__MACOSX" / "x").mkdir(parents=True); (f / "__MACOSX" / "y" / "z").mkdir(parents=True)
        (f / "__MACOSX" / "x" / "._a").write_text("j"); (f / "__MACOSX" / "y" / "z" / "._b").write_text("j"); (f / "keep2.log").write_text("ok")
        _, n1 = self.walk(z)
        _, n2 = self.walk(f)
        self.assertEqual(n1, {"2 macOS metadata file(s) skipped"})
        self.assertEqual(n2, n1)


class ReadTest(Base):
    def test_read_asks_for_no_more_than_size_plus_one(self):
        p = self.d / "a.log"; p.write_bytes(b"x" * 10)
        s = di.walk([p], set())[0]
        di.MAX_MEMBER = 10 ** 12
        calls = []
        real_open = s._open

        class Spy:
            def __init__(self, f): self.f = f
            def __enter__(self): self.f.__enter__(); return self
            def __exit__(self, *a): return self.f.__exit__(*a)
            def read(self, n=-1): calls.append(n); return self.f.read(n)
        s._open = lambda: Spy(real_open())
        self.assertEqual(s.read(), b"x" * 10)
        self.assertLessEqual(max(calls), 11)

    def test_read_still_detects_a_file_larger_than_its_declared_size(self):
        p = self.d / "a.log"; p.write_bytes(b"x" * 100)
        s = di.walk([p], set())[0]
        s.size = 10; di.MAX_MEMBER = 50
        with self.assertRaises(di.MemberTooLarge):
            s.read()
        di.MAX_MEMBER = 500
        self.assertEqual(len(s.read()), 100)


class HostHintChainTest(Base):
    def src(self, *parts):
        return di.Source(list(parts), 1, lambda: io.BytesIO(b"x"))

    def test_nearer_folder_beats_a_named_outer_zip(self):
        self.assertEqual(di.host_hint(self.src("ticket123.zip", "hostA/pstack.log")), "hostA")
        self.assertEqual(di.host_hint(self.src("ticket123.zip", "hostB/tmp/084321-09-21-2020/pstack.log")), "hostB")

    def test_inner_zip_per_host_still_works(self):
        self.assertEqual(di.host_hint(self.src("ticket123.zip", "PSTACK Logs/host61.zip", "tmp/084321-09-21-2020/pstack.log")), "host61")

    def test_generic_outer_name_and_named_outer_without_folders(self):
        self.assertEqual(di.host_hint(self.src("PSTACK Logs.zip", "host63/tmp/084321-09-21-2020/pstack.log")), "host63")
        self.assertEqual(di.host_hint(self.src("ticket123.zip", "tmp/084321-09-21-2020/pstack.log")), "ticket123")
        self.assertIsNone(di.host_hint(self.src("PSTACK Logs.zip", "PSTACK Logs/tmp/084321-09-21-2020/pstack.log")))

    def test_disambiguate_appends_the_last_part_only_to_clashing_hosts(self):
        entries = [{"host": "h9", "label": "a.zip > a.log"}, {"host": "H9", "label": "b.zip > b.log"}, {"host": "other", "label": "o.log"},
                   {"host": "h9", "label": "c.zip > " + "d" * 60 + ".log"}]
        di.disambiguate(entries)
        self.assertEqual([e["host"] for e in entries][:3], ["h9 (a.log)", "H9 (b.log)", "other"])
        self.assertLessEqual(len(entries[3]["host"]), len("h9 ()") + 30)


if __name__ == "__main__":
    unittest.main()
