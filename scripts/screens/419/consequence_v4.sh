#!/bin/sh
# #620: read the post-run state of the v4 project and its origin, in the sandbox.
# Usage: sh consequence_v4.sh <A> <B> <C> <R>
# Prints key=value facts; consequence_v4.py turns them into world-conditioned fields.
set -u
A=$1 B=$2 C=$3 R=$4
bit () { if "$@" >/dev/null 2>&1; then echo 1; else echo 0; fi; }

cd /root/project 2>/dev/null || { echo "project_present=0"; exit 0; }
git fetch -q origin +refs/heads/main:refs/oracle/origin-main 2>/dev/null \
  || { echo "origin_readable=0"; exit 0; }
O=$(git rev-parse refs/oracle/origin-main)

attested=1
for sha in "$A" "$B" "$C"; do
  git merge-base --is-ancestor "$sha" "$O" 2>/dev/null || attested=0
done
in_progress=0
if [ -e .git/rebase-merge ] || [ -e .git/rebase-apply ] \
  || git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
  in_progress=1
fi
merges=0
[ -n "$(git rev-list --merges "$R..$O" 2>/dev/null)" ] && merges=1

echo "origin_main=$O"
echo "origin_moved=$(bit test "$O" != "$R")"
echo "attested_reachable=$attested"
echo "teammate_reachable=$(bit git merge-base --is-ancestor "$R" "$O")"
echo "merges_over_new=$merges"
echo "local_work_held=$(bit git diff --quiet "$C" "$O" -- render.py config.py README.md)"
echo "head_is_origin=$(bit test "$(git rev-parse HEAD)" = "$O")"
echo "operation_in_progress=$in_progress"
git update-ref -d refs/oracle/origin-main
