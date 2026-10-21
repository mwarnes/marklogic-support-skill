import re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
REQ = SKILL / "references/performance-data-requests.md"
MON = SKILL / "references/monitoring.md"
SOURCES = SKILL / "references/sources.md"
SKILL_MD = SKILL / "SKILL.md"

PAGE = "https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/status.html#id_80312"
FUNCS = ["request-status", "server-status", "host-status", "forest-status", "request-cancel", "forest-counts"]
URLS = ["https://docs.marklogic.com/xdmp:" + f for f in FUNCS]


def section():
    text = REQ.read_text()
    return text.split("## Running requests: request and server status")[1].split("\n## ")[0]


class StatusCaptureDocsTest(unittest.TestCase):
    def test_section_position(self):
        heads = [l[3:] for l in REQ.read_text().splitlines() if l.startswith("## ")]
        i = heads.index("Running requests: request and server status")
        self.assertEqual(heads[i - 1], "Kernel and OOM messages")
        self.assertEqual(heads[i + 1], "Stack samples: pstack movie")

    def test_section_content(self):
        s = section()
        self.assertIn("xdmp:server-status", s)
        self.assertIn("xdmp:request-status", s)
        self.assertIn("incident gate", s)
        self.assertIn("Engineer notes:", s)

    def test_cancel_only_in_engineer_notes(self):
        s = section()
        req, notes = s.split("Engineer notes:")
        self.assertNotIn("xdmp:request-cancel", "\n".join(l for l in req.splitlines() if l.startswith(">")))
        self.assertIn("xdmp:request-cancel", notes)
        self.assertIn("Monitoring History", notes)

    def test_file_length(self):
        self.assertLessEqual(len(REQ.read_text().splitlines()), 200)

    def test_monitoring_cites_pages(self):
        text = MON.read_text()
        src = SOURCES.read_text().split("## monitoring.md")[1].split("\n## ")[0]
        for u in URLS + [PAGE]:
            self.assertIn(u, text, u)
            self.assertIn(u, src, u)

    def test_privileges_recorded(self):
        text = MON.read_text()
        for p in ["privileges/status", "privileges/counts", "privileges/cancel-any-request",
                  "privileges/cancel-my-requests"]:
            self.assertIn(p, text, p)

    def test_no_breach(self):
        for p in (REQ, MON):
            self.assertNotIn("breach", p.read_text().lower())

    def test_skill_md(self):
        t = SKILL_MD.read_text()
        self.assertIn("For a stuck or slow request, also ask for the request/server status capture "
                      "(`references/performance-data-requests.md`) before anything is cancelled.", t)
        rows = [l for l in t.splitlines() if l.startswith("|") and "references/performance-data-requests.md" in l]
        self.assertEqual(len(rows), 1)
        self.assertIn("stuck query, request-status", rows[0].split("|")[1])


if __name__ == "__main__":
    unittest.main()
