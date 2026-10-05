#!/usr/bin/env python3
"""
Feed the already-generated jailbreak-strategy prompts from redteam.yaml
to the running app and record prompt/response pairs for manual review.

No LLM grading, no API key — just the plumbing. Use this when you intend
to read the responses yourself rather than trust an automated grader.

Usage:
    python promptfoo/run_manual_probe.py [--strategy-prefix jailbreak] [--out FILE]

Requires the Flask app running locally first: python app.py
"""
import argparse
import json
import sys
import time
import urllib.request

import yaml

TARGET_URL = "http://localhost:5050/api/ask"


def load_tests(config_path: str, strategy_prefix: str):
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    tests = []
    for t in cfg["tests"]:
        meta = t.get("metadata", {})
        strategy_id = meta.get("strategyId", "")
        if strategy_prefix and not strategy_id.startswith(strategy_prefix):
            continue
        tests.append({
            "prompt": t["vars"]["prompt"],
            "pluginId": meta.get("pluginId", ""),
            "strategyId": strategy_id,
            "goal": meta.get("goal", "").strip(),
        })
    return tests


def ask(prompt: str, timeout: int = 150) -> dict:
    body = json.dumps({"message": prompt}).encode()
    req = urllib.request.Request(
        TARGET_URL, data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="promptfoo/redteam.yaml")
    parser.add_argument("--strategy-prefix", default="jailbreak")
    parser.add_argument("--out", default="promptfoo/manual_review.md")
    args = parser.parse_args()

    tests = load_tests(args.config, args.strategy_prefix)
    print(f"Loaded {len(tests)} tests with strategyId starting '{args.strategy_prefix}'", file=sys.stderr)

    lines = [f"# Manual review: {args.strategy_prefix}* prompts against {TARGET_URL}\n"]
    for i, t in enumerate(tests, 1):
        print(f"[{i}/{len(tests)}] {t['pluginId']} / {t['strategyId']}", file=sys.stderr)
        start = time.time()
        result = ask(t["prompt"])
        elapsed = time.time() - start

        lines.append(f"## {i}. {t['pluginId']} — {t['strategyId']}")
        if t["goal"]:
            lines.append(f"**Goal:** {t['goal']}\n")
        lines.append(f"**Prompt:**\n```\n{t['prompt']}\n```\n")
        lines.append(f"**Response ({elapsed:.1f}s, type={result.get('type')}):**")
        reply = result.get("reply") or result.get("error") or result.get("detail") or json.dumps(result)
        lines.append(f"```\n{reply}\n```\n")

    with open(args.out, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {len(tests)} prompt/response pairs to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
