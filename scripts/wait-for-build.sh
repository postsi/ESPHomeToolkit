#!/usr/bin/env bash
# Poll GitHub Actions until the workflow run for the given commit (or latest) completes.
# Run after ./scripts/deploy.sh so we wait for the build for the commit we just pushed.
# Usage: ./scripts/wait-for-build.sh [repo_owner/repo_name] [commit_sha]
# Example: ./scripts/wait-for-build.sh
#          ./scripts/wait-for-build.sh postsi/ESPHomeToolkit abc123
set -e

# Usage: [repo] or [commit_sha] or [repo commit_sha]
COMMIT_SHA=""
REPO=""
if [[ "${1:-}" =~ ^[0-9a-fA-F]{40}$ ]]; then
  COMMIT_SHA="$1"
  ORIGIN="$(git remote get-url origin 2>/dev/null || true)"
  if [[ "$ORIGIN" =~ github\.com[:/]([^/]+/[^/.]+) ]]; then REPO="${BASH_REMATCH[1]%.git}"; else REPO="postsi/ESPHomeToolkit"; fi
elif [[ -n "${1:-}" ]] && [[ "$1" == */* ]]; then
  REPO="$1"
  [[ "${2:-}" =~ ^[0-9a-fA-F]{40}$ ]] && COMMIT_SHA="$2"
else
  ORIGIN="$(git remote get-url origin 2>/dev/null || true)"
  if [[ "$ORIGIN" =~ github\.com[:/]([^/]+/[^/.]+) ]]; then REPO="${BASH_REMATCH[1]%.git}"; else REPO="postsi/ESPHomeToolkit"; fi
  [[ "${1:-}" =~ ^[0-9a-fA-F]{40}$ ]] && COMMIT_SHA="$1"
fi

if [[ -n "$COMMIT_SHA" ]]; then
  echo "Waiting for workflow run for commit ${COMMIT_SHA:0:7}..."
else
  echo "Waiting for latest workflow run..."
fi
echo "Polling GitHub Actions for $REPO every 10s (Ctrl+C to stop)."
echo ""

API="https://api.github.com/repos/$REPO/actions/runs?per_page=20"
while true; do
  PAYLOAD="$(curl -sS "$API" 2>/dev/null)" || { echo "Failed to fetch $API"; sleep 10; continue; }
  STATUS="$(echo "$PAYLOAD" | python3 -c "
import sys, json
commit_sha = '''$COMMIT_SHA'''.strip()
try:
    r = json.load(sys.stdin)
    runs = r.get('workflow_runs', [])
    if not runs:
        print('no_runs|||')
        sys.exit(0)
    if commit_sha:
        for w in runs:
            if (w.get('head_sha') or '') == commit_sha or (w.get('head_sha') or '').startswith(commit_sha):
                break
        else:
            w = None
        if w is None:
            print('no_match|||')
            sys.exit(0)
    else:
        w = runs[0]
    status = w.get('status', '?')
    conclusion = w.get('conclusion') or ''
    run_num = w.get('run_number', '?')
    name = w.get('name', '?')
    head = (w.get('head_sha') or '')[:7]
    print(status + '|' + conclusion + '|' + str(run_num) + '|' + name + '|' + head)
except Exception as e:
    print('error|' + str(e) + '|||')
    sys.exit(1)
" 2>/dev/null)" || STATUS="error|fetch failed||||"

  IFS='|' read -r status conclusion run_num name head_short _ <<< "$STATUS"

  if [[ "$status" == "completed" ]]; then
    echo ""
    if [[ "$conclusion" == "success" ]]; then
      echo "Build completed successfully (run #$run_num: $name)."
      echo "You can now update the add-on in Home Assistant to this version."
      exit 0
    else
      echo "Build finished with conclusion: $conclusion (run #$run_num: $name)."
      echo "Check: https://github.com/$REPO/actions"
      exit 1
    fi
  fi

  if [[ "$status" == "no_match" ]] || [[ "$status" == "no_runs" ]]; then
    echo "$(date '+%H:%M:%S') — run for commit not yet listed ... waiting 10s"
  else
    echo "$(date '+%H:%M:%S') — status=$status (run #$run_num: $name) ... waiting 10s"
  fi
  sleep 10
done
