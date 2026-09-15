#!/usr/bin/env bash
# Usage: tools/check-ref.sh <reference.md>  — validates the fixed reference shape.
set -e
f="$1"
[ -f "$f" ] || {
 echo "FAIL: $f missing"
 exit 1
}
for h in "## Concepts" "## Standard procedures" "## Common mistakes & symptoms" "## Sources"; do
 grep -qxF "$h" "$f" || {
  echo "FAIL: $f missing heading '$h'"
  exit 1
 }
done
grep -qF '| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |' "$f" ||
 {
  echo "FAIL: $f missing mistakes table header"
  exit 1
 }
# every table body row (starts with '|', not header/separator) must carry a source
awk '/^\| Mistake/{t=1;next} t&&/^\|[- |]+\|$/{next} t&&/^\|/{print} t&&!/^\|/{t=0}' "$f" |
 grep -vE 'http|Inside MarkLogic p\.[0-9]+|\[unverified — confirm\]' |
 head -1 | grep -q . && {
 echo "FAIL: $f has a mistakes row without Source"
 exit 1
}
max=250
case "$f" in *architecture.md) max=120 ;; esac
[ "$(wc -l <"$f")" -le "$max" ] || {
 echo "FAIL: $f exceeds $max lines"
 exit 1
}
echo "OK: $f"
