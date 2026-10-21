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
- The sub-page "SLA & Severity Definitions" is linked from the scope page. Its text has NOT been supplied yet.

## Severity, priority and business impact

Three different things; do not mix them up when asking a customer.

- Severity: the condition of the customer's system when the case is opened.
- Priority: how important it is to the customer to have the issue resolved. It is not a field in the support system; it is something the customer can share.
- Business Impact: the effect the issue has on business operations.

Example 1. A Production database is offline and a critical application cannot run. Severity 1 (production, unavailable for business work). Priority High. Business Impact: barely functioning, risk of lost work, revenue lost per hour, an audit deadline approaching.

Example 2. The same fault on a reporting or replication target while production is fine, and an audit report is due. Severity 2 ("Restricted Operations"). Priority High, because running the reports on production would load it and hurt the main application. Business Impact: an audit deadline and financial penalties.

The resolution-time SLOs on the page are internal guidelines, not commitments.

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
- Severity, priority and business impact text: maintainer-supplied; community pages cannot be fetched.
- The KB article on preparing diagnostic information (see `customer-diagnostics-guide.md`): https://community.progress.com/s/article/How-to-Prepare-and-Share-Diagnostic-Information-for-Progress-MarkLogic-Support-Cases
