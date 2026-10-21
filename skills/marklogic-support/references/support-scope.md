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
- The sub-pages "Scope Of Support Policy" and "SLA & Severity Definitions" are linked from the scope page. Their text has NOT been supplied yet.

## Severity, priority and business impact

Three different things; do not mix them up when asking a customer.

- Severity: the condition of the customer's system when the case is opened.
- Priority: how important it is to the customer to have the issue resolved. It is not a field in the support system; it is something the customer can share.
- Business Impact: the effect the issue has on business operations.

Example 1. A Production database is offline and a critical application cannot run. Severity 1 (production, unavailable for business work). Priority High. Business Impact: barely functioning, risk of lost work, revenue lost per hour, an audit deadline approaching.

Example 2. The same fault on a reporting or replication target while production is fine, and an audit report is due. Severity 2 ("Restricted Operations"). Priority High, because running the reports on production would load it and hurt the main application. Business Impact: an audit deadline and financial penalties.

The resolution-time SLOs on the page are internal guidelines, not commitments.

## Scope check (pending criteria)

The policy's lists of what is and is not covered have NOT been supplied yet. Until a `Criteria` list is added below:

- do NOT guess what is out of scope;
- do NOT raise scope flags on your own.

Once criteria exist, compare the ticket's requests with them. When a ticket goes FAR beyond the scope of a support ticket, open the output with one short paragraph, "Scope flag: ...", naming the criterion and giving the policy link. Remind the engineer they may still choose to help, then carry on with the normal output. Ordinary requests that are inside scope, or only slightly beyond it, get no flag.

### Criteria (to be filled from the Scope Of Support Policy)

Entry format: `- <what the customer asks for> — <why it is out of scope> — <policy section>`

(none yet)

## Sources

- https://community.progress.com/s/products/marklogic/scope-of-support
- https://community.progress.com/s/products/marklogic/support-guide
- Severity, priority and business impact text: maintainer-supplied; community pages cannot be fetched.
- The KB article on preparing diagnostic information (see `customer-diagnostics-guide.md`): https://community.progress.com/s/article/How-to-Prepare-and-Share-Diagnostic-Information-for-Progress-MarkLogic-Support-Cases
