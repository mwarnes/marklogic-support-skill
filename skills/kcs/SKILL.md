---
name: kcs
description: Write a compliant KCS article (Markdown, Word, Salesforce HTML) from a completed MarkLogic support ticket. Use when the user runs /kcs or asks for a KCS article for a finished ticket.
argument-hint: [ticket number]
---

This is the `/kcs` workflow the user's own team maintains for turning a finished MarkLogic support ticket into a Knowledge-Centered Support article that follows the company Solution Content Standard (see the `ticket` skill, which creates the ticket folder and its `audit-trail/`). It reads the ticket's audit trail, drafts an article in the team's fixed 20-field format, and renders it to Markdown, Word and Salesforce HTML. Imperative wording below is only there so steps are executed rather than narrated.

Ticket argument: $ARGUMENTS

(If the line above still shows the literal text `$ARGUMENTS`, or nothing, take the ticket number from the user's message — for example `/skill:kcs 12345` or "write the KCS article for ticket 12345" — and if there is none, the ticket opened by the `ticket` skill earlier in this session.)

1. **Resolve the ticket.**
   - If there is a ticket number (from the argument, the user's message, or the `ticket` skill earlier in this same session), that is the ticket. **Locate the `marklogic-support` skill directory** (it holds `SKILL.md`, `references/` and `scripts/`; call it `<skill-dir>`). Check, in this order, and use the first that exists: `~/.agents/skills/marklogic-support`, `~/.claude/skills/marklogic-support`, `~/.copilot/skills/marklogic-support`, then in the project (the current directory and its parents up to the repository root) `.agents/skills/marklogic-support`, `.claude/skills/marklogic-support`, `.github/skills/marklogic-support`, then `skills/marklogic-support` if this repository is checked out. Do not search the filesystem. If none exists (or a symlink is broken), tell the user the skill is not installed and that the repository README explains how to install it, then stop. Then run `python3 <skill-dir>/scripts/ticket_init.py --check "<ticket>"` (on Windows use `python` or `py -3` if `python3` is unavailable). If it reports the ticket was not found, tell the user ticket `<ticket>` was not found under the project root and stop — do not create it (that is the `ticket` skill's job).
   - If there is no ticket number, ask the user in plain chat text for an existing ticket number, and stop.
   - Work from the ticket directory the script printed from here on.

2. **Load the skill material.** Read `<skill-dir>/references/kcs-writing.md` (`<skill-dir>` was located in step 1). Then read all five files in `<TICKET>/audit-trail/`: `Timeline.md`, `Analysis.md`, `Required-Diagnostics.md`, `Problems.md`, `Root-Cause.md`.

3. **Check the ticket is article-worthy and safe to publish.**
   - If `Root-Cause.md` has no entries beyond its title line, warn the user the cause is not confirmed and a KCS article would be premature; ask (plain chat) whether to continue anyway, and stop unless they say yes. Articles written this way use the standard Cause statement for an unknown cause (`kcs-writing.md`, "Standard statements"), say plainly which parts are unconfirmed, and use `Validation Status: Unverified`.
   - **Alert guard.** If the ticket describes a product-wide issue, a release announcement or a serious defect affecting most customers, tell the user that Product and Critical Alerts follow a separate approval process and stop.
   - **Security guard.** Read `references/security-vulnerability-handling.md` ("Detect", "KCS articles"). If the audit trail shows a security incident gate was raised (`Timeline.md` "Security incident gate raised") and not cleared, tell the user the incident gate is still open and stop. If the ticket involves a security vulnerability or CVE (`CVE-`, CVSS, "vulnerability", an exploit report, security-scanner output), tell the user the article may only be published to the `Internal App` channel unless Product Management or the product's Security team directs otherwise after they have synchronised with them; the Title will carry the `INTERNAL` prefix and Area of Interest will be `Security`. Never write the word "breach"; describe the event neutrally.

4. **Choose the type and the audience.** Problem/Solution, How-To or How to troubleshoot, per `kcs-writing.md`. Decide from the evidence; ask the user one plain-chat question only if genuinely ambiguous. Unless the security guard already forced it, ask once whether the article is for internal use only (default no); if yes, the Title gets the `INTERNAL` prefix.

5. **Ask the four Environment values.** The company standard Environment section is exactly four lines (Product, Version, OS, Component). Ask them as four questions — with the structured/multiple-choice question tool if your harness has one (the automatic "Other" entry is option 3), otherwise as numbered plain-chat options with "3. Something else (type it)". Derive option 2 from the audit trail and ticket folder; if nothing supports a derived value, drop option 2 rather than guess.

   | Item | Option 1 (default) | Option 2 (derived from the ticket) | Option 3 |
   | --- | --- | --- | --- |
   | Product | `MarkLogic` | `Semaphore` | Something else — user types the product |
   | Version | `All supported versions` | the version(s) in the ticket, e.g. `12.1.0` | Something else |
   | OS | `All supported platforms` | `Linux` or `Windows`, as the ticket shows | Something else |
   | Component | `Server` | the affected area, e.g. `Administration`, `Security` | Something else |

   Use the answers verbatim in the Environment section (format in `kcs-writing.md`); for a defect article list only the versions and operating systems where the defect is present. Put the free-form environment detail under Clarifying Information as an **Environment details** paragraph.

6. **Defects and enhancements.** Search the audit trail for `MLE-<number>` ids. Confirm with the user (plain chat) each id found, or — if none is found — ask once whether a defect or enhancement was filed for this issue and for its `MLE-<number>`. For each defect ask its state: fixed in a shipped release (which), fix targeted for an unreleased release (which, and the calendar quarter), open with or without a workaround, or closed with no plans to fix / unable to reproduce. Use the matching standard Resolution statement from `kcs-writing.md`. Never write hotfix numbers into the article. A defect closed as "not a bug" or "rejected" is not listed as `Defects` in Area of Interest (derive the category from the topic instead); its id goes in Internal Comments, entered by the engineer.

7. **Derive Validation Status and Area of Interest.** Do not ask the user; propose them in the draft. Validation Status follows "Validation Status" in `kcs-writing.md` and the draft must name the evidence for `Verified`. Area of Interest follows "Article Category" (one of the eight values, or empty when in doubt). A security vulnerability or CVE article is always `Security`, even when a defect was filed.

8. **Draft** `<TICKET>/kcs/kcs-<TICKET>-<type>-<slug>.md` where `<type>` is `problem`, `howto` or `troubleshoot` (create `kcs/` if needed) following `kcs-writing.md` exactly: all 20 `## ` headings in order; Title of 55 characters or fewer (70 at most); URL Name derived from the Title; a Summary of the symptom or question only; Internal Comments and Admin Ticket ID as their placeholders; no customer names, hosts, IPs, IDs or secrets; the ticket number nowhere in the article. Take facts only from the audit trail and files in the ticket folder; do not invent versions, steps or test results. Show the full draft to the user, with the proposed Validation Status and Area of Interest called out, and list anything you could not source. Wait for their approval or edits; apply edits and re-show if they ask.

9. **Render** once approved: `python3 <skill-dir>/scripts/kcs_render.py <TICKET>/kcs/<file>.md`. Treat each `SCS content errors` line as a defect in the draft: fix the Markdown, tell the user what changed, and re-run. Show the user any `warning:` lines (title/summary over target, pronouns) and fix them unless they ask to keep them. If it reports pandoc missing, tell the user the `.md` is finished and how to install pandoc; do not hand-write the other formats. Confirm all three files exist with `ls`.

10. **Record it** per `references/ticket-auditing.md`: append a `Timeline.md` line ("KCS article drafted: <title>, <folder>"). Do not write an `[Closure]` entry in `Analysis.md` unless the user has confirmed the ticket is closed. Finish by listing the three file paths, then remind the user of the manual steps in Salesforce: fill Admin Ticket ID and Internal Comments (hotfix numbers for a fixed defect, forum or source links, defects closed as "not a bug"), set Area of Interest if it was left empty, convert each listed MarkLogic article title to a Smart Link, add any attachment or image, and check the Channels setting (`Internal App` only for an `INTERNAL` article).
