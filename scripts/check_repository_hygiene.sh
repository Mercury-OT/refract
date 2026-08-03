#!/usr/bin/env bash
set -euo pipefail

fail() {
    echo "[hygiene] $1" >&2
    exit 1
}

echo "[hygiene] checking for unresolved merge conflict markers"
if git grep -nE '^(<<<<<<<|=======|>>>>>>>)' -- . >/tmp/refract-hygiene-conflicts.txt 2>/dev/null; then
    cat /tmp/refract-hygiene-conflicts.txt >&2
    rm -f /tmp/refract-hygiene-conflicts.txt
    fail "unresolved merge conflict markers detected in tracked files"
fi
rm -f /tmp/refract-hygiene-conflicts.txt

echo "[hygiene] checking for tracked secret-like files"
tracked_secret_like_files="$({
    git ls-files -- '*.pem' '*.key' '*.p12' '*.pfx' '*.crt' '*.cer' '*.mobileprovision' 2>/dev/null || true
    git ls-files -- '.env' '.env.*' '*.env' 2>/dev/null || true
} | sed '/^$/d' | sort -u)"
if [ -n "$tracked_secret_like_files" ]; then
    printf '%s\n' "$tracked_secret_like_files" >&2
    fail "tracked secret-like files detected; remove them from the public repository"
fi

echo "[hygiene] repository hygiene checks passed"
