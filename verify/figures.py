#!/usr/bin/env python3
"""Every published figure, recomputed from committed data.

One rule, and the whole point of this file: a number does not go into prose
unless this script prints it. The corpus-size correlation was published as
r = -0.12 and could not be reproduced, because its specification lived in a
session rather than in the repository. Nothing here lives in a session.

  python3 verify/figures.py            # human-readable
  python3 verify/figures.py --json     # machine-readable, for check_claims.py
"""
import argparse, collections, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "paper"))

import corpus_size  # the pinned specification lives there, not here
import dataset      # noqa: F401  (import order: dataset must resolve before use)

DATA = os.path.join(ROOT, "hf", "data")


from dataset import load  # one loader for every figure script


def pct(hit, total):
    return round(hit / total * 100, 1) if total else None


# One definition for the whole repository, and it is score.py's.
scoreable = corpus_size.scoreable


def accuracy_figures(figs):
    answers = load("answers")
    questions = {q["id"]: q for q in load("questions")}

    figs["questions.count"] = len(questions)
    figs["answers.count"] = len(answers)
    figs["models.count"] = len(set(a["model"] for a in answers))

    per_model = collections.defaultdict(lambda: collections.Counter())
    for a in answers:
        m = per_model[a["model"]]
        m["n"] += 1
        m["declined"] += a["declined"]
        if scoreable(a):
            m["scoreable"] += 1
            m["within10"] += a["within_10pct"]
            m["within50"] += a["within_50pct"]
            m["rswn"] += a["right_source_wrong_number"]
            m["cited_correct"] += a["citation_correct"]
        if a["cited_a_source"]:
            m["cited"] += 1

    for model, c in sorted(per_model.items()):
        figs[f"model.{model}.accuracy"] = pct(c["within10"], c["scoreable"])
        figs[f"model.{model}.within50"] = pct(c["within50"], c["scoreable"])
        figs[f"model.{model}.declined"] = pct(c["declined"], c["n"])
        figs[f"model.{model}.cited"] = pct(c["cited"], c["n"])
        # score.py's metric of this name is conditional on having named the right
        # source -- it is not a share of all scoreable answers. Two denominators
        # under one name is how the published range and the registry drifted apart.
        figs[f"model.{model}.right_source_wrong_number"] = pct(c["rswn"], c["cited_correct"])

    tot = sum(per_model.values(), collections.Counter())
    figs["overall.accuracy"] = pct(tot["within10"], tot["scoreable"])
    figs["overall.within50"] = pct(tot["within50"], tot["scoreable"])

    # category and publisher accuracy, pooled over the pinned model pool
    for label, keyfn in (("category", lambda a: a["section"]),
                         ("publisher", lambda a: questions[a["question_id"]]["source_id"])):
        agg = collections.defaultdict(lambda: [0, 0])
        for a in answers:
            if a["model"] not in corpus_size.POOL or not scoreable(a):
                continue
            k = keyfn(a)
            agg[k][1] += 1
            if a["within_10pct"]:
                agg[k][0] += 1
        for k, (hit, total) in sorted(agg.items()):
            figs[f"{label}.{k}.accuracy"] = pct(hit, total)
            figs[f"{label}.{k}.n"] = total


def paired_figures(figs):
    rows = load("paired")
    agg = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        c = agg[(r["model"], r["condition"])]
        c["n"] += 1
        if scoreable(r):
            c["scoreable"] += 1
            c["within10"] += bool(r["within_10pct"])
    for (model, condition), c in sorted(agg.items()):
        figs[f"paired.{model}.{condition}.accuracy"] = pct(c["within10"], c["scoreable"])
        figs[f"paired.{model}.{condition}.n"] = c["n"]


def recommendation_figures(figs):
    rows = load("recommendations")
    figs["aeo.answers.count"] = len(rows)
    figs["aeo.prompts.count"] = len(set(r["prompt"] for r in rows))

    named = collections.Counter()
    first = collections.Counter()
    mentions = 0
    for r in rows:
        for v in set(r["vendors_named"]):
            named[v] += 1
            mentions += 1
        if r["first_vendor_named"]:
            first[r["first_vendor_named"]] += 1
    for vendor, n in named.items():
        figs[f"aeo.vendor.{vendor}.named_in"] = pct(n, len(rows))
        figs[f"aeo.vendor.{vendor}.share_of_voice"] = pct(n, mentions)
        figs[f"aeo.vendor.{vendor}.named_first"] = first.get(vendor, 0)
    figs["aeo.greencalculus.named_in_count"] = sum(
        1 for r in rows if r["names_greencalculus"])

    datasets = collections.Counter()
    for r in rows:
        for d in set(r.get("datasets_cited") or []):
            datasets[d] += 1
    for d, n in datasets.items():
        figs[f"aeo.dataset.{d}.cited_in"] = pct(n, len(rows))


