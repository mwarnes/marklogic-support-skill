# `/kcs` — compliant KCS article generation

## Goal
When a ticket is complete, `/kcs [ticket]` drafts a KCS article from the ticket's audit trail and
emits it as Markdown (canonical), Word (.docx) and Salesforce-ready HTML.

## Components
1. `prompts/kcs.md` — the `/kcs [ticket]` template (same pattern as `prompts/ticket.md`).
2. `skills/marklogic-support/references/kcs-writing.md` — article spec derived from `kcs-drafts/`:
   the 18 fields in order (Title, URL Name, Validation Status, Summary, Article Number,
   Environment, Question/Problem Description, Steps to Reproduce, Clarifying Information, Error
   Message, Defect Number, Enhancement Number, Cause, Resolution, Workaround, Notes, Keyword
   Phrase, Admin Ticket ID), per-field rules, Problem/Solution vs How-To framing (How-To uses
   `N/A — ...` in non-applicable fields), conventions (`Unverified`, "(assigned by Salesforce on
   save)", Related articles under Notes, lowercase-hyphen URL Name).
3. `skills/marklogic-support/scripts/kcs_render.py <article.md>` — pandoc → `.docx`; pandoc → `.html`
   with Salesforce inline styles (Verdana 14px body/headings, `#dde1e5` code, bordered `pre`).
   Clear error if pandoc is missing.
4. Pointers in `SKILL.md` and `README.md`; `/kcs` added to `package.json` prompts (already a dir).

## Gating
Ticket = `$1` if given, else the ticket opened by `/ticket` earlier in this session. Neither →
stop and ask. `$1` given → `<project-root>/$1/audit-trail/` must exist, else stop.

## Flow
1. Read audit-trail files as source.
2. Root-Cause.md empty → warn article is premature; ask whether to continue.
3. Pick Problem/Solution or How-To; ask only if ambiguous.
4. Draft `<TICKET>/kcs/kcs-<ticket>-<type>-<slug>.md`; show user. Anything not verified per the
   audit trail is not stated as verified.
5. On approval run renderer → `.docx`, `.html` beside the `.md`.
6. Append a Timeline.md line and an `[Closure]` Analysis.md entry (append-only rules).

## Safeguards
Articles are customer-visible: sanitise customer names, hostnames, IPs, credentials, ticket
specifics (use `example.com` placeholders). Ticket number only in Admin Ticket ID.

## Testing
pytest for the renderer on a fixture `.md`: HTML has the 18 headings and inline styles, docx is a
valid zip with expected headings; skipped if pandoc absent. Also render one existing draft's
pandoc-derived MD and compare headings.
