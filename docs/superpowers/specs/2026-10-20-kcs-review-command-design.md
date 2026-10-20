# `/kcs-review` — review a KCS article written by another engineer

## Goal
`/kcs-review` reviews a KCS article that another engineer sent for review (HTML, Word or Markdown,
or pasted text), summarises recommendations, and on acceptance writes the revised article as
Markdown, Word (.docx) and Salesforce HTML.

## Components
1. `prompts/kcs-review.md` — the command template (same pattern as `prompts/kcs.md`).
2. `skills/marklogic-support/references/kcs-writing.md` — new "Reviewing an article" section: the
   review checklist and severity definitions.
3. `skills/marklogic-support/scripts/kcs_render.py` — two additions, both pytest-covered:
   - import mode: convert `.html` / `.docx` to Markdown via pandoc (`.md` passes through).
   - title-to-slug helper used to derive the output filename from the Title field.
4. `README.md` — pointer to the new command.

## Input
Prompt for either a file path (`.md`, `.html`, `.docx`) or pasted article text (treated as
Markdown). HTML/docx are converted to Markdown with pandoc first. If pandoc is missing and the
input needs it, say so and stop; `.md` and pasted input do not need pandoc until rendering.
A missing or unsupported file → clear message, ask again.

## Review
Check against `kcs-writing.md`:
- all 18 `## ` fields present, in order; imported articles whose headings don't match are mapped
  where unambiguous, otherwise flagged;
- four-line Environment section (Product, Version, OS, Component);
- sanitisation: customer names, hostnames, IPs, credentials, ticket specifics (ticket number only
  under Admin Ticket ID);
- field rules, Problem/Solution vs How-To framing, `Unverified` convention, URL Name format,
  Keyword Phrase;
- internal consistency and technical accuracy against the skill's reference files. Claims that
  cannot be verified are flagged, not silently corrected.

Findings are grouped **must-fix / should-fix / optional**.

## Decision (all-or-nothing)
Show a summary of the recommendations and ask whether to accept.
- **Accept** → apply every recommendation, show the full revised article, get final confirmation.
- **Decline** → ask which parts need correction or improvement, revise, re-summarise, ask again.

## Output
- Filename derived from the article's Title field: `kcs-<slug>.{md,docx,html}`.
- Directory: `./kcs-drafts/` if it exists in the current working directory, otherwise the current
  project folder.
- The original is never modified. If a target filename exists, add a numeric suffix.
- Rendering via `kcs_render.py`, so `.docx` and Salesforce `.html` match `/kcs` output. If pandoc
  is missing at this stage the `.md` is still written and the user is told how to install it.
- Finish by listing the three file paths.

## Out of scope
No ticket audit-trail entries (the article has no ticket here); no review-notes file unless the
user asks for one in chat; no per-item accept/reject.

## Testing
pytest: HTML/docx → Markdown import round-trips the 18 headings on the existing fixture
(skipped if pandoc absent); slug helper cases (punctuation, case, length); collision suffixing;
output-directory selection (`kcs-drafts/` present vs absent).
