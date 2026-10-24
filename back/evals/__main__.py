"""Run the LLM evals against the real OpenAI API.

Run:  OPENAI_API_KEY=... uv run python -m evals [--repeat 3] [--only id ...] [--out report.json]
Costs real tokens and the model is not deterministic: kept out of pytest and CI.
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from evals.harness import load_cases, run_case


def main() -> None:
    p = argparse.ArgumentParser(prog="evals")
    p.add_argument("--repeat", type=int, default=1, help="runs per case (pass rate)")
    p.add_argument("--only", nargs="*", help="case ids to run")
    p.add_argument("--out", help="write full transcripts as JSON")
    args = p.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Falta OPENAI_API_KEY: las evals llaman al modelo real.")

    cases = [c for c in load_cases() if not args.only or c["id"] in args.only]
    jobs = [c for c in cases for _ in range(args.repeat)]
    with ThreadPoolExecutor(max_workers=8) as pool:  # cases are independent
        results = list(pool.map(run_case, jobs))

    passed_total = 0
    for case in cases:
        runs = [r for r in results if r.id == case["id"]]
        ok = sum(r.passed for r in runs)
        passed_total += ok
        print(f"{'✓' if ok == len(runs) else '✗'} {ok}/{len(runs)}  {case['id']:<26} {case['title']}")
        for r in runs:
            for f in ([r.error] if r.error else r.failures):
                print(f"      · {f}")
    print(f"\n{passed_total}/{len(results)} ejecuciones correctas")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2, default=str)
    raise SystemExit(0 if passed_total == len(results) else 1)


if __name__ == "__main__":
    main()
