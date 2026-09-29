#!/usr/bin/env python3
"""
CI gate for promptfoo red-team/regression CSV output.

Why this exists: promptfoo's own Pass/Fail column can't be trusted blindly.
The 2026-09-23 run had 44/213 rows where the backend never actually
responded (timeout), and 38 of those were graded as a "safe" pass. This
script fails the build on:
  1. Any genuine graded failure (Pass column starts with "Fail").
  2. Any row where the target never produced a real response — regardless
     of what the Pass column says — so an infra outage can never look like
     a clean run again.

Usage:
    python promptfoo/ci_gate.py results.csv [--max-untested-pct 0]
"""
import argparse
import csv
import sys


UNTESTED_MARKERS = ("was unreachable", "raw-retrieval fallback", "llm_unavailable")


def _response_col(row: dict) -> str:
    # `promptfoo redteam run` exports a "Response" column; plain `promptfoo
    # eval` exports "[<provider label>] {{prompt}}" instead. Detect either.
    if "Response" in row:
        return "Response"
    for key in row:
        if "{{prompt}}" in key or key.startswith("["):
            return key
    raise KeyError(f"Couldn't find a response column in: {list(row.keys())}")


def _prompt_text(row: dict) -> str:
    return row.get("Prompt") or row.get("prompt") or ""


def is_fail(row: dict) -> bool:
    # redteam-run export uses "Pass" ("Pass (1)" / "Fail (0)"); plain eval
    # export uses "Status" ("PASS" / "FAIL").
    value = (row.get("Pass") or row.get("Status") or "").strip().lower()
    return value.startswith("fail")


def is_untested(row: dict) -> bool:
    response = row.get(_response_col(row), "")
    if response.strip() == "":
        return True
    return any(marker in response for marker in UNTESTED_MARKERS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument(
        "--max-untested-pct",
        type=float,
        default=0.0,
        help="Build fails if more than this %% of rows never got a real response.",
    )
    args = parser.parse_args()

    with open(args.csv_path, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("::error::CSV has no rows — did the run actually execute?")
        return 1

    untested = [r for r in rows if is_untested(r)]
    real_fails = [r for r in rows if is_fail(r) and not is_untested(r)]
    false_passes = [r for r in untested if not is_fail(r)]

    total = len(rows)
    untested_pct = len(untested) / total * 100

    print(f"Total: {total}  Untested: {len(untested)} ({untested_pct:.1f}%)  "
          f"Real fails: {len(real_fails)}  False passes hidden in untested: {len(false_passes)}")

    ok = True

    def label(r: dict) -> str:
        tag = "/".join(t for t in (r.get("Plugin"), r.get("Strategy")) if t)
        return f"[{tag}] " if tag else ""

    if real_fails:
        ok = False
        print(f"\n::error::{len(real_fails)} genuine failure(s):")
        for r in real_fails:
            print(f"  - {label(r)}{_prompt_text(r)[:100]!r}")

    if untested_pct > args.max_untested_pct:
        ok = False
        print(f"\n::error::{len(untested)} row(s) ({untested_pct:.1f}%) never reached the "
              f"model — exceeds --max-untested-pct {args.max_untested_pct}. "
              "Investigate backend/timeout issues before trusting this run's pass rate.")
        for r in untested:
            tag = "FALSE PASS" if not is_fail(r) else "flagged fail"
            print(f"  - [{tag}] {label(r)}{_prompt_text(r)[:100]!r}")

    if ok:
        print("\nGate passed.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
