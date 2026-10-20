# Writing a compliant KCS article

Written to the company Solution Content Standard (SCS, `KCS_SolutionContentStandard.txt` in the
repo root — the generic and MarkLogic parts only). One article per resolved problem or reusable
procedure. The Markdown file is canonical; `scripts/kcs_render.py` checks it and produces the `.docx`
and Salesforce `.html`. Source material is the ticket's `audit-trail/`.

## File layout and naming

```
<TICKET>/kcs/kcs-<TICKET>-<type>-<short-slug>.md      type = problem | howto | troubleshoot
                                                .docx
                                                .html
```

Start the `.md` with the banner comment (the renderer reuses it in the HTML):

```
<!--
KCS ARTICLE — Problem/Solution     (or: How-To (framed as Problem/Solution per template constraints),
                                    or: How to troubleshoot)
Paste each section below into the matching Salesforce field.
-->
```

Without a banner, `kcs_render.py` infers the type from `-problem-` / `-howto-` / `-troubleshoot-` in the filename.

## Article type

- **Problem/Solution** (SCS "Diagnostic") — a symptom, error or unexpected behaviour with a cause
  and fix or workaround. Title states product + symptom/error.
- **How-To** — a goal, defined by a question that is not a problem. Title starts "How to ...". Uses all
  20 fields: Question/Problem Description is the question, Steps to Reproduce is
  `N/A — this article is a configuration procedure, not a defect.`, Cause/Error/Defect/Enhancement
  fields `N/A` where they do not apply.
- **How to troubleshoot** ("umbrella" article) — an error with several causes or contexts. Title
  starts "How to troubleshoot ...". Question/Problem Description names the error and the contexts it
  occurs in; Cause lists the possible causes; Resolution walks the reader through the checks that
  identify their situation, then the fix for each cause.
- **Alerts are out of scope.** A Product Alert (product-wide issue, release announcement) or Critical
  Alert (serious defect affecting most customers) needs Product Management/Legal approval and a
  separate process. `/kcs` stops and tells the engineer so.
- **Security vulnerability content.** Anything that describes a security defect, a product
  vulnerability or a CVE (see `security-vulnerability-handling.md`) is published to the `Internal App`
  channel only, unless Product Management or the product's Security team directs otherwise after the
  engineer has synchronised with them. A TSE may create it, edit it after consulting the original
  author or a security subject-matter expert, and publish it internally; a TSE may not publish it
  externally alone. Write the article, prefix the Title with `INTERNAL`, set Area of Interest to `Security`, and warn the
  engineer not to publish externally.

## Title prefix

`INTERNAL ` (one word, then a space) marks an article intended for an internal-only audience, a beta
release, sensitive information or security/CVE content. It is not counted in the title length and is
never part of the URL Name. There is no `INCOMPLETE` / stub article for MarkLogic.

## The 20 fields — exact `## ` headings, in this order, none omitted

| # | Heading | Rule |
| --- | --- | --- |
| 1 | Title | One line, key words first, **55 characters or fewer, 70 at most** (not counting `INTERNAL `). Product + symptom (Problem) or "How to ..." (How-To). Trim error text to its key phrase; the whole message goes in Error Message. |
| 2 | URL Name | The Title (without `INTERNAL `) lowercased, every run of characters other than a–z and 0–9 replaced by one hyphen. No truncation, no ticket number. |
| 3 | Summary | The symptom or question only, key words first, **160 characters or fewer** (renderer errors above 250). Never the cause or resolution. Add detail that does not fit the title and tells similar articles apart. |
| 4 | Validation Status | `Verified` or `Unverified`, per "Validation Status" below. |
| 5 | Article Number | `*(assigned by Salesforce on save)*` |
| 6 | Environment | Company standard, exactly four lines and nothing else — see "Environment format". |
| 7 | Question/Problem Description | Diagnostic: the problem. How-To: the question. Complete thoughts, the user's context restated in technical wording (key words, not a verbatim customer paste). Include relevant log or stack-trace frames only, no customer specifics, and the error message with the trace. Lead in with `Log excerpt from <file> reads:` or `Full stack trace from <process> on <OS> reads:`. |
| 8 | Steps to Reproduce | Numbered, minimal, runnable. **Required** when the issue is easily reproduced, needs no customer code and is not too complex. Otherwise `N/A — <which condition fails>`. How-To: `N/A — ...`. |
| 9 | Clarifying Information | An **Environment details** paragraph first (versions verified, required configuration, third-party product versions), then facts that stay true after the fix: conditions under which the problem does not occur, what it is easily mistaken for and how to tell them apart. When the article cites a defect, also put the "Verified on ..." sentence here (not in Resolution). |
| 10 | Error Message | Verbatim, in a fenced block, stating where it appears. Strip customer-specific names (products, files, hosts). `N/A` if none. |
| 11 | Defect Number | `N/A`, or comma-separated `MLE-<number>`. Include defects closed as "no plans to fix". |
| 12 | Enhancement Number | `N/A`, or comma-separated `MLE-<number>`. |
| 13 | Cause | Confirmed root cause in customer-consumable language, mechanism not just symptom. Use the standard statements below when the cause is unknown or the behaviour is by design. How-To: `N/A`. |
| 14 | Resolution | Numbered steps or bullets with the commands, how to confirm success and how to undo any diagnostics. Defects: the standard statements below. Link a resource that is needed to complete the step in the text; put background reading in Notes. |
| 15 | Workaround | Interim option, or `None. <why>` / `N/A — <fix is the resolution>`. |
| 16 | Notes | Anything that fits no other field, then the reference blocks below. Do not repeat a link already given in another field. |
| 17 | Internal Comments | **Manual entry only.** Always `*(manual entry)*`. |
| 18 | Article Category | Two lines — see "Article Category". |
| 19 | Keyword Phrase | One line of search terms: product, error codes, setting names, key nouns, vendor names. |
| 20 | Admin Ticket ID | **Always** `*(fill in if applicable)*`. The ticket number never appears in the article. |

