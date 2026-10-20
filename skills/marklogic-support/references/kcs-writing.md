# Writing a compliant KCS article

Format learned from the team's published drafts (`kcs-drafts/`). One article per resolved problem
or reusable procedure. The Markdown file is canonical; `scripts/kcs_render.py` produces the
`.docx` and Salesforce `.html` from it. Source material is the ticket's `audit-trail/`.

## File layout and naming

```
<TICKET>/kcs/kcs-<TICKET>-<type>-<short-slug>.md      type = problem | howto
                                             .docx
                                             .html
```

Start the `.md` with the banner comment used in the published drafts (the renderer reuses it in the HTML):

```
<!--
KCS ARTICLE — Problem/Solution            (or: How-To (framed as Problem/Solution per template constraints))
Paste each section below into the matching Salesforce field.
-->
```

Without a banner, `kcs_render.py` infers the type from `-problem-` / `-howto-` in the filename.

## Article type

- **Problem/Solution** — a symptom, error or unexpected behaviour with a confirmed cause and fix.
  Title states the symptom in the customer's words (product + symptom/error).
- **How-To** — a reusable procedure. Title starts "How to ...". Still uses all 18 fields
  ("framed as Problem/Solution per template constraints"): Question/Problem Description is the
  question ("Which values ... and how do I ..."), Steps to Reproduce is
  `N/A — this article is a configuration procedure, not a defect.`, Cause/Error/Defect fields `N/A`
  where they do not apply.

## The 18 fields — exact `## ` headings, in this order, none omitted

| # | Heading | Rule |
| --- | --- | --- |
| 1 | Title | One line. Product + symptom (Problem) or "How to ..." (How-To). Include the error text/code if there is one. |
| 2 | URL Name | Lowercase, hyphenated, ASCII, no ticket number. Starts `marklogic-` for Problem articles. |
| 3 | Validation Status | `Unverified` (a reviewer changes it in Salesforce). |
| 4 | Summary | 2–4 sentences: symptom, then cause/answer. Usable as a search snippet. |
| 5 | Article Number | `*(assigned by Salesforce on save)*` |
| 6 | Environment | Company standard, exactly four lines and nothing else — see "Environment format" below. |
| 7 | Question/Problem Description | What the user sees/asks, in their terms, not the diagnosis. |
| 8 | Steps to Reproduce | Numbered, minimal, runnable. How-To or non-reproducible: `N/A — <why>`. |
| 9 | Clarifying Information | An **Environment details** paragraph first (free-form: versions verified, required configuration, third-party product versions), then what it is easily mistaken for, how to tell them apart, caching/timing gotchas. |
| 10 | Error Message | Verbatim log/HTTP text in an indented/fenced code block, stating where it appears and which trace events produce it. `N/A` if none. |
| 11 | Defect Number | Bug ID or `N/A`. |
| 12 | Enhancement Number | Enhancement ID or `N/A`. |
| 13 | Cause | Confirmed root cause only (from `Root-Cause.md`), mechanism not just symptom. How-To: `N/A`. |
| 14 | Resolution | Numbered steps incl. how to confirm success and how to undo any diagnostics (e.g. disable trace events). End with a "Verified on ..." sentence only if verification is on record. |
| 15 | Workaround | Interim option, or `None. <why>` / `N/A — <fix is the resolution>`. |
| 16 | Notes | Related checks and limits. Finish with `**Related articles:**` bullet list of article *titles*. |
| 17 | Keyword Phrase | One line of search terms: product, error codes, setting names, key nouns, vendor names. |
| 18 | Admin Ticket ID | The ticket number (the only place it appears). Leave `*(fill in if applicable)*` if none. |

## Environment format

The Environment section is the four fields below, one per line (end each line but the last with a
backslash `\` so Markdown keeps the line breaks), with no other text:

```
Product: MarkLogic\
Version: All supported versions\
OS: All supported platforms\
Component: Administration
```

`/kcs` asks the user for each value (option 1 default, option 2 derived from the ticket, option 3
free text): Product `MarkLogic` / `Semaphore`; Version `All supported versions` / the ticket's
version; OS `All supported platforms` / `Linux` or `Windows`; Component `Server` / the affected
area (e.g. `Administration`, `Security`). Free-form environment detail goes in Clarifying
Information, never here.

## Style rules

- Tables are fine in the `.md`/`.docx`; the renderer turns them into bullet lists in the
  Salesforce `.html` (Salesforce article fields do not take tables): first column bold, then
  ` – `, then the other columns (labelled with their headers when there are 3+ columns). Keep
  table cells short so the bullets read well.
- Plain, jargon-light, impersonal. No "we", no customer narrative, no timeline.
- Setting/field/command/error names in backticks; UI labels in **bold**; UI paths with `→`.
- Commands in fenced blocks, one per step, with `example.com` hosts. Say what to substitute.
- Admin Interface route first, Management API (curl) alternative where one exists; note when an
  API call *replaces* rather than merges.
- State scope honestly: versions verified, "not verified on earlier releases".
- Do not claim "verified" beyond what the audit trail shows was tested. Hypotheses stay out of
  Cause (same discipline as `Root-Cause.md`).

## Sanitise (articles are customer-visible)

Remove or replace: customer/company names, real hostnames and domains (`example.com`), IPs,
usernames, tenant/app/client IDs, secrets/keys/tokens, file paths revealing the customer, support
dump contents, and ticket-specific dates. Keep error codes, setting names and generic log lines.
The ticket number appears only in Admin Ticket ID. When unsure whether something identifies the
customer, replace it.

## Quality gate before rendering

All 18 headings present once in order; no `TBD`/placeholders; every command runnable as written;
Cause is confirmed; sanitised; title and keyword phrase would match what a customer would search.

## Reviewing an article (used by `/kcs-review`)

Review an article written by someone else against everything above, then group findings:

- **must-fix** — breaks the format or is unsafe: missing/misordered/extra headings, Environment not
  exactly the four standard lines, unsanitised customer data (names, hosts, IPs, IDs, secrets,
  ticket number outside Admin Ticket ID), unconfirmed Cause stated as fact, commands that cannot
  run as written, claims contradicted by the skill's reference files.
- **should-fix** — hurts findability or clarity: missing or incorrect type banner comment
  (`<!-- KCS ARTICLE — <type> ... -->`; html/docx imports always lose it), weak Title or Keyword Phrase, URL Name not
  lowercase-hyphen, wrong Problem/Solution vs How-To framing (How-To fields should be
  `N/A — ...`), `Validation Status` stronger than the evidence, scope/versions not stated
  honestly, missing "substitute these values" notes, no Management API alternative where one exists.
- **optional** — style: wording, bold/backtick conventions, table cell length, ordering of steps.

Checks that cannot be settled from the article and the references (a version number, a behaviour
claim) are reported as "could not verify" — never silently changed. An imported article whose
headings differ from the 18 fields is mapped only where the match is unambiguous (e.g. `Problem`
→ `Question/Problem Description`); otherwise the field is reported missing.
