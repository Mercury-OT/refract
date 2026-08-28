#!/usr/bin/env bash
#
# Repository hygiene checks for the public Refract repository.
#
# WHAT THIS IS NOT
# ----------------
# This is NOT a product-neutrality gate, and it must never be labelled as one.
#
# The leaks that actually matter — scale figures tied to an identity, "we already
# verified this internally" claims, private naming carried over by habit — are not
# expressible as a pattern, so no script can catch them. A gate that catches only the
# easy cases manufactures false confidence, which is worse than no gate at all.
# Product neutrality is therefore a HUMAN review, performed per change, judged by
# asking "is the source of this fact publicly stateable?" rather than "is this word on
# a list".
#
# A deny-list of forbidden words must never live in this repository: the list itself
# would publish exactly what it is meant to conceal. Everything below is instead a
# POSITIVE check — it names only what IS allowed, so it leaks nothing.
#
set -euo pipefail

status=0

report() {
    echo "[hygiene] FAIL: $1" >&2
    status=1
}

# deny <description> <extended-regex> [<allowed-extended-regex>]
#
# Fails if any tracked text file matches <extended-regex>, except for lines that also
# match the optional allow-list pattern.
deny() {
    local description="$1" pattern="$2" allow="${3:-}" hits
    if [ -n "$allow" ]; then
        hits="$(git grep -nI -E "$pattern" -- . | grep -v -E "$allow" || true)"
    else
        hits="$(git grep -nI -E "$pattern" -- . || true)"
    fi
    if [ -n "$hits" ]; then
        report "$description"
        printf '%s\n' "$hits" >&2
    fi
}

echo "[hygiene] unresolved merge conflict markers"
deny "unresolved merge conflict markers in tracked files" '^(<<<<<<<|=======|>>>>>>>)'

echo "[hygiene] tracked secret-like files"
tracked_secret_like_files="$({
    git ls-files -- '*.pem' '*.key' '*.p12' '*.pfx' '*.crt' '*.cer' '*.mobileprovision' 2>/dev/null || true
    git ls-files -- '.env' '.env.*' '*.env' 2>/dev/null || true
} | sed '/^$/d' | sort -u)"
if [ -n "$tracked_secret_like_files" ]; then
    report "tracked secret-like files; remove them from the public repository"
    printf '%s\n' "$tracked_secret_like_files" >&2
fi

# A local absolute path exposes the machine it was written on, and often a real name.
# Patterns are written with a bracketed first character (`/[U]sers/`) so that this file
# does not match its own rules. That keeps the gate itself subject to the gate — the
# previous neutrality gate leaked precisely because it was exempt from scrutiny.
echo "[hygiene] machine-local absolute paths"
deny "machine-local absolute path; use a repository-relative path" '(/[U]sers/|/[h]ome/[a-z]|[A-Z]:\\)'

echo "[hygiene] e-mail addresses"
deny "e-mail address in a tracked file" '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}'

# Only loopback, documentation domains, the licence URL, and official package hosts
# required by the generated dependency lock may appear. Anything else is a host that
# exists somewhere real, which is how internal service names escape.
echo "[hygiene] non-allowlisted hosts"
deny "URL pointing at a host outside the public allow-list" \
     'https?://[A-Za-z0-9._:/-]+' \
     '://(localhost|127\.0\.0\.1|0\.0\.0\.0|example\.(com|org|net)|www\.apache\.org|pypi\.org|files\.pythonhosted\.org)([/:]|$)'

echo "[hygiene] private-range IP addresses"
deny "private-range IP address; internal network topology must not be published" \
     '(^|[^0-9.])(10\.[0-9]+\.[0-9]+\.[0-9]+|192\.168\.[0-9]+\.[0-9]+|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+)'

# The public repository is written in English so the community can read it.
# Non-English text in a tracked file is therefore either an oversight or a note
# that was never meant to be published.
# Matched by UTF-8 lead bytes so the check works with both BSD and GNU grep.
echo "[hygiene] non-English (CJK) text in tracked files"
if hits="$(LC_ALL=C git grep -nI -E $'[\xe4-\xe9][\x80-\xbf][\x80-\xbf]' -- . || true)"; [ -n "$hits" ]; then
    report "non-English text in a tracked file; the public repository is English-only"
    printf '%s\n' "$hits" >&2
fi

if [ "$status" -ne 0 ]; then
    echo "[hygiene] repository hygiene checks FAILED" >&2
    exit 1
fi

echo "[hygiene] repository hygiene checks passed"
echo "[hygiene] reminder: product neutrality is a human review, not this script."