### Notes layout

```
<free text>

References to Other Documentation:

<Book or page title, section>
<https URL on its own line>

MarkLogic article(s):
- <article title — the engineer converts each to a Smart Link>
```

Omit the "References to Other Documentation" block when there are no document links. Every hyperlink
shows its URL in the displayed text. Link the latest documentation version unless the article is
about a specific version.

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
area (e.g. `Administration`, `Security`). An article about a defect lists only the versions and
operating systems where the defect is present — never "All supported versions". Free-form
environment detail goes in Clarifying Information, never here.

## Validation Status

`/kcs` proposes one value, names the evidence, and the engineer confirms in the draft review.

- **Verified** only when the audit trail shows at least one of: the customer confirmed the solution
  worked; Support reproduced the problem and the solution; the information is in the product
  documentation; Development confirmed how the product works or was designed (not a suggestion for
  one customer); a defect or enhancement was filed (what is verified is that it was filed).
- **Unverified** otherwise — the solution is believed to work but none of the above is on record.

Never claim more than the audit trail shows. `In research` is not used.

## Article Category

```
Product Group: MarkLogic\
Area of Interest: Security
```

Product Group is always `MarkLogic`. Area of Interest is one of `Admin/Config`, `Defects`,
`Enhancement`, `Installation`, `Licensing`, `Performance`, `Programming`, `Security`, derived from the
article and ticket: a security vulnerability or CVE article → `Security` (always `Security`, even when a defect is filed); a filed defect → `Defects`; a filed enhancement → `Enhancement`; otherwise the
dominant topic (install/upgrade → `Installation`; licence keys → `Licensing`; slowness, memory,
throughput → `Performance`; authentication, SAML/OAuth, certificates, roles → `Security`; XQuery,
JavaScript, REST/Java/Node client code → `Programming`; configuration and administration →
`Admin/Config`). A defect closed as "not a bug" or "rejected" is not `Defects`: derive the category from the topic
instead (its id goes in Internal Comments, entered by the engineer). Area of Interest is mandatory in
Salesforce, so when in doubt leave the value empty (`Area of Interest:` — the renderer accepts an empty
value) and the engineer sets it in Salesforce.

## Standard statements

Use these wordings exactly (fill the `<...>` parts).

**Cause**

- Unknown: `The exact cause is not known at this time.`
- By design: `This is expected behavior.` followed by one concise sentence saying why.
- Unsupported platform: `The exact cause is not known at this time.` then
  `The behavior described in this article has not been tested or verified by MarkLogic Support. At the time of writing (<Month Year>), <OS or version> is not a supported platform for MarkLogic Server and is therefore not supported.`

**Resolution when a defect is referenced** (state the defect id in Defect Number, not here; hotfix
numbers are never written in the article — the engineer records them in Internal Comments)

- Filed, no fix, no workaround: `None at this time.`
- Filed, no fix, workaround exists: `Until the fix is available, use the workaround below.`
- Fixed in a release: `Fixed in MarkLogic <release>.`
- Fix in a release not yet shipped (only when the defect is neither Scheduled nor in Active Dev for it):
  `The fix for this issue is targeted for an upcoming release <X.Y>.` then
  `As of <today's date>, release <X.Y> is targeted to be released in <Qn CYyyyy>, although dates and content of the release are subject to change.`
  Use calendar quarters and years, never fiscal ones, and no specific day.
- Closed with no plans to fix or unable to reproduce: `The defect was closed as the information provided was not sufficient to reproduce the scenario in-house or the provided workaround was adequately viable.` then
  `If the defect is affecting a current version and the workaround is not viable, please open a new support case with steps to reproduce the issue.`

