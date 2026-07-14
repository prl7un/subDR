#!/usr/bin/env bash
# On-prem heartbeat for AWS EC2 (Linux). Same behavior as keepalive.ps1.
# Requires: git, curl.
# Healthchecks ping URL: hc-ping-url.local.txt (gitignored, never commit).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PING_FILE="${REPO_DIR}/hc-ping-url.local.txt"
KEEPALIVE_FILE="${REPO_DIR}/KEEPALIVE.txt"
BRANCH="main"
REMOTE="origin"

cd "${REPO_DIR}"

# Prevent overlapping cron runs
LOCK_DIR="${REPO_DIR}/.keepalive.lock"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "Another keepalive is running. Exit."
  exit 0
fi
trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT

# --- Healthchecks ping ---
if [[ -f "${PING_FILE}" ]]; then
  PING_URL="$(tr -d '[:space:]' < "${PING_FILE}")"
  if [[ -n "${PING_URL}" ]]; then
    curl -sS -o /dev/null --max-time 10 "${PING_URL}" || echo "WARN: Healthchecks ping failed"
  else
    echo "WARN: ${PING_FILE} is empty"
  fi
else
  echo "WARN: ${PING_FILE} missing. Create it with one line: https://hc-ping.com/UUID"
fi

# --- Git heartbeat (secondary signal / audit trail) ---
git pull --quiet "${REMOTE}" "${BRANCH}"

timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
echo "last_keepalive: ${timestamp}" > "${KEEPALIVE_FILE}"

git add KEEPALIVE.txt
if git diff --cached --quiet; then
  echo "No keepalive change."
  exit 0
fi

git -c user.email="keepalive@subdr.local" -c user.name="subDR Keepalive" \
  commit -m "keepalive: ${timestamp}" --quiet
git push --quiet "${REMOTE}" "HEAD:${BRANCH}"
echo "Keepalive sent at ${timestamp} (Healthchecks ping + git push)"
