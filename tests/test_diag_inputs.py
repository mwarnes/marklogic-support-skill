import io, os, struct, sys, tempfile, unittest, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/marklogic-support/scripts"))
import diag_inputs as di


def zbytes(members, compression=zipfile.ZIP_STORED):
    """members: {name: bytes}; a name ending '/' is a directory entry."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", compression) as zf:
        for n, d in members.items():
            zf.writestr(n, d)
    return b.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.d = Path(self.tmp.name)
        for k in ("MAX_DEPTH", "MAX_MEMBER", "MAX_TOTAL", "MAX_MEMBERS", "RATIO_MIN_SIZE", "RATIO", "NESTED_BUDGET"):
            self.addCleanup(setattr, di, k, getattr(di, k))

    def walk(self, *paths):
        notes = set()
        srcs = di.walk(paths, notes)
        self.addCleanup(di.close_all, srcs)
        return srcs, notes


class WalkTest(Base):
    def test_plain_file(self):
        p = self.d / "pstack.log"; p.write_bytes(b"hello world")
        srcs, notes = self.walk(p)
        s = srcs[0]
        self.assertEqual((s.label, s.name, s.size, s.parts), ("pstack.log", "pstack.log", 11, ["pstack.log"]))
        self.assertEqual((s.head(5), s.read()), (b"hello", b"hello world"))
        self.assertEqual(len(s.sha256()), 64)
        self.assertEqual(notes, set())

    def test_missing_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            di.walk([self.d / "nope"], set())

    def test_directory_is_recursive_and_sorted(self):
        for n in ("b/z.log", "a.log", "b/a.log", "c/d/e.log"):
            (self.d / n).parent.mkdir(parents=True, exist_ok=True); (self.d / n).write_text(n)
        srcs, _ = self.walk(self.d)
        self.assertEqual([s.label for s in srcs], ["a.log", "b/a.log", "b/z.log", "c/d/e.log"])
        self.assertEqual(srcs[1].name, "a.log")

    def test_zip_member_label_and_content(self):
        z = self.d / "t.zip"; z.write_bytes(zbytes({"tmp/1/pstack.log": b"abc", "tmp/.ICE-unix/": b""}))
        srcs, notes = self.walk(z)
        self.assertEqual([s.label for s in srcs], ["t.zip > tmp/1/pstack.log"])
        s = srcs[0]
        self.assertEqual((s.name, s.size, s.read(), s.head(2)), ("pstack.log", 3, b"abc", b"ab"))
        self.assertEqual(s.sha256(), di.hashlib.sha256(b"abc").hexdigest())
        self.assertEqual(notes, set())

    def test_zip_detected_by_content_without_suffix(self):
        z = self.d / "bundle.dat"; z.write_bytes(zbytes({"x.log": b"1"}))
        srcs, _ = self.walk(z)
        self.assertEqual([s.label for s in srcs], ["bundle.dat > x.log"])

    def test_zip_in_zip_in_zip_has_full_chain(self):
        inner = zbytes({"tmp/084321-09-21-2020/pstack.log": b"data"})
        mid = zbytes({"host61.zip": inner})
        outer = self.d / "PSTACK Logs.zip"; outer.write_bytes(zbytes({"PSTACK Logs/": b"", "m.zip": mid}))
        srcs, notes = self.walk(outer)
        self.assertEqual([s.label for s in srcs],
                         ["PSTACK Logs.zip > m.zip > host61.zip > tmp/084321-09-21-2020/pstack.log"])
        self.assertEqual(srcs[0].parts, ["PSTACK Logs.zip", "m.zip", "host61.zip", "tmp/084321-09-21-2020/pstack.log"])
        self.assertEqual(srcs[0].read(), b"data")
        self.assertEqual(notes, set())

    def test_depth_limit_note(self):
        inner = zbytes({"a.log": b"x"})
        outer = self.d / "o.zip"; outer.write_bytes(zbytes({"i.zip": inner}))
        di.MAX_DEPTH = 1
        srcs, notes = self.walk(outer)
        self.assertEqual(srcs, [])
        self.assertEqual(notes, {"o.zip > i.zip: not opened, zips nested more than 1 deep"})

    def test_macos_junk_skipped_and_counted_once(self):
        z = self.d / "t.zip"
        z.write_bytes(zbytes({"__MACOSX/x/._pstack.log": b"j", "x/._a": b"j", "x/.DS_Store": b"j", "Thumbs.db": b"j",
                              "desktop.ini": b"j", "x/pstack.log": b"ok"}))
        (self.d / "dir").mkdir(); (self.d / "dir" / ".DS_Store").write_text("j"); (self.d / "dir" / "._b").write_text("j")
        (self.d / "dir" / "keep.log").write_text("ok")
        srcs, notes = self.walk(z, self.d / "dir")
        self.assertEqual([s.label for s in srcs], ["t.zip > x/pstack.log", "keep.log"])
        self.assertEqual(notes, {"7 macOS metadata file(s) skipped"})

    def test_corrupt_zip_note(self):
        z = self.d / "bad.zip"; z.write_bytes(b"PK\x03\x04 this is not a zip")
        srcs, notes = self.walk(z)
        self.assertEqual(srcs, [])
        self.assertEqual(notes, {"bad.zip: not a readable zip file"})

    def test_corrupt_inner_zip_note(self):
        o = self.d / "o.zip"; o.write_bytes(zbytes({"h.zip": b"PK\x03\x04junk", "ok.log": b"1"}))
        srcs, notes = self.walk(o)
        self.assertEqual([s.label for s in srcs], ["o.zip > ok.log"])
        self.assertEqual(notes, {"o.zip > h.zip: not a readable zip file"})

    def test_member_over_max_member_skipped_with_note(self):
        o = self.d / "o.zip"; o.write_bytes(zbytes({"big.log": b"x" * 100, "small.log": b"x"}))
        di.MAX_MEMBER = 50
        srcs, notes = self.walk(o)
        self.assertEqual([s.name for s in srcs], ["small.log"])
        self.assertEqual(len(notes), 1)
        self.assertTrue(next(iter(notes)).startswith("o.zip > big.log: skipped, larger than "))

    def test_plain_file_over_max_member_skipped_with_note(self):
        (self.d / "big.log").write_bytes(b"x" * 100)
        di.MAX_MEMBER = 50
        srcs, notes = self.walk(self.d)
        self.assertEqual(srcs, [])
        self.assertTrue(any(n.startswith("big.log: skipped, larger than ") for n in notes), notes)

    def test_read_enforces_the_limit_even_if_the_header_lies(self):
        o = self.d / "o.zip"; o.write_bytes(zbytes({"a.log": b"x" * 100}))
        (self.d / "p.log").write_bytes(b"y" * 100)
        srcs, _ = self.walk(o, self.d / "p.log")
        self.assertEqual(len(srcs), 2)
        di.MAX_MEMBER = 50
        for s in srcs:
            with self.assertRaises(di.MemberTooLarge):
                s.read()

    def test_total_limit_stops_with_a_note(self):
        o = self.d / "o.zip"; o.write_bytes(zbytes({"a.log": b"x" * 40, "b.log": b"x" * 40, "c.log": b"x" * 40}))
        di.MAX_TOTAL = 100
        srcs, notes = self.walk(o)
        self.assertEqual([s.name for s in srcs], ["a.log", "b.log"])
        self.assertEqual(len(notes), 1)
        self.assertTrue(next(iter(notes)).startswith("o.zip: stopped reading, more than "), notes)

    def test_member_count_limit_stops_with_a_note(self):
        o = self.d / "o.zip"; o.write_bytes(zbytes({f"f{i}.log": b"x" for i in range(5)}))
        di.MAX_MEMBERS = 3
        srcs, notes = self.walk(o)      # the declared count is checked before the zip is opened (see test_diag_inputs_hardening)
        self.assertEqual(srcs, [])
        self.assertEqual(notes, {"o.zip: stopped reading, more than 3 entries"})

    def test_encrypted_member_note(self):
        data = bytearray(zbytes({"secret.log": b"abc", "ok.log": b"1"}))
        i = data.index(b"PK\x01\x02")          # first central directory entry: general purpose flags at offset 8
        data[i + 8] |= 0x1
        o = self.d / "o.zip"; o.write_bytes(bytes(data))
        srcs, notes = self.walk(o)
        self.assertEqual([s.name for s in srcs], ["ok.log"])
        self.assertEqual(notes, {"o.zip > secret.log: skipped, password-protected"})

    def test_suspicious_compression_ratio_skipped(self):
        o = self.d / "o.zip"; o.write_bytes(zbytes({"z.log": b"\0" * 100000}, zipfile.ZIP_DEFLATED))
        di.RATIO_MIN_SIZE = 1000; di.RATIO = 50
        srcs, notes = self.walk(o)
        self.assertEqual(srcs, [])
        self.assertEqual(notes, {"o.zip > z.log: skipped, suspicious compression ratio"})

    def test_labels_never_contain_dotdot_or_leading_slash(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as zf:
            zf.writestr("../../etc/evil.log", b"x"); zf.writestr("/abs/p.log", b"x"); zf.writestr("a/../b/c.log", b"x")
        o = self.d / "o.zip"; o.write_bytes(b.getvalue())
        srcs, _ = self.walk(o)
        self.assertEqual(len(srcs), 3)
        for s in srcs:
            self.assertNotIn("..", s.label)
            self.assertFalse(any(p.startswith("/") for p in s.parts))
        self.assertEqual(sorted(s.label for s in srcs), ["o.zip > a/b/c.log", "o.zip > abs/p.log", "o.zip > etc/evil.log"])

    def test_nothing_is_written_to_disk(self):
        o = self.d / "o.zip"; o.write_bytes(zbytes({"../x.log": b"1", "i.zip": zbytes({"y.log": b"2"})}))
        before = sorted(os.listdir(self.d))
        srcs, _ = self.walk(o)
        [s.read() for s in srcs]
        self.assertEqual(sorted(os.listdir(self.d)), before)

    def test_realistic_layout(self):
        log = b"Thread 1 (Thread 0x1 (LWP 1)):\n#0  0x1 in poll ()\n"
        ts = "tmp/084321-09-21-2020/pstack.log"
        hosts = {f"PSTACK Logs/host{n}.zip": zbytes({ts: log, "tmp/.ICE-unix/": b""}) for n in (61, 62)}
        outer = self.d / "PSTACK Logs.zip"
        outer.write_bytes(zbytes({**hosts, "PSTACK Logs/" + ts: log, "PSTACK Logs/tmp 2/084321-09-21-2020/pstack.log": log,
                                  "__MACOSX/PSTACK Logs/._host61.zip": b"j", "PSTACK Logs/.DS_Store": b"j"}))
        srcs, notes = self.walk(outer)
        self.assertEqual(len(srcs), 4)
        srcs = di.dedupe(srcs, notes)
        self.assertEqual(len(srcs), 1)
        self.assertEqual([n for n in notes if "duplicate" in n], [f"3 duplicate copy(ies) of {srcs[0].label} skipped"])
        self.assertIn("2 macOS metadata file(s) skipped", notes)


class HostHintTest(Base):
    def src(self, *parts):
        return di.Source(list(parts), 1, lambda: io.BytesIO(b"x"))

    def test_inner_zip_name(self):
        self.assertEqual(di.host_hint(self.src("PSTACK Logs.zip", "PSTACK Logs/host61.zip", "tmp/084321-09-21-2020/pstack.log")), "host61")

    def test_nearest_zip_wins(self):
        self.assertEqual(di.host_hint(self.src("cluster7.zip", "host61.zip", "pstack.log")), "host61")

    def test_folder_name(self):
        self.assertEqual(di.host_hint(self.src("host62/pstack.log")), "host62")
        self.assertEqual(di.host_hint(self.src("host62/tmp/084321-09-21-2020/pstack.log")), "host62")

    def test_generic_and_timestamp_names_give_none(self):
        self.assertIsNone(di.host_hint(self.src("PSTACK Logs.zip", "PSTACK Logs/tmp/084321-09-21-2020/pstack.log")))
        self.assertIsNone(di.host_hint(self.src("Perfdata.zip", "Logs/Data/x.log")))
        self.assertIsNone(di.host_hint(self.src("pstack.log")))
        self.assertIsNone(di.host_hint(self.src("084321-09-21-2020/pstack.log")))

    def test_generic_zip_falls_back_to_folder(self):
        self.assertEqual(di.host_hint(self.src("PSTACK Logs.zip", "host63/tmp/084321-09-21-2020/pstack.log")), "host63")


class DedupeTest(Base):
    def test_first_of_identical_kept_with_one_note_per_kept(self):
        for n, c in (("a.log", b"same"), ("b.log", b"same"), ("c.log", b"same"), ("d.log", b"other"), ("e.log", b"sam")):
            (self.d / n).write_bytes(c)
        srcs, notes = self.walk(self.d)
        out = di.dedupe(srcs, notes)
        self.assertEqual([s.label for s in out], ["a.log", "d.log", "e.log"])
        self.assertEqual(notes, {"2 duplicate copy(ies) of a.log skipped"})

    def test_no_duplicates_no_note(self):
        (self.d / "a.log").write_bytes(b"1"); (self.d / "b.log").write_bytes(b"2")
        srcs, notes = self.walk(self.d)
        self.assertEqual(len(di.dedupe(srcs, notes)), 2)
        self.assertEqual(notes, set())


if __name__ == "__main__":
    unittest.main()
