import csv, json, os, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/marklogic-support/scripts/analyse_pstack.py"
FIX = Path(__file__).with_name("fixture_pstack") / "pstack-sample.log"
sys.path.insert(0, str(SCRIPT.parent))
import analyse_pstack as ap


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def thread(tid, lwp, *frames):
    return f"Thread {tid} (Thread 0x7f0000000{tid:03d} (LWP {lwp})):\n" + "".join(
        f"#{i}  0x0000000000{i:06x} in {f}\n" for i, f in enumerate(frames))


IDLE = ("sem_wait () from /lib64/libpthread.so.0", "svc::Semaphore::wait(bool) const ()", "svc::PooledThread::run() ()")
BUSY = ("xdmp::Foo::spin(unsigned int) ()", "xdmp::Bar::eval() ()", "xdmp::AppRequestTask::run() ()")


class BaseTest(unittest.TestCase):
    def test_base_strips_library_arguments_and_versions(self):
        self.assertEqual(ap.base("sem_wait () from /lib64/libpthread.so.0"), "sem_wait")
        self.assertEqual(ap.base("xdmp::Foo::bar(unsigned int, bool) const ()"), "xdmp::Foo::bar")
        self.assertEqual(ap.base("pthread_cond_wait@@GLIBC_2.3.2 () from /lib64/libpthread.so.0"), "pthread_cond_wait")
        self.assertEqual(ap.base("std::vector<unsigned int, std::allocator<unsigned int> >::reserve(unsigned long) ()"),
                         "std::vector<unsigned int, std::allocator<unsigned int> >::reserve")
        self.assertEqual(ap.base("?? ()"), "??")

    def test_classify(self):
        self.assertEqual(ap.classify("poll"), "waiting")
        self.assertEqual(ap.classify("pthread_cond_timedwait"), "waiting")
        self.assertEqual(ap.classify("__lll_lock_wait"), "lock")
        self.assertEqual(ap.classify("sched_yield"), "lock")
        self.assertEqual(ap.classify("madvise"), "running")


