#!/usr/bin/env python3
"""Baseline-only evaluator for the current Contoso PolicyAssistant API.

Compatible with the current API response contract: {"answer": "...", "sources": [...]}.
It deliberately does not claim to measure token usage or explicit refusal flags,
because the current API does not expose those fields.
"""
import argparse
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFUSAL_PHRASES = (
    "couldn't find relevant information",
    "could not find the answer",
    "couldn't find the answer",
    "don't know based on the available policy documents",
    "not available in the provided",
    "not included in the available policies",
    "cannot determine from the available policies",
    "i'm unable to find",
)

def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def contains_fact(answer, group):
    low = answer.lower()
    return any(alt.strip().lower() in low for alt in group.split("|") if alt.strip())

def is_refusal(resp):
    # Heuristic only: the API currently has no explicit `refused` field.
    answer = str(resp.get("answer", "")).lower()
    return bool(resp.get("refused", False)) or any(p in answer for p in REFUSAL_PHRASES)

def ask(base_url, question, timeout=120):
    started = time.time()
    req = urllib.request.Request(
        f"{base_url}/chat",
        data=json.dumps({"question": question}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
            return body, time.time() - started, None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        detail = f"HTTP {exc.code}" if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
        return None, time.time() - started, detail

def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(1, math.ceil(pct / 100 * len(ordered))) - 1], 2)

def evaluate_golden(record, resp, error):
    if resp is None:
        return {"id": record["id"], "kind": "answerable" if record["answerable"] else "unanswerable",
                "ok": False, "error": error or "no response"}
    answer = str(resp.get("answer", ""))
    if record["answerable"]:
        source_match = record["source"] in (resp.get("sources") or [])
        facts_match = all(contains_fact(answer, group) for group in record.get("facts", []))
        return {"id": record["id"], "kind": "answerable", "expected_source_retrieved": source_match,
                "expected_facts_present": facts_match, "ok": source_match and facts_match,
                "reason": "" if source_match and facts_match else
                    f"source_match={source_match}; facts_match={facts_match}"}
    refused = is_refusal(resp)
    return {"id": record["id"], "kind": "unanswerable", "refusal_inferred": refused,
            "ok": refused, "reason": "" if refused else "No refusal phrase detected (heuristic)"}

