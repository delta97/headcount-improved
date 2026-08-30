#!/usr/bin/env python3
"""Live routing evaluation: does a real model pick the right skill for each eval prompt?

Opt-in and credentialed on purpose — ordinary CI and local validation stay free and offline
(scripts/validate-routing-evals.py covers those). This runner presents the model with what
Claude Code's routing sees, every skill's `department:skill` address and description, and asks
which single skill should handle each case's prompt. It measures description quality and
boundary overlap through the same lens the harness uses; it does not execute the harness's own
selection code, so treat results as a strong signal rather than a certification.

  ANTHROPIC_API_KEY=...  python3 scripts/run-routing-evals.py
      --model claude-sonnet-5     model to evaluate against
      --runs 1                    samples per case (majority is not taken; each run is a trial)
      --tags near-neighbor        only cases carrying this tag (repeatable)
      --json PATH                 write full machine-readable results
      --threshold 0.9             exit non-zero if pass rate falls below this
      --limit N                   first N cases only (smoke run)

Scoring per trial: any forbidden skill selected fails the case outright; otherwise the
selection passes if it is in `expected` (a hit) or `acceptable` (ambiguity, accepted and
counted separately); a case with neither expected nor acceptable passes when nothing
forbidden was selected. No dependencies — stdlib HTTP against the Anthropic Messages API.
"""
import argparse
import collections
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
CASES = "evals/routing/cases.jsonl"


def catalog():
    out = []
    for path in sorted(glob.glob("plugins/*/skills/*/SKILL.md")):
        parts = path.split(os.sep)
        text = open(path, encoding="utf-8").read()
        front = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
        desc = re.search(r"^description:\s*(.+)$", front.group(1), re.M).group(1).strip()
        out.append((f"{parts[1]}:{parts[3]}", desc))
    return out


def build_system(skills):
    lines = "\n".join(f"- {addr} — {desc}" for addr, desc in skills)
    return (
        "You are the skill router for an agent organization. Below is the complete catalog of "
        "installed skills, one per line, as `department:skill — description`.\n\n"
        f"{lines}\n\n"
        "Given a user request, decide which single skill should activate. Reply with ONLY a JSON "
        'object on one line: {"skill": "department:skill"} — or {"skill": null} if no skill in '
        "the catalog should activate. No prose, no code fences."
    )


def ask(model, system, prompt, api_key):
    body = json.dumps({
        "model": model,
        "max_tokens": 100,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    text = "".join(b.get("text", "") for b in data.get("content", []))
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None, text
    try:
        return json.loads(m.group(0)).get("skill"), text
    except ValueError:
        return None, text


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--tags", action="append", default=[])
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--threshold", type=float)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("run-routing-evals: set ANTHROPIC_API_KEY. This runner is opt-in; the deterministic "
              "checks (validate-routing-evals.py) need no credentials.", file=sys.stderr)
        return 2

    cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
    if args.tags:
        cases = [c for c in cases if set(args.tags) & set(c["tags"])]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("no cases matched", file=sys.stderr)
        return 2

    system = build_system(catalog())
    trials = []
    for case in cases:
        for run in range(args.runs):
            try:
                selected, raw = ask(args.model, system, case["prompt"], api_key)
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                print(f"  {case['id']}: API error: {e}", file=sys.stderr)
                selected, raw = None, f"ERROR: {e}"
            expected, acceptable = case["expected"], case["acceptable"]
            forbidden_hit = selected in case["forbidden"] if selected else False
            if forbidden_hit:
                outcome = "forbidden"
            elif selected and selected in expected:
                outcome = "pass"
            elif selected and selected in acceptable:
                outcome = "ambiguous-accepted"
            elif not expected and not acceptable:
                outcome = "pass"  # negative-only case, nothing forbidden selected
            else:
                outcome = "fail"
            trials.append({"id": case["id"], "run": run, "selected": selected,
                           "outcome": outcome, "expected": expected, "raw": raw})

    # ── Aggregate ────────────────────────────────────────────────────────────────
    n = len(trials)
    passed = sum(t["outcome"] == "pass" for t in trials)
    ambiguous = sum(t["outcome"] == "ambiguous-accepted" for t in trials)
    forbidden = sum(t["outcome"] == "forbidden" for t in trials)
    failures = n - passed - ambiguous

    recall_hit, recall_all = collections.Counter(), collections.Counter()
    precision_hit, precision_all = collections.Counter(), collections.Counter()
    confusion = collections.Counter()
    for t in trials:
        ideal = t["expected"][0] if t["expected"] else None
        if ideal:
            recall_all[ideal] += 1
            if t["selected"] == ideal:
                recall_hit[ideal] += 1
            elif t["selected"]:
                confusion[(ideal, t["selected"])] += 1
        if t["selected"]:
            precision_all[t["selected"]] += 1
            if t["outcome"] in ("pass", "ambiguous-accepted"):
                precision_hit[t["selected"]] += 1

    pass_rate = (passed + ambiguous) / n if n else 0.0
    print("Routing evaluation")
    print("------------------")
    print(f"Model: {args.model}   runs per case: {args.runs}")
    print(f"Trials: {n}")
    print(f"Pass: {passed}")
    print(f"Ambiguous accepted: {ambiguous}")
    print(f"Failures: {failures} (of which forbidden selections: {forbidden})")
    print(f"Pass rate: {pass_rate:.1%}")
    worst = sorted(recall_all, key=lambda s: recall_hit[s] / recall_all[s])[:5]
    if worst:
        print("\nLowest per-skill recall:")
        for s in worst:
            print(f"  {s}: {recall_hit[s]}/{recall_all[s]}")
    if confusion:
        print("\nTop confusion pairs (expected -> selected):")
        for (a, b), c in confusion.most_common(8):
            print(f"  {a} -> {b}  ({c})")

    if args.json_out:
        report = {
            "model": args.model, "runs": args.runs, "trials": n,
            "pass": passed, "ambiguous_accepted": ambiguous, "failures": failures,
            "forbidden_selections": forbidden, "pass_rate": pass_rate,
            "recall": {s: [recall_hit[s], recall_all[s]] for s in recall_all},
            "precision": {s: [precision_hit[s], precision_all[s]] for s in precision_all},
            "confusion": [{"expected": a, "selected": b, "count": c}
                          for (a, b), c in confusion.most_common()],
            "results": [{k: t[k] for k in ("id", "run", "selected", "outcome")} for t in trials],
        }
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nwrote {args.json_out}")

    if args.threshold is not None and pass_rate < args.threshold:
        print(f"\nFAIL: pass rate {pass_rate:.1%} below threshold {args.threshold:.1%}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
