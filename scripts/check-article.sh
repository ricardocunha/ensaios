#!/usr/bin/env bash
# Pre-publish checks for one article folder. Exit code 1 if anything needs attention.
#   scripts/check-article.sh articles/<yyyy-mm>-<slug>
set -uo pipefail
dir="${1:?usage: scripts/check-article.sh articles/<yyyy-mm>-<slug>}"
[ -d "$dir" ] || { echo "no such folder: $dir"; exit 2; }
fail=0

echo "== placeholders"
if grep -n -E '\[\[(RESULT|VERIFY|LINK)' "$dir"/*.md; then fail=1; else echo "none"; fi

echo "== required files"
for f in README.md article-en.md linkedin-en.md; do
  [ -f "$dir/$f" ] || { echo "missing $f"; fail=1; }
done

echo "== secrets and private data tracked by git"
tracked=$(git ls-files "$dir")
if echo "$tracked" | grep -E '(^|/)\.env$|(^|/)private/'; then fail=1; fi
if [ -n "$tracked" ] && echo "$tracked" | xargs grep -l -E 'sk-ant-[A-Za-z0-9]|(LANGSMITH|BASETEN|FIREWORKS|HF)_API_KEY=[A-Za-z0-9]' 2>/dev/null; then
  fail=1
fi

echo "== links still pointing at a branch"
grep -n -E 'tree/article/' "$dir"/*.md && fail=1

[ "$fail" = 0 ] && echo "OK: ready to merge" || echo "NOT READY"
exit "$fail"
