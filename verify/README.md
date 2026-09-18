# The claims gate

One rule:

> **A number does not go into published prose unless a committed script prints it.**

## Why this exists

On 10 September 2026 the guide *Where AI Is Reliable on Emission Factors*
published the corpus-size correlation as **r = −0.12**, described as
"essentially no relationship". It was wrong — the value is −0.28 — and, worse,
it was *unfalsifiable*: the specification behind it (which models, which answers
count, which threshold) lived in a working session and was never written down.
Nobody could check it, including us.

The correction then hit the same fault a second time. The first attempt
published −0.27, because "scoreable" was reconstructed from the data's flags
instead of read from `score.py`. The reconstruction is close but not identical,
and the gap moves the second decimal. This gate caught that within the hour.

The lesson is not "be more careful". It is that a figure whose recipe is not in
the repository cannot be checked by anyone, so it will eventually be wrong and
nobody will notice.

## The two scripts

| Script | What it does |
|---|---|
| `figures.py` | Recomputes every published figure from `hf/data/`, `results/` and `paper/sources.tsv`. `--check-fresh` re-runs the scorers and fails if a committed output has drifted from the script that made it. |
| `check_claims.py` | Extracts every numeric claim from the four study pages, the preprint, the dataset card and `FINDINGS.md`, and fails if any of them is neither reproduced by `figures.py` nor justified in `allowlist.json`. |

```sh
python3 verify/figures.py                 # all figures
python3 verify/figures.py --check-fresh   # committed outputs are not stale
python3 verify/check_claims.py            # includes the live pages over HTTP
python3 verify/check_claims.py --offline  # local files only
```

## Before publishing any number, anywhere

1. Make the script that produces it, or add it to `figures.py`.
2. Run `python3 verify/check_claims.py`. It must pass.
3. Only then write the sentence.

If a figure genuinely cannot be derived — a hand adjudication, a figure quoted
from someone else's pricing page, a historical value from an earlier scorer
version — it goes in `allowlist.json` **with a written reason**. "It is correct"
is not a reason. Every allowlist entry is a surface we cannot verify
automatically, which is a debt rather than a resolution.

## The licence audit — closed 11 September 2026

This was listed as "not reproducible from this repository". That was wrong, and
worth recording as its own lesson: **the debt was smaller than the note claimed,
and nobody had checked.** The audit does not live in the `gc-sources` store. It
reproduces from `gc_mb_canonical_sources_registry()` joined to corpus row counts,
which is what `verify/licences.py` now does. 137 sources, 17,074 rows and the 92%
republishable row share reproduce exactly.

A licence audit is a **point-in-time** statement, so it is snapshotted rather than
recomputed live: `licence_snapshot.json` carries the date it describes, the guide
is checked against the snapshot, and `--drift` compares the snapshot to the live
registry. Drift is not a failure — it is the signal to re-date the guide, or to
record why the published date still stands.

Both items this opened were closed the same day, by re-dating the guide:

- **Drift.** Two sources had their verdict changed after publication — one is
  `LOVEHAGEN_2023_EMBODIED_USER_DEVICES`, whose author granted display permission
  on 2026-09-09 in reply to a request from us. Republishable moved 75 / 15,748 →
  **77 / 15,762**, restricted 62 / 1,326 → **60 / 1,312**. The 92% row share was
  unchanged. The guide now states the current figures.
- **The family boundary.** The published table put 13 sources under "All rights
  reserved"; the committed rule in `licences.py` puts 17, moving four
  `© … fair-use citation` sources (IPCC AR4, ICCT, NVIDIA, AWS) out of "Bespoke".
  Eleven of the thirteen families were already exact. The guide now says **39%**
  of sources have no standard licence instrument, not 42% — which makes its point
  more sharply, not less. The assignment was a presentational judgement that was
  never a stored field; `FAMILIES` is now that rule, in one place, versioned.

The guide also gained a dated paragraph explaining that licence positions are
point-in-time and why they move. That is the durable half: a reader who finds a
different number in a cached copy now has an explanation rather than a
contradiction, and the weekly drift job means the next re-licence surfaces in
days.

## Known debt

- **`FINDINGS.md` spans several scorer versions.** Its historical figures are
  allowlisted individually and marked as historical.

## For the search-enabled runs

The search arm is a **panel on a fortnightly cadence**, not a baseline and a
single re-run. An earlier draft of this file named 6 October and the launch plan
named 13 October; neither date survives, because the design that needed one
specific re-run date has been replaced. `aeo/trend.py` reads every run and
differences ours against the control brands measured in the same call.

The publishing rule is unchanged and still binds: the scorer output gets
committed, `figures.py` gains the new family, and no number from any run appears
in a post, a guide or a thread until `check_claims.py` passes with the new page
in its surface list.
