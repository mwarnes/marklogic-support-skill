---
name: ticket
description: Set up a working directory and audit trail for a MarkLogic support ticket and load the marklogic-support skill. Use when the user runs /ticket <number> or asks to start work on a support ticket.
argument-hint: <ticket number>
---

This is the `ticket` workflow (`/ticket <number>`) the user's own team maintains for triaging MarkLogic support tickets. It sets up a per-ticket working directory and its persistent audit trail, and loads the team's `marklogic-support` skill before asking for the ticket's problem description. The imperative wording below ("run this command now", "do not paraphrase") exists only because earlier testing found that softer, descriptive phrasing was sometimes narrated by the model instead of executed, or a step was silently skipped — it is a plain internal workflow for creating a folder and reading documentation files.

Ticket number: $ARGUMENTS

(If the line above is empty or still shows a `$`-placeholder instead of a value, take the ticket number from the user's message — for example `/skill:ticket 12345` or "start ticket 12345".)

1. **Locate the `marklogic-support` skill directory** (it holds `SKILL.md`, `references/` and `scripts/`; call it `<skill-dir>`). First look for the `marklogic-support` folder that sits next to this skill's own folder, i.e. `../marklogic-support` relative to the folder this SKILL.md was loaded from (in Claude Code that is `${CLAUDE_SKILL_DIR}/../marklogic-support`); if it exists, use it. Otherwise check, in this order, and use the first that exists: `~/.agents/skills/marklogic-support`, `~/.claude/skills/marklogic-support`, `~/.copilot/skills/marklogic-support`, then in the project (the current directory and its parents up to the repository root) `.agents/skills/marklogic-support`, `.claude/skills/marklogic-support`, `.github/skills/marklogic-support`, then `skills/marklogic-support` if this repository is checked out. Do not search the filesystem. If none exists (or a symlink is broken), tell the user the skill is not installed and that the repository README explains how to install it, then stop. Scripts below are run with `python3`; on Windows use `python` or `py -3` if `python3` is not available.

2. Validate the ticket number is non-empty; if missing, ask the user in plain chat text (not a structured/multiple-choice question tool — the answer needs to be free-form pasted text) for the ticket reference number, and stop here. Otherwise run this single command now, in full, as one call — do not split it, paraphrase it, or substitute a path:

   ```
   python3 "<skill-dir>/scripts/ticket_init.py" "<ticket>"
   ```

   It creates the ticket working directory under the project root (the git top-level directory, else the current directory) and its persistent audit trail (5 files under `audit-trail/` — every ticket gets one, this is not optional), never truncating a file that already has content, and prints the ticket directory followed by the files. Check the output lists all 5 files (`Analysis.md`, `Problems.md`, `Required-Diagnostics.md`, `Root-Cause.md`, `Timeline.md`) — if any are missing or the command fails, say so and stop. See `references/ticket-auditing.md` in the skill for the format each file follows. Then change into the printed ticket directory now with `cd "<ticket directory>"` (use the exact path the script printed) and continue from there: all later commands in this session run there, so the skill's audit-trail updates find `audit-trail/`.

3. Load the MarkLogic support skill now: read `<skill-dir>/SKILL.md` in full and follow its instructions for the rest of this session exactly as if the user had invoked the `marklogic-support` skill directly.

4. Check whether the user's message already contains (a) the ticket's problem description (pasted text, an error log, a dump path, etc.) beyond just the ticket number, and (b) the ticket's severity (1, 2 or 3, or "Sev 1" and similar wording).

5. If it contains the description, proceed into analysis using the skill's instructions (which includes updating the audit trail — see the skill's "Audit trail" section). If it does not, ask the user in plain chat text (not a structured/multiple-choice question tool) to paste it, and wait for the reply before any analysis. If the severity is missing, ask for it in the same message, together with whether it is a production system, whether a workaround is in place and the business impact — "unknown" is an acceptable answer. The severity is needed so the skill can check it against the support guide (`references/support-scope.md`, "Severity check"); engineers cannot change it, but can raise a doubt with the customer's Client Success Manager. In either case, before any analysis, apply the skill's security check (`references/security-vulnerability-handling.md`): a security incident stops at the incident gate; a security vulnerability prints the banner and checklist first.
