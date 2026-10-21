import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
REQ = (SKILL / "references/performance-data-requests.md").read_text()
SOURCES = (SKILL / "references/sources.md").read_text()


def section(name):
    return REQ.split("## " + name + "\n", 1)[1].split("\n## ", 1)[0]


class StackAndPerfRequestTest(unittest.TestCase):
    def test_sections_exist_in_order_before_the_cloud_section(self):
        heads = [l[3:] for l in REQ.splitlines() if l.startswith("## ")]
        i = heads.index("Stack samples: pstack movie")
        self.assertEqual(heads[i:i + 4], ["Stack samples: pstack movie", "CPU profile: perf",
                                          "Memory growth: pmap", "Cloud-hosted customers"])
        self.assertNotIn("Hangs: thread dumps and pmap", heads)

    def test_pstack_request_follows_the_kb_procedure(self):
        s = section("Stack samples: pstack movie")
        for needle in ("assets/support-scripts/pstack.sh", "sudo ./pstack.sh 60", "yum -y install pstack sysstat psutils gdb",
                       "/etc/MarkLogic/proc-util.sh pstack", "service MarkLogic pstack", "11.3.1", "/tmp/",
                       "000266816", "creating-a-pstack-movie-for-support", "pauses", "while the problem is happening"):
            self.assertIn(needle, s, needle)
        self.assertIn("3 seconds", s)

    def test_perf_request_follows_the_kb_procedure(self):
        s = section("CPU profile: perf")
        for needle in ("yum install perf", "cd /tmp", "perf record -F 99 -ag -- sleep 60", "perf report --header -I --stdio",
                       "perf script", "same host", "000268341", "using-perf-to-understand-performance", "perf top"):
            self.assertIn(needle, s, needle)

    def test_old_unverified_manual_stack_commands_are_gone(self):
        self.assertNotIn("gdb -p <pid>", REQ)
        self.assertNotIn("pstack <pid>", REQ)
        self.assertNotIn("No official MarkLogic documentation or KB article describing process-level stack collection", REQ)

    def test_pmap_request_kept(self):
        self.assertIn("pmap -x <pid>", section("Memory growth: pmap"))

    def test_cloud_and_gate_rules_still_hold(self):
        before = REQ.split("## Cloud-hosted customers")[0]
        self.assertNotIn("EBS", before)
        self.assertIn("incident gate", REQ)
        self.assertNotIn("breach", REQ.lower())

    def test_sources_md_lists_both_kb_articles(self):
        for needle in ("https://community.progress.com/s/article/creating-a-pstack-movie-for-support",
                       "https://community.progress.com/s/article/using-perf-to-understand-performance",
                       "perf-record.1.html"):
            self.assertIn(needle, SOURCES, needle)


if __name__ == "__main__":
    unittest.main()
