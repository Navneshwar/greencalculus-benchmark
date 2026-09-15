#!/usr/bin/env python3
"""Read the search arm. Four questions, kept apart because they have different fixes.

  1. NAMED        — are we in the answer text? The headline.
  2. IN SOURCES    — did the model READ us but not cite us? That is a writing
                     problem, fixable in a week. Not found at all is a discovery
                     problem, fixable in months. Pooling them hides which one we have.
  3. DOMAIN MAP    — which pages does a model actually read to answer these
                     questions? Reconnaissance: it says where being present is worth
                     paying for, and it is free because cited_urls is already recorded.
  4. DID IT SEARCH — a provider silently ignoring the tool returns answers
                     indistinguishable from the baseline and would report "no
                     change" when it had simply not run.

Brand detection uses hits() from aeo/score.py — the SAME function behind every
published baseline figure. A second implementation here would let the two arms
drift and the comparison would measure the scorer, not the models.
"""
import json, collections, sys, re
from pathlib import Path
from score import hits
from brands import VENDORS, DATASETS

ROOT = Path(__file__).parent
# Our own assets. Whether the RESEARCH is findable is a different question from
# whether the PRODUCT is, and they have different fixes, so they are counted apart.
ASSETS = {
    "greencalculus.com":  r"greencalculus\.com",
    "benchmark repo":     r"github\.com/greencalculus|greencalculus-benchmark",
    "Zenodo DOI":         r"zenodo\.org|10\.5281",
    "HuggingFace":        r"huggingface\.co/datasets/greencalculus",
    "PyPI / LangChain":   r"pypi\.org/project/(greencalculus|langchain-greencalculus)",
    "npm / MCP":          r"npmjs\.com/package/greencalculus-mcp|mcp\.greencalculus\.com",
    "MCP registry":       r"registry\.modelcontextprotocol\.io",
    "Glama":              r"glama\.ai/mcp/servers/(greencalculus|jeremiahsay)",
}


def load(fname):
    seen, rows = set(), []
    fp = ROOT / fname
    if not fp.exists():
        return rows
    for l in fp.open():
        if not l.strip():
            continue
        r = json.loads(l)
        k = (r["model"], r["prompt"])
        if k in seen:
            continue
        seen.add(k); rows.append(r)
    return rows


# Gemini does not return readable URLs. Its groundingChunks carry a
# vertexaisearch.cloud.google.com redirect plus the real domain in `.title`, and
# run_search.py appends both. Accepting ONLY http:// forms silently blinded the
# domain map for both Gemini models — 2 of 5 — and left "vertexaisearch" as the
# top result, which is not a source anyone can act on.
REDIRECTORS = {"vertexaisearch.cloud.google.com"}


def domain(u):
    u = (u or "").strip()
    m = re.match(r"https?://([^/]+)", u)
    if m:
        d = m.group(1).lower().removeprefix("www.")
        return None if d in REDIRECTORS else d
    # Gemini's title form: a bare domain such as "climatiq.io"
    if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", u.lower()):
        return u.lower().removeprefix("www.")
    return None


def main():
    rows = load(sys.argv[1] if len(sys.argv) > 1 else "search_answers.jsonl")
    if not rows:
        sys.exit("no rows yet")
    models = sorted({r["model"] for r in rows})
    print(f"=== SEARCH ARM — {len(rows)} answers, {len(models)} models ===\n")

    # 4. did it search
    print("DID THE MODEL ACTUALLY SEARCH")
    for m in models:
        sub = [r for r in rows if r["model"] == m]
        ns = [r.get("n_searches", 0) for r in sub]
        noser = sum(1 for r in sub if not r.get("searched"))
        print(f"  {m:24} {len(sub):>3} answers  {sum(ns)/max(len(ns),1):.1f} searches avg"
              f"   {noser} did not search" + ("   <-- SUSPECT" if noser > len(sub)//3 else ""))

    # 1 + 2 us
    print("\nGREENCALCULUS")
    tot_named = tot_src = 0
    for m in models:
        sub = [r for r in rows if r["model"] == m]
        named = sum(1 for r in sub if r.get("greencalculus_in_text"))
        insrc = sum(1 for r in sub if r.get("greencalculus_in_sources"))
        tot_named += named; tot_src += insrc
        print(f"  {m:24} named {named:>2}/{len(sub):<3}  in sources {insrc:>2}/{len(sub)}")
    print(f"  {'TOTAL':24} named {tot_named:>2}/{len(rows):<3}  in sources {tot_src:>2}/{len(rows)}")
    read_not_cited = sum(1 for r in rows
                         if r.get("greencalculus_in_sources") and not r.get("greencalculus_in_text"))
    print(f"\n  READ BUT NOT CITED: {read_not_cited}"
          f"   <- a writing problem, not a discovery problem" if read_not_cited else
          f"\n  READ BUT NOT CITED: 0")

    # by intent
    print("\n  by intent (named / n):")
    for intent in sorted({r["intent"] for r in rows}):
        sub = [r for r in rows if r["intent"] == intent]
        print(f"    {intent:12} {sum(1 for r in sub if r.get('greencalculus_in_text')):>2}/{len(sub)}")

    # competitors, same scorer as the published baseline
    print("\nWHO GETS NAMED (hits() — the published scorer)")
    c = collections.Counter()
    for r in rows:
        for b in set(hits(r["answer"])):
            c[b] += 1
    for b, n in c.most_common(18):
        tag = "dataset" if b in DATASETS else ("vendor" if b in VENDORS else "")
        print(f"  {b:26} {n:>3}/{len(rows)}  {100*n/len(rows):>5.1f}%  {tag}")

    # 3. the domain map
    print("\nWHAT THE MODELS ACTUALLY READ (top 30 domains)")
    dom = collections.Counter()
    answers_with = collections.Counter()
    for r in rows:
        ds = {d for d in (domain(u) for u in r.get("cited_urls") or []) if d}
        for d in ds:
            dom[d] += 1; answers_with[d] += 1
    for d, n in dom.most_common(30):
        print(f"  {d:44} {n:>3} answers  {100*n/len(rows):>5.1f}%")

    # our assets
    print("\nARE OUR OWN ASSETS BEING READ")
    for name, pat in ASSETS.items():
        rx = re.compile(pat, re.I)
        n = sum(1 for r in rows if any(rx.search(u) for u in (r.get("cited_urls") or []))
                or rx.search(r["answer"]))
        print(f"  {name:22} {n:>3}/{len(rows)}")


if __name__ == "__main__":
    main()
