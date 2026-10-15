---
description: Write a compliant KCS article (Markdown, Word, Salesforce HTML) from a completed MarkLogic support ticket
argument-hint: [ticket number]
---

This is the `/kcs` workflow the user's own team maintains for turning a finished MarkLogic support ticket into a Knowledge-Centered Support article (see `/ticket` in `prompts/ticket.md`, which creates the ticket folder and its `audit-trail/`). It reads the ticket's audit trail, drafts an article in the team's fixed 18-field format, and renders it to Markdown, Word and Salesforce HTML. Imperative wording below is only there so steps are executed rather than narrated.

Ticket argument: $1

1. **Resolve the ticket.**
   - If `$1` is non-empty, the ticket is `$1`. Run (shell tool) `PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"; ls "$PROJECT_ROOT/$1/audit-trail/"`. If the directory does not exist, tell the user ticket `$1` was not found under the project root and stop — do not create it (that is `/ticket`'s job).
   - If `$1` is empty, use the ticket opened by `/ticket` earlier in this same session. If `/ticket` was not run in this session, ask the user in plain chat text for an existing ticket number, and stop.
   - Work from `<PROJECT_ROOT>/<TICKET>/` from here on.

2. **Load the skill material.** Read `skills/marklogic-support/references/kcs-writing.md` (locate the skill by checking the same paths as `/ticket` step 2 — pi and Claude Code locations, `~/.claude/skills/marklogic-support/` included; if none exists or the symlink is broken, say so and stop). Then read all five files in `<TICKET>/audit-trail/`: `Timeline.md`, `Analysis.md`, `Required-Diagnostics.md`, `Problems.md`, `Root-Cause.md`.

3. **Check the ticket is article-worthy.** If `Root-Cause.md` has no entries beyond its title line, warn the user the cause is not confirmed and a KCS article would be premature; ask (plain chat) whether to continue anyway, and stop unless they say yes. Articles written this way must say plainly in Cause which parts are unconfirmed and use `Validation Status: Unverified`.

4. **Choose the type.** Problem/Solution or How-To, per `kcs-writing.md`. Decide from the evidence; ask the user one plain-chat question only if genuinely ambiguous.

5. **Ask the four Environment values.** The company standard Environment section is exactly four lines (Product, Version, OS, Component). Ask them as four questions — with the structured/multiple-choice question tool if your harness has one (the automatic "Other" entry is option 3), otherwise as numbered plain-chat options with "3. Something else (type it)". Derive option 2 from the audit trail and ticket folder; if nothing supports a derived value, drop option 2 rather than guess.

   | Item | Option 1 (default) | Option 2 (derived from the ticket) | Option 3 |
   | --- | --- | --- | --- |
   | Product | `MarkLogic` | `Semaphore` | Something else — user types the product |
   | Version | `All supported versions` | the version(s) in the ticket, e.g. `12.1.0` | Something else |
   | OS | `All supported platforms` | `Linux` or `Windows`, as the ticket shows | Something else |
   | Component | `Server` | the affected area, e.g. `Administration`, `Security` | Something else |

   Use the answers verbatim in the Environment section (format in `kcs-writing.md`). Put the free-form environment detail that used to live there (exact versions verified, required configuration, IdP/product versions) under Clarifying Information as an **Environment details** paragraph.

6. **Draft** `<TICKET>/kcs/kcs-<TICKET>-<type>-<slug>.md` (create `kcs/` if needed) following `kcs-writing.md` exactly: all 18 `## ` headings in order, sanitised (no customer names, hosts, IPs, IDs, secrets), ticket number only under Admin Ticket ID. Take facts only from the audit trail and files in the ticket folder; do not invent versions, steps or test results. Show the full draft to the user and list anything you could not source. Wait for their approval or edits; apply edits and re-show if they ask.

7. **Render** once approved: `python3 <skill-dir>/scripts/kcs_render.py <TICKET>/kcs/<file>.md`. If it reports pandoc missing, tell the user the `.md` is finished and how to install pandoc; do not hand-write the other formats. Confirm all three files exist with `ls`.

8. **Record it** per `references/ticket-auditing.md`: append a `Timeline.md` line ("KCS article drafted: <title>, <folder>"). Do not write an `[Closure]` entry in `Analysis.md` unless the user has confirmed the ticket is closed. Finish by listing the three file paths.
