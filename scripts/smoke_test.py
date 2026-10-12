#!/usr/bin/env python3
"""Smoke test for the deployed Contoso PolicyAssistant (real Foundry + Search).

1. Waits until /version reports the commit that was just deployed, which proves
   the running revision is the one this pipeline built.
2. Checks /health.
3. Asks one real question through /chat and checks the answer and its source.

Standard library only, so it runs anywhere with Python 3.
Usage:
  python scripts/smoke_test.py --url https://<app-url> --sha <commit>   # CI
  python scripts/smoke_test.py --url https://<app-url>                  # manual
Exit code 0 = pass, 1 = fail.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

QUESTION = "How many annual sick leave days are available to full-time employees?"
EXPECT_IN_ANSWER = "10"
EXPECT_SOURCE = "hr-leave-policy.md"


def call(url, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def wait_for_version(base, sha, timeout_s, interval_s):
    deadline, last = time.time() + timeout_s, "no response yet"
    while time.time() < deadline:
        try:
            _, body = call(f"{base}/version", timeout=20)
            last = body.get("git_sha")
            if sha is None or last == sha:
                print(f"OK   /version -> git_sha={last}")
                return
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last = f"{type(exc).__name__}"
        print(f"...  waiting for new revision (currently: {last})")
        time.sleep(interval_s)
    fail(f"/version never reported {sha} within {timeout_s}s (last: {last})")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--sha", default=None, help="expected git SHA; omit to skip the check")
    p.add_argument("--timeout", type=int, default=300, help="seconds to wait for the new revision")
    p.add_argument("--interval", type=int, default=10)
    a = p.parse_args()
    base = a.url.rstrip("/")

    wait_for_version(base, a.sha, a.timeout, a.interval)

    status, body = call(f"{base}/health")
    if status != 200 or body.get("status") != "ok":
        fail(f"/health returned {status} {body}")
    print("OK   /health")

    last_err = None
    for attempt in (1, 2):  # one retry covers a cold start or a transient model error
        try:
            t0 = time.time()
            status, body = call(f"{base}/chat", {"question": QUESTION}, timeout=120)
            latency = time.time() - t0
            break
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last_err = exc
            print(f"...  /chat attempt {attempt} failed: {type(exc).__name__}: {exc}")
            time.sleep(5)
    else:
        fail(f"/chat failed twice: {last_err}")

    answer, sources = body.get("answer", ""), body.get("sources", [])
    if EXPECT_IN_ANSWER not in answer:
        fail(f"answer does not contain {EXPECT_IN_ANSWER!r}: {answer!r}")
    if EXPECT_SOURCE not in sources:
        fail(f"{EXPECT_SOURCE} not in sources: {sources}")
    print(f"OK   /chat in {latency:.1f}s -> {answer[:100]!r} sources={sources}")
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
