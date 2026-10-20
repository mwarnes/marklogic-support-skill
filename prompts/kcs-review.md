---
description: Review a KCS article written by another engineer (md/html/docx or pasted) and write the revised article as Markdown, Word and Salesforce HTML
argument-hint: [path to article]
---

This is the `/kcs-review` workflow the user's own team maintains for reviewing a Knowledge-Centered Support article that another engineer sent for review (see `/kcs` in `prompts/kcs.md`, which writes articles from a ticket). It checks the article against the team's 20-field format, the Solution Content Standard rules in `kcs-writing.md`, and sanitisation rules, summarises recommendations, and on acceptance writes the revised article as Markdown, Word and Salesforce HTML. Imperative wording below is only there so steps are executed rather than narrated.

Article path argument (optional, may contain spaces): $ARGUMENTS

1. **Load the skill material.** Read `skills/marklogic-support/references/kcs-writing.md` (locate the skill by checking the same paths as `/ticket` step 2 — pi and Claude Code locations, `~/.claude/skills/marklogic-support/` included; if none exists or the symlink is broken, say so and stop). Set `<skill-dir>` to the directory that holds it. Use its "Reviewing an article" section as the checklist.

2. **Get the article.**
   - If `$ARGUMENTS` is non-empty, the whole of it is the path (do not split on spaces). Otherwise ask in plain chat text: "Give me the path to the KCS article (.md, .html or .docx), or paste the article text here." Wait for the reply.
   - A path: run (shell tool) `python3 <skill-dir>/scripts/kcs_render.py --to-md "<path>"` and use its stdout as the article Markdown. If it fails (file not found, unsupported type, pandoc missing for html/docx), show the error, and ask again — for pandoc missing, also offer that the user can paste the text instead.
   - Pasted text: treat it as Markdown as-is.
   - Keep the original untouched; all edits are made to your working copy.

3. **Review** the working copy against the checklist: the 20 `## ` headings in order, the four-line Environment section, sanitisation (the ticket number must appear nowhere), the SCS field rules (title and summary length, URL Name derived from the Title, `MLE-<number>` ids, Article Category, manual-only Internal Comments and Admin Ticket ID, standard Cause and Resolution statements, style and links), the security/CVE and alert checks, consistency, and technical accuracy against the skill's reference files, and the type banner: the Markdown must start with the `<!-- KCS ARTICLE — <type> ... -->` comment from `kcs-writing.md` (`Problem/Solution`, `How-To (framed as Problem/Solution per template constraints)`, or `How to troubleshoot`) matching the article's real type. Imports from .html/.docx always lose it, so treat a missing or wrong banner as should-fix. Do not invent facts to fill gaps and do not silently correct anything you cannot verify — report it as "could not verify". An article in the earlier 18-field format gets the two missing fields added (placeholder and a derived Area of Interest) — list that as a should-fix change.

4. **Summarise** the findings in plain chat text, grouped **must-fix**, **should-fix**, **optional**, each with the field it applies to and the proposed change. Then ask: "Accept these recommendations?" (yes / no).

5. **Decide** (all-or-nothing).
   - **Yes:** apply every recommendation to the working copy, show the full revised article, and ask the user to confirm it. Apply edits and re-show if they ask for more.
   - **No:** ask in plain chat text which parts need correction or improvement. Revise accordingly, re-summarise what changed, and go back to the "Accept?" question.

6. **Write** once the user has confirmed the revised article.
   - Take the title from the `## Title` field of the revised article. Run `python3 <skill-dir>/scripts/kcs_render.py --target "<title>"`; its output is the target path without extension (`kcs-drafts/` in the current directory if it exists, otherwise the current directory; existing files get a numeric suffix).
   - The revised Markdown must begin with the banner comment exactly as in `kcs-writing.md` (`<!--`, `KCS ARTICLE — Problem/Solution`, `KCS ARTICLE — How-To (framed as Problem/Solution per template constraints)` or `KCS ARTICLE — How to troubleshoot`, `Paste each section below into the matching Salesforce field.`, `-->`) with the correct article type; re-add it if the import lost it. The renderer reads the type from that line and otherwise guesses from the filename.
   - Write the revised Markdown to `<target>.md` and run `python3 <skill-dir>/scripts/kcs_render.py <target>.md`. If the renderer rejects the article (headings, Environment or an `SCS content errors` line), fix the Markdown, show the user what you changed, and re-run. If pandoc is missing, tell the user the `.md` is finished and how to install pandoc; do not hand-write the other formats. Show the user any `warning:` lines the renderer printed.
   - Confirm with `ls` that the `.md`, `.docx` and `.html` exist, then list the three file paths. Do not modify or delete the original article. Do not write ticket audit-trail entries. Remind the user of the manual Salesforce steps: Admin Ticket ID, Internal Comments, Smart Links for the listed article titles, attachments/images, and Channels.
