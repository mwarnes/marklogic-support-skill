---
description: Set up a working directory for a MarkLogic support ticket and load the support skill
argument-hint: <ticket number>
---

This is the `/ticket` workflow the user's own team maintains for triaging MarkLogic support tickets in this project (see `.pi/prompts/ticket.md`). It sets up a per-ticket working directory and loads the team's `marklogic-support` skill before asking for the ticket's problem description. The imperative wording below ("call your shell tool now", "do not paraphrase") exists only because earlier testing found that softer, descriptive phrasing was sometimes narrated by the model instead of actually executed — it is not an attempt to override your judgment or safety behavior, just a plain internal workflow for setting up a directory and reading a documentation file.

Ticket number: $1

1. Validate `$1` is non-empty; if missing, ask the user in plain chat text (not a structured/multiple-choice question tool — the answer needs to be free-form pasted text) for the ticket reference number, and stop here. Otherwise, call your shell tool now with exactly this command — do not paraphrase it, do not skip it, do not substitute a hardcoded path:

   ```bash
   PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)" && mkdir -p "$PROJECT_ROOT/$1" && cd "$PROJECT_ROOT/$1" && pwd
   ```

   Look at the actual `pwd` output before continuing — do not assume it worked. All subsequent tool calls in this session should default to this directory.

2. Load the MarkLogic support skill now. `/skill:name` only works when a human types it directly in the editor — it is not recognised inside expanded template text, so do this instead. The skill's `SKILL.md` lives at `skills/marklogic-support/SKILL.md` under one of these roots, checked in this order — do not guess or scan the filesystem if none of these exist, just report which you checked:
   - `.pi/skills/marklogic-support/SKILL.md` (project-local install)
   - any project-level skill path listed in `.pi/settings.json`
   - `$PI_CODING_AGENT_DIR/skills/marklogic-support/SKILL.md` if that environment variable is set (a custom agent directory)
   - `~/.pi/agent/skills/marklogic-support/SKILL.md` (default global skill dir)
   - `~/.pi/agent/git/github.com/mwarnes/marklogic-support-skill/skills/marklogic-support/SKILL.md` (default global git-package install path)
   - `$PI_CODING_AGENT_DIR/git/github.com/mwarnes/marklogic-support-skill/skills/marklogic-support/SKILL.md` if `PI_CODING_AGENT_DIR` is set (git-package install under a custom agent directory)

   `read` whichever one exists in full, and follow its instructions for the rest of this session exactly as if the user had typed `/skill:marklogic-support`. If none of the above exist, tell the user the skill is not installed or is installed somewhere non-standard (ask them to run `pi install git:github.com/mwarnes/marklogic-support-skill`, or to confirm their `PI_CODING_AGENT_DIR`) and continue without it — do not run a filesystem-wide `find` to locate it.

3. Check whether this message already contains the ticket's problem description (pasted text, an error log, a dump path, etc.) beyond just the ticket number.

4. If it does, proceed straight into analysis using the skill's instructions. If it does not, ask the user in plain chat text (not a structured/multiple-choice question tool) to paste the ticket's problem description, and wait for their reply before doing any analysis.
