---
description: Set up a working directory for a MarkLogic support ticket and load the support skill
argument-hint: <ticket number>
---

Ticket number: $1

1. Validate `$1` is non-empty; if missing, ask the user for the ticket reference number and stop here. Otherwise, call your shell tool now with exactly this command — do not paraphrase it, do not skip it, do not substitute a hardcoded path:

   ```bash
   PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)" && mkdir -p "$PROJECT_ROOT/$1" && cd "$PROJECT_ROOT/$1" && pwd
   ```

   Look at the actual `pwd` output before continuing — do not assume it worked. All subsequent tool calls in this session should default to this directory.

2. Load the MarkLogic support skill now. `/skill:name` only works when a human types it directly in the editor — it is not recognised inside expanded template text, so do this instead: locate the `marklogic-support` skill's `SKILL.md` (check, in order: `.pi/skills/marklogic-support/SKILL.md` in this project, any project-level skill path from `.pi/settings.json`, and the global install under `~/.pi/agent/git/github.com/mwarnes/marklogic-support-skill/skills/marklogic-support/SKILL.md` or `~/.pi/agent/skills/marklogic-support/SKILL.md`), `read` it in full, and follow its instructions for the rest of this session exactly as if the user had typed `/skill:marklogic-support`. If you cannot find it anywhere, tell the user the skill is not installed (`pi install git:github.com/mwarnes/marklogic-support-skill`) and continue without it.

3. Check whether this message already contains the ticket's problem description (pasted text, an error log, a dump path, etc.) beyond just the ticket number.

4. If it does, proceed straight into analysis using the skill's instructions. If it does not, ask the user to paste the ticket's problem description and wait for their reply before doing any analysis.