def probe_figures(figs):
    rows = load("direct_probe")
    figs["probe.count"] = len(rows)
    outcomes = collections.Counter(r["outcome"] for r in rows)
    for outcome, n in outcomes.items():
        figs[f"probe.outcome.{outcome}"] = n
    figs["probe.models"] = len(set(r["model"] for r in rows))


def corpus_size_figures(figs):
    answers, questions, sizes = corpus_size.load()
    agg = corpus_size.accuracy_by_publisher(answers, questions, corpus_size.POOL)
    pts = corpus_size.points(agg, sizes, corpus_size.THRESHOLD)
    r = corpus_size.pearson([p[0] for p in pts], [p[1] for p in pts])
    figs["corpus_size.r"] = round(r, 2)
    figs["corpus_size.r_exact"] = round(r, 4)
    figs["corpus_size.n"] = len(pts)
    figs["corpus_size.p"] = round(corpus_size.two_sided_p(r, len(pts)), 2)
    figs["corpus.rows"] = sum(sizes.values())
    figs["corpus.sources"] = len(sizes)
    for source_id, rows in sizes.items():
        figs[f"corpus.source.{source_id}.rows"] = rows


def scorer_output_figures(figs):
    """Every value in the committed outputs of compare.py and paired.py.

    These files are produced by committed scripts over committed raw answers.
    Run `python3 verify/figures.py --check-fresh` to prove they are not stale.
    """
    for name in ("comparison.json", "paired.json", "absolute.json"):
        path = os.path.join(ROOT, "results", name)
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            blob = json.load(fh)
        stem = name.split(".")[0]

        def walk(node, prefix):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f"{prefix}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{prefix}.{i}")
            elif isinstance(node, (int, float)) and not isinstance(node, bool):
                figs[prefix] = node

        walk(blob, f"results.{stem}")


def check_fresh():
    """Re-run the scorers and fail if a committed output has drifted."""
    import filecmp, shutil, tempfile
    stale = []
    for script, out in (("compare.py", "results/comparison.json"),
                        ("paired.py", "results/paired.json")):
        path = os.path.join(ROOT, out)
        if not os.path.exists(path):
            continue
        backup = tempfile.mktemp(suffix=".json")
        shutil.copy(path, backup)
        subprocess.run([sys.executable, script], cwd=ROOT,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not filecmp.cmp(backup, path, shallow=False):
            stale.append(out)
        shutil.copy(backup, path)
    return stale


def licence_figures(figs):
    """The licence audit, from its committed snapshot. See verify/licences.py --
    the audit is a point-in-time statement, so the snapshot is what the guide is
    checked against, and `--drift` reports what has moved in the live registry."""
    import licences
    if not os.path.exists(licences.SNAPSHOT):
        return
    snap = licences.load_snapshot()
    figs.update(licences.figures(snap["sources"])[0])
    figs["licence.snapshot_as_of"] = snap["as_of"]


def build():
    figs = {}
    scorer_output_figures(figs)
    licence_figures(figs)
    accuracy_figures(figs)
    paired_figures(figs)
    recommendation_figures(figs)
    probe_figures(figs)
    corpus_size_figures(figs)
    return figs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check-fresh", action="store_true",
                    help="re-run the scorers and fail if a committed output drifted")
    args = ap.parse_args()
    if args.check_fresh:
        stale = check_fresh()
        if stale:
            print("STALE (committed output no longer matches its script): "
                  + ", ".join(stale))
            return 1
        print("fresh: every committed scorer output reproduces from its script")
        return 0
    figs = build()
    if args.json:
        print(json.dumps(figs, indent=1, sort_keys=True))
        return
    for k, v in sorted(figs.items()):
        print(f"{k:62} {v}")
    print(f"\n{len(figs)} figures from the benchmark dataset, results/ "
          "and the licence snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
