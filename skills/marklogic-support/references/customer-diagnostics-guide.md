# Customer diagnostics guide (reference only)

A paraphrased digest of the KB article new customers are sent. Use it to help a customer send the data that helps the ticket at hand, nothing more.

## Rules for using it

Maintainer's policy, in the maintainer's words: the article "How to Prepare and Share Diagnostic Information for Progress MarkLogic Support Cases" is what new customers are sent. It is REFERENCE ONLY and NOT a hard requirement.

- Use it only when prompting a customer to send diagnostic and system data that would help this ticket.
- Extract (paraphrase) only the section that helps with the particular problem. Never quote or paste the whole article verbatim.
- Never present the folder structure as mandatory. The article itself says providing all of it is not mandatory. Say it helps the engineer, especially in clusters.
- Give the link only if the customer needs the full article.
- Ask for one or two items at a time, matched to the symptom (see `performance-data-requests.md` for the ready-made requests).

## What to extract for which problem

| Problem | Part of the article to extract | Paraphrase |
| --- | --- | --- |
| Customer unsure how to package or upload | General guidelines | Organise before sharing; one folder per environment (Prod, QA, Stage), never mixed; keep original names and unmodified logs; ZIP or TAR; describe behaviour, symptoms and a timeline in the case; extract once to check; upload via the case Attachments. If the upload fails (size limits) the engineer offers alternatives. |
| Support dump | Support dump | A cluster-level, status-only dump, the current one and an earlier one if things changed, sent to Progress MarkLogic Secure Storage; fallback is a `dump` folder in the case. |
| Data from several hosts | Multi-node host data | `hosts/<hostname>/` with `Logs/` (MarkLogic logs, including ErrorLog and RequestLog), `OSLogs/` (for example /var/log/messages), and `perf/`, `pstack/`, `sar/` only when requested. SAR comes from /var/log/sa/saXX, as text. |
| Meters data | Meters export | `performance/meters/`, sent as its own zip. |
| Reproducible case | Reproduction | `repro/` holding a runbook with the exact steps plus what is needed to run it: code, ml-gradle projects, Query Console workspace exports, sample data and the folder hierarchy. |
| Cloud deployment such as AWS EC2 | Cloud details | `cloud/` with the hostname to primary IP mapping (include the secondary ENI address), a copy of the DynamoDB table, volume count, size, type and IOPS, the exact CloudFormation templates (current and earlier), and host folders named by the secondary ENI hostname shown in the Admin UI. |
| Backups | Backups | Large; send separately over the secure transfer Support provides (Progress MoveIt or a ShareFile request), not as case attachments or email. |
| Environment and deployment information | Environment overview | A readable document: product and version, infrastructure type, instance or hardware, OS, cloud or service provider, storage layout, deployment strategy (manual, scripted, cloud automation), hostname to IP mapping, load balancer details. |

## Where our own requests fit (optional hints)

Mention a folder only when it helps, in one line, and say "see the guide" rather than asking for it. Output of our requests can be placed in:

- `hosts/<hostname>/pstack/` for the pstack movie
- `hosts/<hostname>/perf/` for a perf report, perf script output or raw perf.data
- `hosts/<hostname>/sar/` for SAR text from `LC_ALL=C S_TIME_FORMAT=ISO sar -A -f`
- `performance/meters/` for Meters export zips
- `dump/` or Secure Storage for the support dump

`analyse_pstack.py` and `analyse_perf.py` read this layout straight from a zip or folder and take the host from the `hosts/<hostname>/` folder. When the inputs come from more than one environment folder they add a Notes line, because environments should not be mixed.

## Sources

- KB 000299228, "How to Prepare and Share Diagnostic Information for Progress MarkLogic Support Cases", Jul 17, 2026: https://community.progress.com/s/article/How-to-Prepare-and-Share-Diagnostic-Information-for-Progress-MarkLogic-Support-Cases
- Maintainer-supplied copy of the article; community pages cannot be fetched, so the wording above is a paraphrase of that copy and the current page may differ.
