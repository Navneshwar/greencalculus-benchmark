#!/usr/bin/env python3
"""The search arm as a PANEL: every run, side by side, us against the controls.

Why this exists rather than a single before/after. The plan of record used to be
one baseline on 14 September and one re-run afterwards, with a publishing freeze
in between to keep the two comparable. That design has no control group, cannot
separate our launch from a model-version change, and — at 25 prompts, where the
repo's own limits section says ONE PROMPT IS 4 POINTS OF REACH — cannot resolve
anything short of a doubling. It also costs $14-23 to run, which is far too cheap
to be worth protecting with a freeze on shipping.

So: run it on a cadence, never rewrite a run, and read the DIFFERENCE between our
line and the control lines. Climatiq, ecoinvent, EXIOBASE, DEFRA and EPA are
measured by the same prompts in the same call, so anything that moves all six at
once — a new model version, a search-backend change, a seasonal shift in what the
web says — moves the controls too and cancels. That is the whole argument for
the control arm, and it was free: those brands were already in brands.py.

What it cannot do: n stays small. A differential of one prompt is noise. The
noise floor is printed every time so nobody has to remember it.

  python3 aeo/trend.py              # the panel
  python3 aeo/trend.py --csv        # machine-readable, one row per run x brand
"""
import argparse, collections, csv, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from score import hits

HERE = Path(__file__).parent
BASELINE = HERE / "search_answers.jsonl"
BASELINE_DATE = "2026-09-14"
RUNS = HERE / "runs"
TIMELINE = HERE / "timeline.tsv"

US = "GreenCalculus"
# The control arm. Named here rather than "every other brand" on purpose: these
# five are the ones with enough reach to carry a signal. A vendor sitting at 2%
# is noise in both directions and averaging it in would only widen the band.
CONTROLS = ["Climatiq", "ecoinvent", "EXIOBASE", "_DEFRA", "_EPA"]


def load_run(path, date):
    """De-duplicate within a run, never across. Keeps the LAST answer for a pair:
    if a pair was retried inside one run, the retry is the one that finished."""
    rows = {}
    for line in path.open():
        if line.strip():
            r = json.loads(line)
            rows[(r["model"], r["prompt"])] = r
    return {"date": date, "path": path, "rows": list(rows.values())}


def discover():
    runs = []
    if BASELINE.exists():
        runs.append(load_run(BASELINE, BASELINE_DATE))
    for p in sorted(RUNS.glob("search-*.jsonl")):
        m = re.fullmatch(r"search-(\d{4}-\d{2}-\d{2})\.jsonl", p.name)
        if not m:
            print(f"  ! skipping {p.name}: not search-YYYY-MM-DD.jsonl", file=sys.stderr)
            continue
        runs.append(load_run(p, m.group(1)))
    return sorted(runs, key=lambda r: r["date"])


def reach(rows):
    """Share of answers naming each brand, via the published scorer."""
    c = collections.Counter()
    for r in rows:
        for b in set(hits(r["answer"])):
            c[b] += 1
    n = len(rows) or 1
    return {b: 100 * v / n for b, v in c.items()}


def annotations():
    if not TIMELINE.exists():
        return []
    out = []
    with TIMELINE.open() as fh:
        for row in csv.DictReader((l for l in fh if not l.startswith("#")), delimiter="\t"):
            if row.get("date"):
                out.append(row)
    return sorted(out, key=lambda r: r["date"])


def fmt(x, width=6):
    return f"{x:>{width}.1f}"


