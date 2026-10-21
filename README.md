# marklogic-support-skill

Agent skills for MarkLogic support engineers. They work with [pi](https://pi.dev),
[Claude Code](https://code.claude.com/docs/en/skills), [OpenAI Codex](https://learn.chatgpt.com/docs/build-skills)
and GitHub Copilot ([CLI, VS Code agent mode and the cloud agent](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/create-skills)),
because all four read skills in the [Agent Skills](https://agentskills.io/specification) format (a folder with a `SKILL.md`).

What they do:

- **Triage** MarkLogic tickets: configuration, security, performance/tuning, monitoring, DR/scaling,
  server-side code (XQuery/JS/REST extensions) and client tooling (XCC, Java Client API, mlcp, ml-gradle, CoRB2).
- **Analyse** MarkLogic support dumps, logs (ErrorLog, messages, AccessLog, AuditLog) and Linux SAR data into
  incident timelines and ranked findings, and ask the customer for the right host-level data when it is missing.
- **Write and review KCS articles** that follow the company Solution Content Standard.
- **Follow the Progress security process** for vulnerability and security-incident tickets.

## The skills

| Skill | What it does | How to start it |
| --- | --- | --- |
| `marklogic-support` | Triage method, reference notes, dump/log/SAR analysis. The other three skills build on it. | Describe the problem, or paste a ticket, a dump path or a log path |
| `ticket` | Creates the ticket folder and its audit trail, loads `marklogic-support`, asks for the problem description | `/ticket 12345` |
| `kcs` | Drafts a KCS article from a finished ticket and renders Markdown, Word and Salesforce HTML | `/kcs 12345` |
| `kcs-review` | Reviews another engineer's KCS article and writes the revised version | `/kcs-review path/to/article.md` |

How you start a skill depends on the agent:

| Agent | Starting `ticket` | Notes |
| --- | --- | --- |
| Claude Code | `/ticket 12345` | A skill is a slash command named after its folder |
| pi | `/skill:ticket 12345` | Text after the name is passed to the skill |
| Codex | `$ticket 12345` (or `/skills` to pick) | Codex can also pick a skill from its description |
| GitHub Copilot | `/ticket 12345` in VS Code chat; in the Copilot CLI, "use the /ticket skill for case 12345" | VS Code lists skills as slash commands when you type `/`; the CLI docs say to put the skill name, preceded by a forward slash, in your prompt. Copilot can also choose a skill from its description |

**Changed in 1.1:** `/ticket`, `/kcs` and `/kcs-review` used to be prompt templates (pi) and command files (Claude Code,
Codex). They are now skills, so in **pi** they are started as `/skill:ticket`, `/skill:kcs` and `/skill:kcs-review`
(`/ticket` no longer exists there); in **Claude Code** the commands are unchanged. Old copies of the command files are
listed by `./install.sh status` and moved aside by `./install.sh update --clean-legacy`.

## Requirements

- **Python 3** — the analysis, rendering and ticket scripts use the standard library only. On Windows the agent
  may need `python` or `py -3` where the skills say `python3`.
- **git** — to install and update.
- **[pandoc](https://pandoc.org/installing.html)** (optional) — Word and HTML output for `kcs`, and `.html`/`.docx`
  input for `kcs-review`. Everything else works without it.
- One of the four agents above.

## Install

The repository holds the skills in `skills/`. The installer links each skill folder into the two folders the
agents read, so there is one copy on disk and updating is a `git pull`:

| Folder | Read by |
| --- | --- |
| `~/.agents/skills/` | pi, Codex, GitHub Copilot |
| `~/.claude/skills/` | Claude Code (and GitHub Copilot in VS Code) |

The repository is private: you need read access to it and git credentials that work non-interactively
(for example `gh auth login` followed by `gh auth setup-git`, or an SSH key loaded in `ssh-agent`). Ask the
maintainer for access.

### macOS and Linux

```bash
git clone https://github.com/mwarnes/marklogic-support-skill.git ~/marklogic-support-skill
cd ~/marklogic-support-skill
./install.sh              # all four agents; see ./install.sh --help
./install.sh status       # check what is installed where
```

Then restart your agent if the skills do not appear (Codex's docs say to restart if an update is not picked up).

Options: `--agents pi,claude,codex,copilot` (default `all`), `--copy` (copy instead of link), `--force`
(replace a real folder or a link you made yourself; a `.bak-<time>` copy is kept), `--clean-legacy` (see Update).
A plain `./install.sh` replaces a `--copy` install with links, and links that point at another clone of this
repository (or at nothing) are re-pointed at this one.

### Windows

```powershell
git clone https://github.com/mwarnes/marklogic-support-skill.git $HOME\marklogic-support-skill
cd $HOME\marklogic-support-skill
powershell -ExecutionPolicy Bypass -File .\install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Command status
```

`install.ps1` links with directory junctions, which need no administrator rights. If an agent does not follow a
junction, use `-Copy`, and re-run `-Command update -Copy` after each update. Options: `-Agents`, `-Copy`, `-Force`,
`-NoPull`, `-CleanLegacy`. The Windows script is not run by the project's automated tests; please report problems.

### Per agent

- **Claude Code** — reads `~/.claude/skills/<name>/SKILL.md` and follows symlinked skill folders
  ([docs](https://code.claude.com/docs/en/skills)). Skills named `ticket`, `kcs` and `kcs-review` become
  `/ticket`, `/kcs` and `/kcs-review`.
- **pi** — reads `~/.agents/skills/` ([docs](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/skills.md)).
  You can also install the repository as a pi package instead of using the script:
  `pi install git:github.com/mwarnes/marklogic-support-skill` (add `-l` to install for one project and record it in `.pi/settings.json`).
- **Codex** — reads `~/.agents/skills/` and follows symlinked skill folders
  ([docs](https://learn.chatgpt.com/docs/build-skills)). Codex custom prompts (`~/.codex/prompts`) are
  [deprecated](https://learn.chatgpt.com/docs/custom-prompts) in favour of skills, which is why the
  workflows here are skills too.
- **GitHub Copilot** — personal skills: the Copilot CLI and cloud-agent docs list `~/.copilot/skills` and `~/.agents/skills`; `~/.claude/skills` is documented for VS Code only
  ([VS Code](https://code.visualstudio.com/docs/copilot/customization/agent-skills),
  [CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-skills)).
  The installer's `~/.agents/skills` link therefore covers all of them. Project skills live in `.github/skills/`,
  `.claude/skills/` or `.agents/skills/` inside a repository
  ([docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/create-skills)).
  The Copilot cloud agent runs on GitHub rather than on your machine, so a personal install here is not visible to it; the locations the docs list for it are inside the repository (`.github/skills/`, `.claude/skills/` or `.agents/skills/`).
  The docs describe no
  organisation-wide distribution of skills, so on Copilot Enterprise each engineer installs the skills with the
  script, or a team commits them under `.github/skills/` in its own repository. The GitHub CLI's `gh skill`
  command (preview, GitHub CLI 2.90 or later) can also install skills from a GitHub repository; its exact usage is
  not covered here.

### Without the script

```bash
mkdir -p ~/.agents/skills ~/.claude/skills
for s in marklogic-support ticket kcs kcs-review; do
  ln -sfn ~/marklogic-support-skill/skills/$s ~/.agents/skills/$s
  ln -sfn ~/marklogic-support-skill/skills/$s ~/.claude/skills/$s
done
```

Check first: `ln -sfn` replaces an existing link, and if the destination is a real folder it creates the link
*inside* that folder instead of replacing it. For one project only, create the same links under `<project>/.agents/skills/` (and `.claude/skills/` for Claude
Code, `.github/skills/` for Copilot).

## Update

```bash
cd ~/marklogic-support-skill
./install.sh update                 # git pull --ff-only, then re-link (picks up new skills); use --no-pull to skip the pull
./install.sh status
```

Windows: `powershell -ExecutionPolicy Bypass -File .\install.ps1 -Command update`. Restart the agent if the skills do not appear.

- Because the installed skills are links to the clone, a plain `git pull` also updates them. `update` additionally
  links skills added in the new version and reports the old and new commit.
- **pi package installs:** `pi update --extensions` updates all installed packages, or `pi update git:github.com/mwarnes/marklogic-support-skill`
  updates just this one (`pi update` on its own updates pi itself).
- **Copy installs** (`--copy` / `-Copy`) are not links: run `./install.sh update --copy` to refresh them.
- **Older versions of this repository** shipped `/ticket`, `/kcs` and `/kcs-review` as command files that people
  copied into `~/.claude/commands/` (or the pi/Codex prompt folders). Those copies do not update and are replaced by
  the skills. `install.sh` lists any it finds; `./install.sh update --clean-legacy` moves them aside to `.bak-<time>`.
- A skill link that pointed at a different clone is re-pointed at this one (the output says `relinked`).

## Use

Start a ticket, work it, and write it up:

```
/ticket 12345                     # creates 12345/audit-trail/, loads marklogic-support, asks for the problem
...triage, paste a dump or log path, a SAR file, ask follow-up questions...
/kcs 12345                        # draft the KCS article from the audit trail
/kcs-review path/to/article.md    # review someone else's article
```

Ticket folders are created under the git top-level directory (or the current directory if it is not a git
repository), so start the agent in the folder where you keep your tickets. (Use the form for your agent from the table above.) The skill classifies the input (ticket, question, support
dump, log files, SAR output) and routes to the right reference notes. See `skills/marklogic-support/SKILL.md`
for the routing table and output formats.

### Support dumps, logs and SAR data

`parse_dump.py` splits a support dump into config, status and logs with findings; `analyse_logs.py` classifies
ErrorLog, messages, AccessLog and AuditLog into an incident timeline; `analyse_sar.py` reads `sar -A` text output
and ranks saturation (iowait, disk latency, swap, memory, run queue, steal, network errors).
`performance-data-requests.md` holds ready-to-paste customer requests for SAR, iostat/vmstat/mpstat/pidstat,
kernel and OOM messages, the pstack movie and perf requests (from the Progress KB articles; the customer script is vendored at `skills/marklogic-support/assets/support-scripts/pstack.sh`) and, on cloud-hosted customers only, steal and EBS signals.
`analyse_pstack.py` reads a pstack movie (`pstack.log`, its zip or a folder): per snapshot the waiting, lock-wait
and running threads, allocator and lock patterns, threads that stay in the same stack and thread churn.
`analyse_perf.py` reads a `perf report --stdio` text report: kernel versus user time, time under a user-space
wrapper, unresolved kernel symbols and the top symbols. `pstack-analysis.md` is the reading guide for both.

### Security tickets

A ticket that mentions a security incident, malware or a virus stops at an **incident gate**: no customer dump or
log is analysed until you confirm the Progress Security team and your manager are engaged. A vulnerability ticket
(CVE, CVSS, scanner output) prints the Progress process checklist first. See
`skills/marklogic-support/references/security-vulnerability-handling.md`.

### KCS articles

`kcs` writes `<ticket>/kcs/kcs-<ticket>-<problem|howto|troubleshoot>-<slug>.{md,docx,html}` — Markdown (canonical),
Word, and Salesforce-paste-ready HTML. Articles follow the company Solution Content Standard
(`KCS_SolutionContentStandard.txt`): 20 fields, title of 55 characters or fewer (70 at most), URL derived from the
title, a short symptom-only summary, standard Cause and Resolution statements. `kcs_render.py` checks these and prints
warnings; Internal Comments and Admin Ticket ID are always left for manual entry in Salesforce. The word "breach" is
rejected.

`kcs-review` reviews an article another engineer wrote (`.md`, `.html` or `.docx`, or pasted text), groups findings
as must-fix, should-fix or optional, and on acceptance writes `kcs-<title-slug>.{md,docx,html}` to `kcs-drafts/` if
that folder exists, otherwise to the working directory. The original is never modified.

## Uninstall

```bash
./install.sh uninstall          # removes only links (or marked copies) that point into this clone
```

Windows: `powershell -ExecutionPolicy Bypass -File .\install.ps1 -Command uninstall`. Then delete the clone.
Uninstall before you move or delete the clone: the installer needs the clone to know which links are its own, and
links left behind point at nothing.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| The agent does not see the skills | Restart it. Run `./install.sh status` and check the folder for your agent (table above). |
| `status` says `stale` | Run `./install.sh update`; the link points at another clone. |
| `status` says `conflict` | A real folder, or a link of your own, with that name exists. Move it away, or re-run with `--force` (a backup is kept). |
| `/ticket 12345` does nothing in pi | pi skills are started as `/skill:ticket 12345`. |
| `/kcs` or `/ticket` still behaves like an old version | An old copy in `~/.claude/commands/` (or the pi/Codex prompt folder) is shadowing the skill: `./install.sh update --clean-legacy`. |
| "pandoc not found" from `kcs` | Install pandoc (https://pandoc.org/installing.html); the Markdown article is already written. |
| `python3` not found (Windows) | Install Python 3; the agent can run the scripts with `python` or `py -3`. |
| Windows: the agent ignores the linked skills | Re-run with `-Copy` (and `-Command update -Copy` after each update). |
| `git pull` fails during `update` | Commit or stash local changes in the clone, or run `update --no-pull`. |

## What's included

```
install.sh  install.ps1          install / update / status / uninstall (macOS+Linux / Windows)
skills/
├── marklogic-support/           triage method, routing table, dump / log / SAR / pstack-perf modes
│   ├── SKILL.md
│   ├── assets/support-scripts/pstack.sh   customer script from KB 000266816 (verbatim)
│   ├── scripts/
│   │   ├── parse_dump.py        splits a support dump into config/status/logs + findings
│   │   ├── analyse_logs.py      ErrorLog/messages/AccessLog/AuditLog -> incident timeline + patterns
│   │   ├── analyse_sar.py       sar -A text -> ranked saturation findings + per-host series
│   │   ├── analyse_pstack.py    pstack movie -> per-snapshot thread classes + allocator/lock findings
│   │   ├── analyse_perf.py      perf report --stdio -> kernel vs user, wrapper time, top symbols
│   │   ├── kcs_render.py        KCS article .md -> .docx and Salesforce .html (pandoc), SCS checks
│   │   └── ticket_init.py       creates / checks a ticket folder and its audit trail
│   └── references/              each domain: Concepts -> Standard procedures -> Common mistakes
│       architecture · cluster-hosts-groups · databases-forests · app-servers · security
│       ha-backup-failover · memory-and-os · monitoring · performance-tuning · dr-scaling
│       app-code-review · client-integration · supportdump-anatomy · log-anatomy
│       sar-analysis · performance-data-requests · pstack-analysis · security-vulnerability-handling
│       ticket-auditing · kcs-writing · sources
├── ticket/SKILL.md              /ticket
├── kcs/SKILL.md                 /kcs
└── kcs-review/SKILL.md          /kcs-review
tests/    unit tests for the scripts, installer and documentation wiring (unittest, stdlib only)
tools/    check-ref.sh — validates the fixed reference-file shape
```

## Verifying and maintaining

Every mistake row in `references/*.md` cites a real doc URL, an `Inside MarkLogic Server` PDF page, or is marked
`[unverified — confirm]` — never silently fabricated. Before adding or editing a row: fetch the source, confirm it
supports the exact claim, then run

```bash
tools/check-ref.sh skills/marklogic-support/references/<file>.md
python3 -m unittest discover -s tests
```

## Licence

MIT — see the LICENSE file.
