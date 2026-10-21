# Scope of support and severity (reference only)

## Rules for using it

Maintainer's policy for this skill:

- The Scope of Support page and the full Support Guide are reference only.
- Engineers have leeway to assist beyond the scope of a support ticket to help a customer.
- The skill must HIGHLIGHT to the engineer when a ticket is going far beyond the scope of a support ticket. The skill highlights; the engineer decides.
- Give a link only if needed. Never quote the pages at length; paraphrase the part that applies.

## Links

- Scope of Support: https://community.progress.com/s/products/marklogic/scope-of-support
- Support Guide: https://community.progress.com/s/products/marklogic/support-guide
- SLA & Severity Definitions (sub-page of the support guide; text supplied by the maintainer 2026-10-21, paraphrased below).

## Severity, priority and business impact

Three different things; do not mix them up when asking a customer.

- Severity: the condition of the customer's system when the case is opened.
- Priority: how important it is to the customer to have the issue resolved. It is not a field in the support system; it is something the customer can share.
- Business Impact: the effect the issue has on business operations.

Example 1. A Production database is offline and a critical application cannot run. Severity 1 (production, unavailable for business work). Priority High. Business Impact: barely functioning, risk of lost work, revenue lost per hour, an audit deadline approaching.

Example 2. The same fault on a reporting or replication target while production is fine, and an audit report is due. Severity 2 ("Restricted Operations"). Priority High, because running the reports on production would load it and hurt the main application. Business Impact: an audit deadline and financial penalties.

The SLOs are internal guidelines, not commitments. Progress may change a severity to match the condition the engineer finds. If a practical workaround or temporary solution is found, the severity is re-evaluated (usually lowered).

### Severity levels (paraphrased)

| Level | Meaning | Typical issues | Response | Target |
| --- | --- | --- | --- | --- |
| 1 | Production system down, no workaround | hang, crash or uncontrolled stop; data corruption or loss; security compromised; system or key component will not start or connect | 1 business hour | restore within 12 business hours; resolution in the next release |
| 2 | Restricted operations: production, development, test or migration hindered but still running | severe performance problems; production-down issue with a workaround in place; intermittent stability problems | 1 business hour | resolution within 14 calendar days |
| 3 | Minimal impact | cosmetic or GUI issues; nuisance; usage or roadmap questions; set-up or configuration help; enhancement requests | 1 day | resolution within 21 calendar days |

- Severity 1 needs the customer reachable round the clock and the engineer working continuously until resolved or circumvented; Severity 2 needs the customer's documentation, system and people available. If that is not the case, the severity is re-evaluated.
- A Severity 1 ticket notifies every support engineer and engineering management. On weekends Severity 1 cases should be opened by phone.
- Severity 1 includes "security compromised": apply the security incident gate in `security-vulnerability-handling.md` before any data is requested or opened.
- Engineers cannot change a ticket's severity. Check the stated severity against this table; if it does not fit, raise the doubt (see "Severity check" below) so the engineer can take it to the customer's Client Success Manager. Never state that the severity "is wrong"; say what does not fit.

### Severity check

- Needs the stated severity (1, 2 or 3), whether the system is production, whether a workaround is in place, and the business impact. Missing facts are asked, never assumed.
- Raise a doubt when the facts do not fit the stated level, in either direction. Examples: Severity 1 with no production outage, or with a workaround running (fits 2 or 3); Severity 3 for a hang, crash, data loss or a system that will not start in production (fits 1); Severity 2 or 1 for a how-to, configuration help or a cosmetic issue (fits 3); Severity 1 with a customer who cannot be reached round the clock.
- Output: one short paragraph, "Severity query: ...", naming the stated level, the facts that do not fit, the level they would fit, and that the engineer can raise it with the Client Success Manager. Add one line to `Timeline.md`: "Severity recorded: N" always, and "Severity query raised: ..." when a doubt is raised.
- A consistent severity gets no paragraph, only the Timeline line. An unknown severity is recorded as "unknown" and re-checked when the facts arrive.

### Case handling rules from the support guide (paraphrased)

- A reopen is allowed within 30 days, only for the same issue on the same system; otherwise a new case.
- Escalation reasons: high risk to business operations, production critically affected, or low satisfaction with the service level.
- Sunset or Retired releases get commercially reasonable effort only (no updates); recommend upgrading to a supported release.
- Support needs: description of expected and actual behaviour, symptoms, leading events and a timeline; for server issues a support dump, ErrorLogs, AccessLogs, platform and OS details; for performance also SAR and metering data, and pstack on request; for reproducible cases the steps, code and documents.

## Scope check

Compare what the customer asks for with the lists below (paraphrased from the Scope of Support policy, supplied by the maintainer). When a ticket goes FAR beyond scope, open the output with one short paragraph, "Scope flag: ...", naming the criterion and giving the scope-of-support link. Remind the engineer they may still choose to help, then carry on with the normal output. Requests inside scope, or only slightly beyond it, get no flag. Never guess a criterion that is not listed.

### Covered (no flag)

- Explaining standard features, intended use, coding techniques, capabilities and configuration; troubleshooting warnings, errors and exceptions, including in customer code built on the product.
- Diagnosing and reporting defects (customer isolates a reproducible sample), workarounds, fix timing, access to updates, guidance on logging Enhancement Requests.
- Platform/product compatibility, life cycle, planned certifications, which product fits a goal.
- Performance: reporting performance defects and GENERAL guidance, including OS or third-party tuning where it relates to MarkLogic's use of them.
- Remote assistance (the customer keeps keyboard control); troubleshooting in customer-provided virtual environments; problems with SupportLink, Communities, company websites and downloads.

### Criteria (what is not covered)

Entry format: `<what the customer asks for> — <policy category>`

- In-depth performance tuning of databases, applications, operating systems, cloud systems or networks — performance (Professional Services, chargeable)
- A dedicated support engineer — not offered
- Product training — training (Progress Education)
- Platform migration, disaster recovery planning, active monitoring, database health checks — administration, system and network tasks
- Interpreting results or training on data analysis; administering, configuring or debugging operating systems or networks — administration, system and network tasks
- Scoping or planning projects or migrations; doing upgrades on the customer's behalf — project requirements, migrations and upgrades
- Custom implementation: writing or implementing custom programs or functions, batch files or scripts, code conversion to another language — project requirements
- Recommending or assessing third-party products; supporting them beyond where they interface with MarkLogic; supporting contributions from third parties, Communities or Professional Services — third-party products
- Unauthorised changes to shipped files, code or scripts; tailored installs not made with an official installer — customizations
- Expired Maintenance and Support, evaluation licences, generating or delivering licence keys — evaluations, licences, expiry
- Direct support to end-users of Progress partners — partners
- Direct access to Progress Development/Engineering staff (Support is the liaison) — engineering access

Judgement: a short how-to or a sample query is "guidance"; a full custom program, a tuning engagement, a migration plan or a recurring health check is "far beyond". Several small asks are not a flag; one sustained engagement-sized ask is.

## Sources

- https://community.progress.com/s/products/marklogic/scope-of-support
- https://community.progress.com/s/products/marklogic/support-guide
- Covered / not covered lists: maintainer-supplied paraphrase of the Scope of Support policy (2026-10-21).
- Severity, priority, business impact, SLO and severity-level text, and the case-handling rules: maintainer-supplied paraphrase of the Support Guide and SLA pages; community pages cannot be fetched.
- The KB article on preparing diagnostic information (see `customer-diagnostics-guide.md`): https://community.progress.com/s/article/How-to-Prepare-and-Share-Diagnostic-Information-for-Progress-MarkLogic-Support-Cases