def differential(runs, reaches, dates, floor, n_prompts):
    """Our movement, minus the movement of brands asked the same questions by the
    same models in the same call. Anything that shifts the whole web — a new model
    version, a search-backend change — shifts the controls too and cancels here."""
    first, last = reaches[0], reaches[-1]
    us_d = last.get(US, 0.0) - first.get(US, 0.0)
    ctl_d = sorted(last.get(b, 0.0) - first.get(b, 0.0) for b in CONTROLS)
    mid = (ctl_d[len(ctl_d) // 2] if len(ctl_d) % 2
           else (ctl_d[len(ctl_d)//2 - 1] + ctl_d[len(ctl_d)//2]) / 2)

    print(f"\nDIFFERENCE-IN-DIFFERENCES — {dates[0]} to {dates[-1]}")
    print(f"  GreenCalculus            {us_d:+6.1f} points")
    print(f"  controls (median)        {mid:+6.1f} points   "
          f"[{ctl_d[0]:+.1f} .. {ctl_d[-1]:+.1f}]")
    print(f"  differential             {us_d - mid:+6.1f} points")
    print("  -> " + ("below the noise floor — read it as no change"
                     if abs(us_d - mid) < floor else
                     f"above the one-prompt floor of {floor:.1f} — worth looking at, "
                     f"still not significant at n={n_prompts}"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", action="store_true", help="one row per run x brand")
    args = ap.parse_args()

    runs = discover()
    if not runs:
        sys.exit("no runs found")

    if args.csv:
        w = csv.writer(sys.stdout)
        w.writerow(["run", "n_answers", "brand", "reach_pct", "named"])
        for run in runs:
            rr, n = reach(run["rows"]), len(run["rows"])
            for b in [US] + CONTROLS:
                w.writerow([run["date"], n, b, f"{rr.get(b, 0.0):.2f}",
                            round(rr.get(b, 0.0) * n / 100)])
        return

    print(f"=== SEARCH ARM PANEL — {len(runs)} run(s) ===\n")

    # --- comparability guards, before any number is read ------------------
    # A reach percentage is only comparable run to run if the instrument was the
    # same. Two things break that silently: a model dropping out (the denominator
    # changes and every brand appears to move) and a provider ignoring the search
    # tool (the row looks like an answer but is the no-web arm wearing its badge).
    base_models = None
    problems = []
    tainted = {}          # run date -> why its numbers are not comparable
    for run in runs:
        models = sorted({r["model"] for r in run["rows"]})
        if base_models is None:
            base_models = models
        elif models != base_models:
            why = (f"model set differs from {runs[0]['date']} "
                   f"(+{sorted(set(models) - set(base_models))} "
                   f"-{sorted(set(base_models) - set(models))})")
            problems.append(f"{run['date']}: {why} — reach is NOT comparable")
            tainted[run["date"]] = why
        for m in models:
            sub = [r for r in run["rows"] if r["model"] == m]
            nosearch = sum(1 for r in sub if not r.get("searched"))
            if nosearch > len(sub) // 3:
                why = f"{m} did not search on {nosearch}/{len(sub)}"
                problems.append(f"{run['date']}: {why} — that arm may be the no-web "
                                f"baseline in disguise")
                tainted.setdefault(run["date"], why)
    if problems:
        print("COMPARABILITY WARNINGS")
        for p in problems:
            print(f"  ! {p}")
        print()

    # --- the panel --------------------------------------------------------
    n_prompts = len({r["prompt"] for r in runs[0]["rows"]})
    n_models = len(base_models)
    floor = 100.0 / n_prompts if n_prompts else 0.0
    dates = [r["date"] for r in runs]
    reaches = [reach(r["rows"]) for r in runs]

    head = "  " + f"{'brand':<26}" + "".join(f"{d[5:]:>9}" for d in dates)
    print("REACH — share of answers naming the brand (%)")
    print(head)
    print("  " + "-" * (26 + 9 * len(dates)))
    for b in [US] + CONTROLS:
        label = b.lstrip("_") + (" (dataset)" if b.startswith("_") else "")
        line = "  " + f"{label:<26}" + "".join(fmt(rr.get(b, 0.0), 9) for rr in reaches)
        print(line + ("   <- us" if b == US else ""))

    for run, rr in zip(runs, reaches):
        n = len(run["rows"])
        print(f"\n  {run['date']}: {n} answers, {len({r['model'] for r in run['rows']})} models"
              f"   ({run['path'].name})")

    print(f"\n  Noise floor: one prompt = {floor:.1f} points of reach "
          f"({n_prompts} prompts x {n_models} models). Anything smaller is nothing.")

    if len(runs) < 2:
        print("\n  One run so far — nothing to difference yet. The panel needs a second\n"
              "  point before any of this means anything.")
        return

    # --- the differential -------------------------------------------------
    # This is the number the one-shot design could not produce. Our movement is
    # only interesting to the extent it differs from the movement of brands that
    # were asked the same questions by the same models in the same call.
    # A warning printed above a quotable number is how the wrong number gets
    # quoted. If either endpoint is not comparable, there is no differential to
    # report — say so instead of printing one with a caveat attached.
    bad = [d for d in (dates[0], dates[-1]) if d in tainted]
    if bad:
        print("\nDIFFERENCE-IN-DIFFERENCES — withheld")
        for d in bad:
            print(f"  {d} is not comparable: {tainted[d]}")
        print("  Re-run the affected models onto that run's file, or difference two\n"
              "  clean runs, before quoting any movement.")
    else:
        differential(runs, reaches, dates, floor, n_prompts)

    # --- leading indicator ------------------------------------------------
    # in_sources moves before in_text does: the crawler reaches a new page weeks
    # before the model's prose starts crediting it. If this is climbing while
    # NAMED is flat, the problem is the writing, not the discovery.
    print("\nREAD vs CITED")
    for run in runs:
        rows = run["rows"]
        n = len(rows) or 1
        named = sum(1 for r in rows if r.get("greencalculus_in_text"))
        insrc = sum(1 for r in rows if r.get("greencalculus_in_sources"))
        rnc = sum(1 for r in rows if r.get("greencalculus_in_sources")
                  and not r.get("greencalculus_in_text"))
        print(f"  {run['date']}   named {named:>3}/{n:<4} in sources {insrc:>3}/{n:<4} "
              f"read-but-not-cited {rnc:>3}")

    # --- what shipped between the runs ------------------------------------
    anns = annotations()
    if anns:
        print("\nWHAT SHIPPED BETWEEN THE RUNS")
        for i in range(len(dates) - 1):
            lo, hi = dates[i], dates[i + 1]
            between = [a for a in anns if lo < a["date"] <= hi]
            print(f"  {lo} -> {hi}")
            if not between:
                print("      (nothing logged — if that is wrong, timeline.tsv is stale)")
            for a in between:
                flag = "" if a.get("status") == "shipped" else f"  [{a.get('status')}]"
                print(f"      {a['date']}  {a.get('surface',''):<12} {a.get('what','')}{flag}")
        future = [a for a in anns if a["date"] > dates[-1]]
        if future:
            print(f"  after {dates[-1]} (not yet measured)")
            for a in future:
                print(f"      {a['date']}  {a.get('surface',''):<12} {a.get('what','')}"
                      f"  [{a.get('status','')}]")


if __name__ == "__main__":
    main()
