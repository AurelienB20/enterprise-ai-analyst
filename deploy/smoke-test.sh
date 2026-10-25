#!/bin/sh
# Checks a running stack from outside, through Caddy, without spending LLM tokens unless
# asked: ./smoke-test.sh https://localhost
# With a real ANTHROPIC_API_KEY, add --ask to run one question end to end (~$0.05).
# With a fake key (CI), --fake-llm checks the whole chain up to the provider, which must
# refuse the key: the API answers "failed" cleanly and records the attempt.
set -eu

base="${1:-https://localhost}"
ask="${2:-}"
failures=0

check() {
    if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2', expected '$3'"; failures=$((failures + 1)); fi
}

check "home page" "$(curl -sk -o /dev/null -w '%{http_code}' "$base/")" "200"
headers="$(curl -skI "$base/")"
check "HSTS" "$(echo "$headers" | grep -ci '^strict-transport-security')" "1"
check "CSP" "$(echo "$headers" | grep -ci '^content-security-policy')" "1"
check "no Server header" "$(echo "$headers" | grep -ci '^server:')" "0"
check "API not published" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health || true)" "000"
check "proxy refuses GET" "$(curl -sk -o /dev/null -w '%{http_code}' "$base/api/analyses")" "405"
check "question too short" \
    "$(curl -sk -o /dev/null -w '%{http_code}' -X POST "$base/api/analyses" -H 'content-type: application/json' -d '{"question":"a"}')" "422"

if [ "$ask" = "--fake-llm" ]; then
    body="$(curl -sk -X POST "$base/api/analyses" -H 'content-type: application/json' \
        -d '{"question":"How many active customers do we have?"}')"
    check "question reaches the provider" "$(echo "$body" | grep -o '"status":"[a-z]*"' | head -1)" '"status":"failed"'
    check "provider refused the fake key" "$(echo "$body" | grep -c 'rejected the API key')" "1"
fi

if [ "$ask" = "--ask" ]; then
    status="$(curl -sk -X POST "$base/api/analyses" -H 'content-type: application/json' \
        -d '{"question":"How many active customers do we have?"}' | grep -o '"status":"[a-z]*"' | head -1)"
    check "one real question" "$status" '"status":"answered"'
fi

if [ "$failures" -gt 0 ]; then echo "$failures check(s) failed"; exit 1; fi
echo "All checks passed"