class ParseTest(unittest.TestCase):
    def test_numbering_restart_splits_snapshots_and_banner_is_ignored(self):
        text = "MarkLogic - banner\n" + thread(3, 11, *IDLE) + thread(2, 12, *IDLE) + thread(3, 11, *IDLE) + thread(2, 12, *BUSY)
        notes = set()
        snaps = ap.parse_text(text, "x", notes)
        self.assertEqual([len(s["threads"]) for s in snaps], [2, 2])
        self.assertIn("x: 1 line(s) of text outside thread blocks were ignored", notes)
        self.assertFalse(any("banner" in n for n in notes))

    def test_date_lines_split_snapshots_and_are_recorded(self):
        text = ("Tue Oct 21 10:00:01 UTC 2026\n" + thread(2, 1, *IDLE) + "Tue Oct 21 10:00:06 UTC 2026\n" + thread(2, 1, *IDLE))
        snaps = ap.parse_text(text, "x", set())
        self.assertEqual([s["date"] for s in snaps], ["Tue Oct 21 10:00:01 UTC 2026", "Tue Oct 21 10:00:06 UTC 2026"])

    def test_gdb_quoted_thread_names_parse(self):
        text = 'Thread 3 (Thread 0x7f0000000003 (LWP 77) "MarkLogic"):\n#0  0x0000000000000001 in poll () from /lib64/libc.so.6\n'
        snaps = ap.parse_text(text, "x", set())
        self.assertEqual((snaps[0]["threads"][0]["lwp"], snaps[0]["threads"][0]["frames"]), (77, ["poll"]))

    def test_dated_snapshots_with_ascending_thread_numbers_are_not_split_again(self):
        snap = lambda d: d + "\n" + thread(2, 1, *IDLE) + thread(3, 2, *IDLE) + thread(4, 3, *BUSY)
        text = "".join(snap(f"Tue Oct 21 10:00:0{i} UTC 2026") for i in range(3))
        snaps = ap.parse_text(text, "x", set())
        self.assertEqual([len(s["threads"]) for s in snaps], [3, 3, 3])

    def test_undated_ascending_numbers_still_split(self):
        snaps = ap.parse_text(thread(2, 1, *IDLE) + thread(3, 2, *IDLE), "x", set())
        self.assertEqual([len(s["threads"]) for s in snaps], [1, 1])

    def test_date_line_formats(self):
        for d in ("Tue Oct 21 10:00:01 AM UTC 2026", "Tue 21 Oct 2026 10:00:01 UTC", "Tue Oct 21 10:00:01 +03 2026",
                  "Tue 21 Oct 10:00:01 BST 2026", "Tue Oct 21 10:00:01 UTC 2026"):
            text = d + "\n" + thread(2, 1, *IDLE) + d.replace("10:00:01", "10:00:06") + "\n" + thread(2, 1, *IDLE)
            snaps = ap.parse_text(text, "x", set())
            self.assertEqual([len(s["threads"]) for s in snaps], [1, 1], d)
            self.assertEqual(snaps[1]["date"], d.replace("10:00:01", "10:00:06"))

    def test_frame_lines_and_banners_are_never_dates(self):
        text = thread(2, 1, "foo () 10:00:01 2026", *IDLE) + "#9  bar 10:00:01 2026\n" + "MarkLogic 2026 banner\n"
        snaps = ap.parse_text(text, "x", set())
        self.assertEqual(len(snaps), 1)
        self.assertIsNone(snaps[0]["date"])

    def test_crlf_input_parses(self):
        text = ("Tue Oct 21 10:00:01 UTC 2026\n" + thread(2, 1, *IDLE) + "Tue Oct 21 10:00:06 UTC 2026\n" + thread(2, 1, *BUSY)).replace("\n", "\r\n")
        snaps = ap.parse_text(text, "x", set())
        self.assertEqual([len(s["threads"]) for s in snaps], [1, 1])
        self.assertEqual(snaps[0]["threads"][0]["frames"][0], "sem_wait")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "crlf.log"; p.write_bytes(text.encode())
            r = run(p, "--out", Path(d) / "o")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("2 snapshot(s)", r.stdout)


class NormaliseTest(unittest.TestCase):
    def test_norm(self):
        for raw, want in (("__GI___poll", "poll"), ("do_futex_wait.constprop.1", "do_futex_wait"), ("__libc_read", "read"),
                          ("foo.isra.0", "foo"), ("bar.part.12", "bar"), ("baz.cold", "baz"), ("__lll_lock_wait", "lll_lock_wait"),
                          ("__GI___libc_read", "read"), ("je_arena_purge", "arena_purge"), ("xdmp::Foo::bar", "xdmp::Foo::bar")):
            self.assertEqual(ap.norm(raw), want, raw)

    def test_modern_wait_stacks_are_waiting(self):
        for frames in (["do_futex_wait.constprop.1", "__new_sem_wait_slow", "sem_wait"], ["futex_wait_cancelable", "__pthread_cond_wait"],
                       ["__GI___poll"], ["syscall", "futex_wait"], ["__futex_abstimed_wait_common64", "sem_clockwait"],
                       ["epoll_pwait"], ["pthread_cond_clockwait"], ["__GI___libc_read"], ["sem_wait", "xdmp::X"], ["xdmp::X", "__GI___poll"]):
            self.assertEqual(ap.classify(frames), "waiting", frames)

    def test_lock_rules(self):
        self.assertEqual(ap.classify(["futex_wait", "__lll_lock_wait", "pthread_mutex_lock"]), "lock")
        self.assertEqual(ap.classify(["__lll_lock_wait_private", "xdmp::X"]), "lock")
        self.assertEqual(ap.classify(["pthread_mutex_clocklock", "xdmp::X"]), "lock")
        self.assertEqual(ap.classify(["xdmp::X", "pthread_mutex_lock", "xdmp::Y"]), "running")
        self.assertEqual(ap.classify(["syscall", "xdmp::X"]), "running")
        self.assertEqual(ap.classify(["syscall", "__lll_lock_wait"]), "lock")
        self.assertEqual(ap.classify(["xdmp::X", "xdmp::Y", "xdmp::Z", "poll"]), "running")

    def test_idle_modern_threads_across_snapshots_are_not_a_stuck_finding(self):
        idles = [("do_futex_wait.constprop.1 ()", "__new_sem_wait_slow ()", "sem_wait ()"), ("futex_wait_cancelable ()", "pthread_cond_wait ()"),
                 ("__GI___poll () from /lib64/libc.so.6",), ("syscall ()", "futex_wait ()"), ("do_futex_wait.constprop.1 ()", "__new_sem_wait_slow ()", "sem_wait ()")]
        text = "".join("".join(thread(7 - i, 10 + i, *fr) for i, fr in enumerate(idles)) for _ in range(3))
        snaps = ap.parse_text(text, "x", set())
        self.assertEqual([len(s["threads"]) for s in snaps], [5, 5, 5])
        rows, findings, _ = ap.analyse(snaps, 3, 3)
        self.assertNotIn("same_stack_across_snapshots", {f["rule"] for f in findings})
        self.assertEqual([r["waiting"] for r in rows], [5, 5, 5])


