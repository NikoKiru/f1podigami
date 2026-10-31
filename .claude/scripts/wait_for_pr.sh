#!/usr/bin/env bash
# Usage: bash .claude/scripts/wait_for_pr.sh <pr-number>
#
# Waits until a PR has merged and every check has finished, then prints them. For
# a PR into main it also waits for the deploy. Exits 1 if anything failed.
#
# It exists because neither obvious wait is enough here: auto-merge only waits for
# required checks, so E2E (browser) can still be running or fail after the merge,
# and `gh pr checks --watch` can exit green while CI jobs are still queued.
set -u

pr=${1:?usage: wait_for_pr.sh <pr-number>}
interval=${WAIT_INTERVAL:-30}

# count <jq bucket filter> <answer while GitHub has no checks to report>. Right
# after a push `gh pr checks` errors, which means "not yet", never "failed".
count() {
    gh pr checks "$pr" --json bucket --jq "[.[] | select($1)] | length" 2>/dev/null || echo "$2"
}

while :; do
    state=$(gh pr view "$pr" --json state --jq .state)
    failed=$(count '.bucket == "fail" or .bucket == "cancel"' 0)
    pending=$(count '.bucket == "pending"' 1)
    [ "$failed" != 0 ] && break
    [ "$state" = CLOSED ] && break
    [ "$state" = MERGED ] && [ "$pending" = 0 ] && break
    sleep "$interval"
done

gh pr checks "$pr" | cut -f1,2,3
echo "PR #$pr: $state, $failed failed"
[ "$failed" = 0 ] && [ "$state" = MERGED ] || exit 1

[ "$(gh pr view "$pr" --json baseRefName --jq .baseRefName)" = main ] || exit 0

commit=$(gh pr view "$pr" --json mergeCommit --jq .mergeCommit.oid)
while :; do
    status=$(gh run list --workflow deploy.yml --commit "$commit" --json status --jq '.[0].status')
    [ "$status" = completed ] && break
    sleep "$interval"
done
conclusion=$(gh run list --workflow deploy.yml --commit "$commit" --json conclusion --jq '.[0].conclusion')
echo "Deploy: $conclusion"
[ "$conclusion" = success ]
