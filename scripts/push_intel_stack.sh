#!/usr/bin/env bash
# Push only the intel-stack/ folder to the intel-stack remote (no clone).
# One-time: git remote add intel-stack https://github.com/YOUR_USER/intel-stack.git
# Then: ./scripts/push_intel_stack.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEBLOGGER="$(dirname "$SCRIPT_DIR")"
cd "$WEBLOGGER"

if ! git remote get-url intel-stack &>/dev/null; then
  echo "Remote 'intel-stack' not found. Add it once:"
  echo "  git remote add intel-stack git@github.com:rishavsen1/arxiv_cast.git"
  exit 1
fi

BRANCH="${1:-main}"
echo "Pushing intel-stack/ to remote 'intel-stack' (branch $BRANCH)..."
git subtree push --prefix=intel-stack intel-stack "$BRANCH"
echo "Done."
