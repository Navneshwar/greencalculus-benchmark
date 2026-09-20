#!/usr/bin/env python3
"""Accuracy over ALL 467 questions, not just the scoreable ones.

`compare.py` reports within-10% as a share of what could be scored, which is the
right denominator for "when it answers, how often is it right". It is the wrong
denominator for "how often do I get a usable answer", because a model that
declines 313 questions looks excellent on the few it attempts. This scores every
question: a refusal counts as not correct.

results/absolute.json is the `pct_of_all` column in README.md and the study
pages. It was a committed file with no script behind it until now, which meant a
scorer change could move it silently -- verify/figures.py --check-fresh reruns it
with the others.

  python3 absolute.py
"""
import json
from pathlib import Path

from compare import load_run, question_order
from score import score_one

ROOT = Path(__file__).parent


def main():
    uniq = question_order()
    qmap = {q["id"]: q for q in uniq}

    runs = {}
    for d in sorted(ROOT.glob("results/raw_*")):
        runs[d.name.replace("raw_", "")] = load_run(d, uniq)
    legacy = ROOT / "results" / "runs_opus5_full.json"
    if legacy.exists():
        runs["claude-opus-5"] = {r["id"]: r["answer"] for r in json.load(open(legacy))}

    rows = []
    # Insertion order, not sorted: results/raw_* first and the legacy Claude run
    # last, exactly as compare.py builds `runs`. Sorting here would rewrite every
    # row of the committed file for no reason and bury the real change in a diff.
    for model, answers in runs.items():
        scored = [score_one(qmap[i], a) for i, a in answers.items() if i in qmap]
        answered = sum(1 for s in scored if s["answered"])
        correct = sum(1 for s in scored if s["within_10pct"])
        rows.append({
            "model": model,
            "answered": answered,
            "refused": len(scored) - answered,
            "correct": correct,
            "pct_of_all": round(100 * correct / len(scored), 1) if scored else 0.0,
        })

    hdr = f"{'model':26} {'answered':>9} {'refused':>8} {'correct':>8} {'% of all 467':>13}"
    print(hdr); print("-" * len(hdr))
    for r in sorted(rows, key=lambda r: -r["pct_of_all"]):
        print(f"{r['model']:26} {r['answered']:>9} {r['refused']:>8} "
              f"{r['correct']:>8} {r['pct_of_all']:>12.1f}%")
    json.dump(rows, open(ROOT / "results" / "absolute.json", "w"), indent=1)
    print("\nwritten: results/absolute.json")


if __name__ == "__main__":
    main()