class RuleTest(unittest.TestCase):
    def analyse(self, text, **kw):
        snaps = ap.parse_text(text, "x", set())
        rows, findings, _ = ap.analyse(snaps, kw.get("min_samples", 3), kw.get("min_threads", 3))
        return rows, {f["rule"]: f for f in findings}

    def test_same_running_stack_in_consecutive_snapshots_is_flagged_but_waiting_is_not(self):
        text = "".join(thread(3, 1, *BUSY) + thread(2, 2, *IDLE) for _ in range(3))
        _, f = self.analyse(text)
        self.assertIn("same_stack_across_snapshots", f)
        self.assertEqual([t["lwp"] for t in f["same_stack_across_snapshots"]["threads"]], [1])
        _, f = self.analyse(text, min_samples=4)
        self.assertNotIn("same_stack_across_snapshots", f)

    def test_stack_change_breaks_the_run(self):
        text = thread(2, 1, *BUSY) + thread(2, 1, "other () ", *BUSY[1:]) + thread(2, 1, *BUSY)
        _, f = self.analyse(text)
        self.assertNotIn("same_stack_across_snapshots", f)

    def test_pattern_needs_min_threads(self):
        purge = ("madvise () from /lib64/libc.so.6", "pages_purge ()", "arena_purge ()", "free ()")
        text = thread(4, 1, *purge) + thread(3, 2, *purge) + thread(2, 3, *purge) + thread(4, 1, *IDLE)
        _, f = self.analyse(text)
        self.assertEqual(f["allocator_purge"]["threads_per_snapshot"], [3])
        _, f = self.analyse(text, min_threads=4)
        self.assertNotIn("allocator_purge", f)

    def test_lock_wait_is_a_lock_class_not_running(self):
        text = thread(2, 1, "__lll_lock_wait () from /lib64/libpthread.so.0", "pthread_mutex_lock ()", "arena_malloc_large ()", "tcache_create ()")
        rows, f = self.analyse(text, min_threads=1)
        self.assertEqual((rows[0]["lock"], rows[0]["running"]), (1, 0))
        self.assertIn("allocator_lock_wait", f)

    def test_allocator_patterns_are_prefix_tolerant(self):
        purge = ("madvise ()", "je_pages_purge_forced ()", "je_arena_decay_to_limit ()", "free ()")
        flush = ("je_tcache_bin_flush_small ()", "je_tcache_destroy ()", "xdmp::Foo ()")
        text = "".join(thread(4, 1, *purge) + thread(3, 2, *purge) + thread(2, 3, *flush) for _ in range(1))
        rows, f = self.analyse(text, min_threads=1)
        self.assertEqual(rows[0]["allocator_purge"], 2)
        self.assertEqual(rows[0]["thread_cache_flush"], 1)
        text = thread(4, 1, "thread_tcache_flush ()") + thread(3, 2, "tcache_event ()") + thread(2, 3, "arena_decay_all ()")
        rows, _ = self.analyse(text, min_threads=1)
        self.assertEqual((rows[0]["thread_cache_flush"], rows[0]["allocator_purge"]), (2, 1))

    def test_modern_lock_under_arena_is_allocator_lock_wait(self):
        text = thread(2, 1, "futex_wait ()", "lll_lock_wait ()", "pthread_mutex_lock ()", "je_arena_malloc_hard ()")
        _, f = self.analyse(text, min_threads=1)
        self.assertIn("allocator_lock_wait", f)

    def test_bursty_rule_unit(self):
        purge = ("pages_purge ()",)
        def snaps(counts):
            return "".join("Tue Oct 21 10:00:0%d UTC 2026\n" % i + "".join(thread(2 + j, 100 + j, *purge) for j in range(c)) + thread(30, 999, *IDLE)
                           for i, c in enumerate(counts))
        _, f = self.analyse(snaps([3, 0, 3]))
        self.assertEqual(f["bursty_allocator_purge"]["snapshots"], [1, 3])
        _, f = self.analyse(snaps([3, 1, 3]))
        self.assertNotIn("bursty_allocator_purge", f)
        _, f = self.analyse(snaps([3, 0]))
        self.assertNotIn("bursty_allocator_purge", f)

    def test_thread_churn_unit(self):
        def snaps(extra):
            out = ""
            for i in range(3):
                out += "Tue Oct 21 10:00:0%d UTC 2026\n" % i
                out += "".join(thread(2 + j, 100 + j, *IDLE) for j in range(10))
                out += "".join(thread(20 + j, 500 + 10 * i + j, *IDLE) for j in range(extra))
            return out
        _, f = self.analyse(snaps(2))
        self.assertIn("thread_churn", f)
        self.assertIn("6 of 16 threads", f["thread_churn"]["detail"])
        _, f = self.analyse(snaps(0))
        self.assertNotIn("thread_churn", f)


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.out = Path(cls.tmp.name) / "out"
        r = run(FIX, "--out", cls.out)
        assert r.returncode == 0, r.stderr
        cls.stdout = r.stdout
        cls.findings = {f["rule"]: f for f in json.loads((cls.out / "findings.json").read_text())}
        with (cls.out / "snapshots.csv").open() as fh:
            cls.rows = list(csv.DictReader(fh))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_four_snapshots_with_thread_counts_and_classes(self):
        self.assertIn("1 input(s), 4 snapshot(s)", self.stdout)
        self.assertEqual([int(r["threads"]) for r in self.rows], [28, 6, 22, 5])
        first = self.rows[0]
        self.assertEqual((first["waiting"], first["lock"], first["running"]), ("4", "3", "21"))

    def test_allocator_purge_bursts_in_snapshots_1_and_3(self):
        f = self.findings["allocator_purge"]
        self.assertEqual((f["snapshots"], f["threads_per_snapshot"]), ([1, 3], [15, 12]))
        self.assertEqual(self.findings["bursty_allocator_purge"]["snapshots"], [1, 3])
        self.assertEqual(self.findings["thread_cache_flush"]["threads_per_snapshot"], [14, 11])

    def test_lock_and_cache_patterns_below_threshold_are_not_reported(self):
        self.assertNotIn("allocator_lock_wait", self.findings)
        self.assertNotIn("list_cache_lock_wait", self.findings)

    def test_likely_cause_rules_come_first(self):
        sev = [f["severity"] for f in json.loads((self.out / "findings.json").read_text())]
        self.assertEqual(sev, sorted(sev))

    def test_summary_has_no_raw_stacks_and_states_its_limits(self):
        s = (self.out / "SUMMARY.md").read_text()
        self.assertNotIn("#0 ", s)
        self.assertLess(len(s.splitlines()), 90)
        self.assertIn("no date lines", s)
        self.assertIn("`madvise`", s)
        self.assertIn("[unverified — confirm]", s)


class InputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.d = Path(self.tmp.name)

    def test_zip_input_is_read(self):
        z = self.d / "t.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("101530-10-21-2026/pstack.log", FIX.read_text())
            zf.writestr("notes.txt", "no threads here")
        r = run(z, "--out", self.d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 input(s), 4 snapshot(s)", r.stdout)

    def test_directory_input_and_non_pstack_files(self):
        (self.d / "a.log").write_text(FIX.read_text()); (self.d / "b.txt").write_text("hello\n")
        r = run(self.d, "--out", self.d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("skipped, no 'Thread N (...)' blocks", (self.d / "o" / "SUMMARY.md").read_text())

    def test_no_pstack_data_and_missing_path_are_errors(self):
        (self.d / "x.txt").write_text("nothing\n")
        r = run(self.d / "x.txt", "--out", self.d / "o")
        self.assertNotEqual(r.returncode, 0); self.assertIn("no pstack data", r.stderr)
        r = run(self.d / "missing.log")
        self.assertNotEqual(r.returncode, 0); self.assertIn("path not found", r.stderr)

    def test_option_validation(self):
        for opt in ("--min-samples", "--min-threads"):
            r = run(FIX, opt, 0)
            self.assertEqual(r.returncode, 2, opt)

    def test_oversize_files_and_zip_members_are_skipped_with_a_note(self):
        (self.d / "big.log").write_text(FIX.read_text())
        with zipfile.ZipFile(self.d / "t.zip", "w") as zf:
            zf.writestr("in/pstack.log", FIX.read_text())
        old = ap.MAX_BYTES
        ap.MAX_BYTES = 1000
        self.addCleanup(setattr, ap, "MAX_BYTES", old)
        notes = set()
        self.assertEqual(ap.read_inputs([self.d / "big.log"], notes), [])
        self.assertTrue(any("big.log" in n and "larger than" in n for n in notes), notes)
        zf_notes = set()
        with zipfile.ZipFile(self.d / "z2.zip", "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("in/pstack.log", FIX.read_text())
        ap.MAX_BYTES = 20000
        self.assertEqual(len(FIX.read_bytes()) > 20000, True)
        self.assertEqual(ap.read_inputs([self.d / "z2.zip"], zf_notes), [])
        self.assertTrue(any("in/pstack.log" in n and "larger than" in n for n in zf_notes), zf_notes)

    def test_unreadable_file_adds_a_note(self):
        p = self.d / "locked.log"; p.write_text(FIX.read_text()); os.chmod(p, 0)
        self.addCleanup(os.chmod, p, 0o600)
        if os.access(p, os.R_OK):
            self.skipTest("running with privileges that ignore file modes")
        notes = set()
        ap.read_inputs([p], notes)
        self.assertTrue(any("locked.log" in n and "could not be read" in n for n in notes), notes)

    def test_binary_files_in_a_directory_are_skipped_with_a_note(self):
        (self.d / "a.log").write_text(FIX.read_text())
        (self.d / "core.1234").write_bytes(b"\x7fELF\0\0\0" + b"Thread 1 (x LWP 1)" * 10)
        notes = set()
        out = ap.read_inputs([self.d], notes)
        self.assertEqual([n for n, _ in out], ["a.log"])
        self.assertTrue(any("core.1234" in n and "binary" in n for n in notes), notes)

    def test_outputs_are_utf8_whatever_the_locale(self):
        env = {**os.environ, "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0", "LC_ALL": "C"}
        r = subprocess.run([sys.executable, str(SCRIPT), str(FIX), "--out", str(self.d / "o")], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("—", (self.d / "o" / "SUMMARY.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
