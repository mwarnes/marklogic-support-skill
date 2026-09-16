# Ticket audit trail — format and update rules

Every MarkLogic support ticket worked through this skill keeps a persistent, append-only audit
trail under `audit-trail/` inside the ticket folder (created by `/ticket <TICKET-ID>`). It exists
so the ticket's progress is traceable across sessions and reflects standard incident-management
stages: **Identification → Diagnosis → Escalation → Resolution → Closure**.

## Folder layout

```
<ticket-folder>/<TICKET-ID>/
    audit-trail/
        Timeline.md
        Analysis.md
        Required-Diagnostics.md
        Problems.md
        Root-Cause.md
```

`audit-trail/` sits directly under the ticket folder — never a loose file inside it, never mixed
with logs/dumps/exports. `/ticket` creates the folder and all five files (title line only) if they
don't exist; never truncate or recreate a file that already has content.

## Universal rules

- **Append-only.** Never delete or rewrite a prior entry to "clean up". A superseded conclusion
  gets a **new dated entry** saying what changed and why — the history of how understanding
  evolved is itself part of the record.
- **Timeline.md is mandatory on every update.** Any change to any of the other four files gets one
  line in Timeline.md. Not optional.
- **Dates/times**: `YYYY-MM-DD HH:MM`, one consistent timezone noted once at the top of
  Timeline.md.
- **Cross-link by number.** Any Analysis.md/Problems.md/Root-Cause.md entry that relates to a
  diagnostic request or a hypothesis cites it by file + number (`Required-Diagnostics.md #1`,
  `Problems.md #2`) so the files stay navigable as they grow.
- **Self-contained entries.** A reader should understand entry #3 without having read #1 and #2
  first.
- **Numbers are never reassigned.** A ruled-out `Problem #2` stays `#2` forever; the next new
  hypothesis is `#3` even if #2 is closed.
- **Symptom vs. root cause discipline.** Nothing goes into Root-Cause.md while it is still a
  hypothesis — it belongs in Problems.md until confirmed by evidence.
- **Audience split.** Analysis.md and Problems.md are internal-technical, as detailed as needed.
  Required-Diagnostics.md and Root-Cause.md's summary are plain, jargon-light, Salesforce-paste
  ready — no internal shorthand, no assumed context.

## Timeline.md

One line per significant event, oldest first, each line the direct consequence of a write to one
of the other four files:

```
2026-09-16 09:14 — Ticket opened. Customer reports intermittent 401s on SSO login.
2026-09-16 09:40 — Requested cluster topology + ALB config (see Required-Diagnostics.md #1)
2026-09-16 14:02 — Diagnostics received. Began log correlation across d-nodes.
2026-09-17 10:15 — Working hypothesis added to Problems.md #2
2026-09-18 16:30 — Root cause confirmed. See Root-Cause.md.
```

## Analysis.md

The ongoing engineering narrative — what's being done, what's been found, why — in prose, written
for a colleague picking the ticket up cold. Every entry stage-tagged:

```
## 2026-09-17 10:15 — [Diagnosis]
Reviewed the ErrorLog.txt from d-node-3 alongside the ALB access logs. The 401s correlate with
requests where the AuthnRequest and SAMLResponse hit different nodes. Consistent with per-request
state held in node-local memory rather than shared across the cluster (Problems.md #2). Next:
confirm ALB routing policy is round-robin rather than sticky.
```

Stage tags: `[Identification]`, `[Diagnosis]`, `[Escalation]`, `[Resolution]`, `[Closure]`.
Customer-facing language belongs in Required-Diagnostics.md and the Root-Cause.md summary, not
here.

## Required-Diagnostics.md

Everything asked of the customer, kept Salesforce-paste-ready: numbered, self-contained, states
*why* each item is needed.

```
## Diagnostic Request #1 — 2026-09-16
Could you please provide the following so we can narrow down the cause of the intermittent login
failures?

1. The full MarkLogic cluster topology (Admin UI → Cluster tab, or `xdmp:hosts()` output) for the
   affected group.
2. The AWS ALB target group configuration, specifically whether sticky sessions (session affinity)
   are enabled.
3. A copy of ErrorLog.txt from each d-node covering the time window of a recent failed login
   attempt, with the approximate timestamp of that attempt.

**Status:** Awaiting customer response
```

When fulfilled, **append** a status line under the same heading — `**Status:** Received
2026-09-16 14:02` — never delete or edit the original ask.

## Problems.md

A running log of every hypothesis considered, not just the one that wins. Protects against tunnel
vision and records what was ruled out and why.

```
## Problem #1 — 2026-09-16
**Hypothesis:** Certificate mismatch between IdP and SP metadata.
**Status:** Ruled out — 2026-09-16. Metadata exchange verified identical on both sides; certs
valid until 2027.

## Problem #2 — 2026-09-17
**Hypothesis:** ALB is not sticky-routing SAML flow; SP-initiated auth state is node-local, so
mid-flow requests can land on a node that never saw the AuthnRequest.
**Status:** Confirmed — 2026-09-18. Promoted to Root-Cause.md.
```

Status values: `Open`, `Ruled out (<reason>)`, `Confirmed`. Never delete a ruled-out hypothesis.

## Root-Cause.md

Written **once, and only once, root cause is confirmed** — never speculative.

```
## Root Cause — Confirmed 2026-09-18

**Summary:** MarkLogic's SP-initiated SAML SSO stores per-request authentication state in
node-local memory. In a multi-node cluster behind an AWS ALB without session affinity, the ALB
can route the IdP's SAMLResponse POST to a different node than the one that issued the
AuthnRequest, causing that node to reject the response with a 401.

**Evidence:** See Problems.md #2 and Analysis.md entries 2026-09-17 through 2026-09-18. Confirmed
by correlating ALB access logs (node routing) against ErrorLog.txt timestamps across all three
d-nodes.

**Fix / workaround:** [see below]

**Recommended fix:** Enable session affinity (sticky sessions) on the ALB target group, OR
implement RelayState-based state passing so auth state isn't tied to a single node.

**Ticket status:** Resolution pending customer implementation / MarkLogic engineering defect
report.
```

If root cause is later revised, add a **new dated section** — never edit the original — with a
note explaining what changed.

## ITIL-style stage mapping

- **Identification** — symptom captured, ticket scoped, initial severity/priority set.
- **Diagnosis** — hypotheses formed (Problems.md), diagnostics requested
  (Required-Diagnostics.md), evidence gathered and reasoned through (Analysis.md).
- **Escalation** (if needed) — Analysis.md records what was escalated, to whom, why; keep
  Required-Diagnostics.md in sync if the escalation target needs more data.
- **Resolution** — root cause confirmed (Root-Cause.md), fix identified/applied.
- **Closure** — final summary for the customer, drawn from Root-Cause.md and the resolution
  entry in Analysis.md; confirm customer acceptance before closing.

## When the agent writes what (see SKILL.md's "Audit trail" section for the trigger conditions)

- Identification/Diagnosis entries (Timeline, Analysis, Problems as `Open`, Required-Diagnostics)
  are written automatically as a side effect of normal triage output.
- A Problem moving to `Confirmed`, Root-Cause.md being written, an Escalation entry, or a Closure
  entry each require the engineer's explicit go-ahead in the conversation first — these are
  assertions, not triage output, and are never auto-committed to the permanent record.