**Resolution when an enhancement is referenced:** state the enhancement id (in Enhancement Number) and,
if implemented, the release it was implemented in. There is no template text.

## Style rules

- Present tense, short sentences, one idea per sentence, no unnecessary words.
- Impersonal: no "you", "we", "our", no customer narrative, no timeline. Instead of "You should perform a
  backup prior to converting your database" write "Perform a database backup prior to converting the
  database." (The renderer warns on pronouns outside code.)
- Give the command being used when the issue occurs or needed to resolve it.
- Refer to the product documentation for additional information where it applies.
- One complete answer to one problem or goal.
- Never write the word "breach" (breach, breached, breaches, breaching) in an article: Legal must
  approve any such language. Describe the event neutrally (for example "unauthorized access" or
  "security incident"). The renderer rejects it.
- Setting/field/command/error names in backticks; UI labels in **bold**; UI paths with `→`; bold for
  emphasis. Code and commands in fenced blocks, one per step, with `example.com` hosts; say what to
  substitute.
- Tables are fine in the `.md`/`.docx`; the renderer turns them into bullet lists in the Salesforce `.html`
  (first column bold, then ` – `, then the other columns, labelled with their headers when there are 3+
  columns). Keep table cells short.
- Admin Interface route first, Management API (curl) alternative where one exists; note when an API call
  *replaces* rather than merges.
- State scope honestly: versions verified, "not verified on earlier releases". Hypotheses stay out of Cause.
- Images, attachments and video are added by hand in Salesforce; the skill does not produce them. An image
  must be readable at 500 px wide, cropped to what matters, and have a short description (alt text).
  Attachments must contain no customer data and the article must describe them. Video articles are out
  of scope.

## Sanitise (articles are customer-visible)

Remove or replace: customer/company names, real hostnames and domains (`example.com`), IPs, usernames,
tenant/app/client IDs, secrets/keys/tokens, file paths revealing the customer, support dump contents,
ticket-specific dates. Keep error codes, setting names and generic log lines. **The ticket number does
not appear anywhere in the article.** When unsure whether something identifies the customer, replace it.

## Quality gate before rendering

All 20 headings present once in order; no `TBD`/placeholders; every command runnable as written; Cause
is confirmed (or uses a standard statement); sanitised; Title, Summary and Keyword Phrase match what a
customer would search for; Summary holds no cause or resolution; Internal Comments and Admin Ticket ID are
placeholders; `kcs_render.py` reports no errors and no unexplained warnings.

## Reviewing an article (used by `/kcs-review`)

Review an article written by someone else against everything above, then group findings:

- **must-fix** — breaks the standard or leaks data: missing/misordered/extra headings (except the known 18-field format, below); Environment not
  exactly the four standard lines; unsanitised customer data (names, hosts, IPs, IDs, secrets) or the
  ticket number anywhere; URL Name not derived from the Title; cause or resolution in Summary; Article
  Category missing or with an invalid value; Defect/Enhancement Number not `MLE-<number>`/`N/A`; Internal
  Comments or Admin Ticket ID filled in; hotfix numbers in the article; wrong or missing standard
  statement for an unknown cause or a defect; unconfirmed Cause stated as fact; security/CVE content
  without the `INTERNAL` prefix or without Area of Interest `Security`; the word "breach" in any form; alert-type content; commands that cannot run as written; claims
  contradicted by the skill's reference files.
- **should-fix** — hurts findability, clarity or style: Title over 70 characters (the renderer will not
  render it); Summary over 160 characters (over 250 is likewise not rendered); personal pronouns or
  past/future tense; verbatim customer text in Question/Problem Description; reproducible problem with
  no Steps to Reproduce; `Validation Status` stronger than the evidence (or `Unverified` when the audit
  trail shows a Verified condition); link text without its URL; Notes not in the SCS layout; missing or
  incorrect type banner comment (`<!-- KCS ARTICLE — <type> ... -->`; html/docx imports always lose it);
  weak Keyword Phrase; wrong Problem/Solution vs How-To vs troubleshoot framing; scope/versions not
  stated honestly; missing "substitute these values" notes; no Management API alternative where one
  exists; "Verified on ..." sentence in Resolution of a defect article.
- **optional** — Title of 56–70 characters; wording, bold/backtick conventions, table cell length, step order.

Checks that cannot be settled from the article and the references (a version number, a behaviour
claim, whether a defect exists) are reported as "could not verify" — never silently changed. An imported
article whose headings differ from the 20 fields is mapped only where the match is unambiguous (e.g.
`Problem` → `Question/Problem Description`); otherwise the field is reported missing. An article in the
earlier 18-field format (no Internal Comments or Article Category, Summary after Validation Status) is a
**should-fix**, not a must-fix: add the Internal Comments (`*(manual entry)*`) and Article Category
(derived) placeholders, move Summary above Validation Status, and report that you did.
