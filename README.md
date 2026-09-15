# marklogic-support-skill

A [pi](https://pi.dev) agent skill for MarkLogic support engineers. Triages tickets across
configuration, security, performance/tuning, monitoring, DR/scaling, server-side code
(XQuery/JS/REST extensions), and client-side integration tooling (XCC, Java Client API,
mlcp, ml-gradle, CoRB2) — and analyses MarkLogic support dumps and logs into an incident
timeline and ranked findings.

## Install (pi)

```bash
# Available in every project on your machine:
pi install git:github.com/mwarnes/marklogic-support-skill

# Or scoped to one project, shared via that project's .pi/settings.json:
pi install git:github.com/mwarnes/marklogic-support-skill -l
```

`pi install` writes to `~/.pi/agent/settings.json` by default (`-l` writes to the project's
`.pi/settings.json` instead). If a project's `.pi/settings.json` is committed to a shared repo,
pi installs this skill automatically for every engineer on trust — no manual step per person.

No dependencies to install — the skill's two scripts (`parse_dump.py`, `analyse_logs.py`) are
Python 3 stdlib only.

## Use

```
/skill:marklogic-support <ticket text, question, or a support-dump/log file path>
```

The skill classifies the input (ticket / question / support dump / log files) and routes to
the right reference domain automatically. See `skills/marklogic-support/SKILL.md` for the full
routing table and output format.

## What's included

```
skills/marklogic-support/
├── SKILL.md                     triage method, routing table, dump/log modes
├── scripts/
│   ├── parse_dump.py            splits a support dump into config/status/logs + findings
│   └── analyse_logs.py          classifies ErrorLog/messages/AccessLog/AuditLog into an
│                                 incident timeline + pattern summary
└── references/                  14 domains, each: Concepts → Standard procedures →
                                  Common mistakes & symptoms (sourced) → Sources
    architecture · cluster-hosts-groups · databases-forests · app-servers
    security (+ network hardening) · ha-backup-failover · memory-and-os
    monitoring · performance-tuning · dr-scaling
    app-code-review (server-side) · client-integration (XCC/Java/mlcp/ml-gradle/CoRB2)
    supportdump-anatomy · log-anatomy

tests/          unit tests for both scripts (unittest, stdlib only)
tools/          tools/check-ref.sh — validates the fixed reference-file shape
```

## Verifying / maintaining

Every mistake row in `references/*.md` cites a real doc URL, `Inside MarkLogic Server` PDF
page, or is explicitly marked `[unverified — confirm]` — never silently fabricated. Before
adding or editing a row: fetch the source, confirm it supports the exact claim, then run

```bash
tools/check-ref.sh skills/marklogic-support/references/<file>.md
python3 -m unittest tests.test_parse_dump tests.test_analyse_logs -v
```

## Using this skill outside pi

This skill follows the [Agent Skills standard](https://agentskills.io/specification)
(`SKILL.md` with YAML frontmatter + a `references/` directory), which several agent harnesses
support natively or with minor adaptation:

- **Claude Code**: drop `skills/marklogic-support/` into `~/.claude/skills/` (or a project's
  `.claude/skills/`) — Claude Code reads the same `SKILL.md` format directly.
- **OpenAI Codex / GitHub Copilot**: neither has first-class skill discovery yet as of this
  writing. `SKILL.md` plus `references/*.md` are still directly readable as project
  documentation — point the assistant at `skills/marklogic-support/SKILL.md` to have it follow
  the same triage method, or paste the relevant `references/*.md` file into context for a
  specific ticket. The two Python scripts (`parse_dump.py`, `analyse_logs.py`) work standalone
  from any shell regardless of which assistant is driving.

If your team needs first-class support in a specific harness, check that harness's docs for a
skills/plugin mechanism before assuming none exists — this is an active area and multiple
harnesses are converging on the same `SKILL.md` shape.

## License

MIT — see `package.json`.