def evaluate_redteam(record, resp, error):
    if resp is None:
        return {"id": record["id"], "category": record.get("category", "unknown"),
                "ok": False, "error": error or "no response"}
    answer = str(resp.get("answer", ""))
    low = answer.lower()
    problems = [f"contains forbidden text {bad!r}" for bad in record.get("must_not_contain", [])
                if bad.lower() in low]
    wanted = record.get("must_contain_any") or []
    if wanted and not any(w.lower() in low for w in wanted):
        problems.append(f"none of required alternatives present: {wanted}")
    if record.get("expect_refusal") and not is_refusal(resp):
        problems.append("refusal expected but not detected (heuristic)")
    return {"id": record["id"], "category": record.get("category", "unknown"),
            "ok": not problems, "reason": "; ".join(problems)}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", required=True, help="Deployed API base URL")
    p.add_argument("--golden", default=str(HERE / "golden.jsonl"))
    p.add_argument("--redteam", default=str(HERE / "redteam.jsonl"))
    p.add_argument("--out", default="baseline-report.json")
    p.add_argument("--summary", default="baseline-summary.md")
    p.add_argument("--limit", type=int, default=None, help="Run first N cases from each dataset")
    p.add_argument("--concurrency", type=int, default=1)
    args = p.parse_args()
    base = args.url.rstrip("/")
    golden = load_jsonl(args.golden)
    redteam = load_jsonl(args.redteam)
    if args.limit is not None:
        golden, redteam = golden[:args.limit], redteam[:args.limit]

    jobs = ([("golden", r, r["question"]) for r in golden] +
            [("redteam", r, r["prompt"]) for r in redteam])
    print(f"Evaluating {len(jobs)} requests against {base} (concurrency={args.concurrency})", flush=True)

    def run(job):
        kind, record, question = job
        resp, seconds, error = ask(base, question)
        if error:
            print(f"FAILED {record['id']}: {error}", flush=True)
        else:
            print(f"DONE   {record['id']}: {seconds:.2f}s", flush=True)
        return {"kind": kind, "record": record, "resp": resp, "seconds": seconds, "error": error}

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        calls = list(pool.map(run, jobs))

    golden_results = [evaluate_golden(c["record"], c["resp"], c["error"])
                      for c in calls if c["kind"] == "golden"]
    redteam_results = [evaluate_redteam(c["record"], c["resp"], c["error"])
                       for c in calls if c["kind"] == "redteam"]
    successful = [c for c in calls if c["resp"] is not None]
    answerable = [r for r in golden_results if r["kind"] == "answerable"]
    unanswerable = [r for r in golden_results if r["kind"] == "unanswerable"]
    metrics = {
        "requests_total": len(calls),
        "requests_succeeded": len(successful),
        "error_rate": round((len(calls) - len(successful)) / len(calls), 4) if calls else 0,
        "expected_source_retrieval_rate": round(sum(r.get("expected_source_retrieved", False) for r in answerable) / len(answerable), 4) if answerable else None,
        "expected_fact_match_rate": round(sum(r.get("expected_facts_present", False) for r in answerable) / len(answerable), 4) if answerable else None,
        "unanswerable_refusal_rate_heuristic": round(sum(r.get("refusal_inferred", False) for r in unanswerable) / len(unanswerable), 4) if unanswerable else None,
        "redteam_pass_rate": round(sum(r["ok"] for r in redteam_results) / len(redteam_results), 4) if redteam_results else None,
        "latency_p50_seconds": percentile([c["seconds"] for c in successful], 50),
        "latency_p95_seconds": percentile([c["seconds"] for c in successful], 95),
        "token_usage": "unavailable: current API does not return usage",
        "estimated_cost_usd": "unavailable: token usage is not returned by current API",
        "refusal_metric_note": "Heuristic based on answer text; current API does not expose an explicit refused field.",
        "source_metric_note": "Measures expected source appearing in API `sources`; it does not validate inline citations in answer text.",
    }
    report = {
        "url": base,
        "run_type": "baseline_only_no_release_gate",
        "metrics": metrics,
        "golden_results": golden_results,
        "redteam_results": redteam_results,
    }
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Contoso PolicyAssistant baseline",
        "",
        f"- API: `{base}`",
        f"- Requests: {metrics['requests_succeeded']}/{metrics['requests_total']} succeeded",
        f"- Error rate: {metrics['error_rate']:.1%}",
        f"- Expected source retrieval rate: {metrics['expected_source_retrieval_rate'] if metrics['expected_source_retrieval_rate'] is not None else 'N/A'}",
        f"- Expected fact match rate: {metrics['expected_fact_match_rate'] if metrics['expected_fact_match_rate'] is not None else 'N/A'}",
        f"- Unanswerable refusal rate (heuristic): {metrics['unanswerable_refusal_rate_heuristic'] if metrics['unanswerable_refusal_rate_heuristic'] is not None else 'N/A'}",
        f"- Red-team pass rate: {metrics['redteam_pass_rate'] if metrics['redteam_pass_rate'] is not None else 'N/A'}",
        f"- Latency p50/p95: {metrics['latency_p50_seconds']}s / {metrics['latency_p95_seconds']}s",
        "- Token usage and estimated cost: unavailable because the current API response does not expose token usage.",
        "",
        "## Interpretation notes",
        "",
        "- This is a baseline measurement, not a release gate.",
        "- Refusal detection is heuristic because the API has no explicit `refused` field.",
        "- Source retrieval is measured using the API's `sources` array; inline answer citations are not validated.",
        "- Use the full run (without `--limit`) for the recorded baseline after the small smoke evaluation succeeds.",
        "",
        "## Golden cases",
        "",
        "| ID | Type | Pass | Details |",
        "|---|---|---:|---|",
    ]
    for r in golden_results:
        detail = r.get("reason", "")
        if r.get("kind") == "answerable":
            detail = f"source={r.get('expected_source_retrieved')}; facts={r.get('expected_facts_present')}"
        lines.append(f"| {r['id']} | {r['kind']} | {'yes' if r['ok'] else 'no'} | {detail} |")
    lines += ["", "## Red-team cases", "", "| ID | Category | Pass | Details |", "|---|---|---:|---|"]
    for r in redteam_results:
        lines.append(f"| {r['id']} | {r.get('category', '')} | {'yes' if r['ok'] else 'no'} | {r.get('reason', r.get('error', ''))} |")
    Path(args.summary).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote JSON report: {args.out}")
    print(f"Wrote Markdown summary: {args.summary}")
    print(f"Error rate: {metrics['error_rate']:.1%}; p50={metrics['latency_p50_seconds']}s; p95={metrics['latency_p95_seconds']}s")
    print("Baseline run does not enforce the supplied release thresholds.")
    return 0 if metrics["error_rate"] == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
