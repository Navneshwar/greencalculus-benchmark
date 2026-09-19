# Contributing

This file overrides the [organisation default](https://github.com/greencalculus/.github/blob/main/CONTRIBUTING.md).

This repository is a measuring instrument. Most of the rules below exist because an instrument that changes shape stops measuring anything.

Four issues are labelled `good first issue`; each names the files to change, a command to verify the change, and an explicit scope.

## Setup

Python 3, standard library. Scoring, verification and the panel all run offline against committed data:

```bash
git clone https://github.com/greencalculus/greencalculus-benchmark
cd greencalculus-benchmark

python3 verify/check_claims.py --offline   # every published number reproduces
python3 verify/figures.py --check-fresh    # committed scorer output is current
python3 aeo/trend.py                       # the search-arm panel
```

API keys are needed **only** to re-run models. Everything else — the scorers, the gates, the 467 questions and every raw answer — is in the repo.

## The rules that are not negotiable

**Never edit the prompts.** `aeo/prompts.py` and `questions.json` are the instrument. A changed instrument measures nothing, and every published figure becomes incomparable to every earlier one. If a question is wrong, open an issue rather than fixing it in place — the fix may be a new version of the set, not an edit to this one.

**UNSCOREABLE is a deliberate outcome, not a bug.** When a model's unit cannot be mechanically reconciled with the corpus unit, the answer leaves the denominator rather than counting as wrong. Closing those gaps is welcome ([#18](https://github.com/greencalculus/greencalculus-benchmark/issues/18), [#23](https://github.com/greencalculus/greencalculus-benchmark/issues/23)); reconciling two units that are not the same quantity in order to make a number look better is not.

**Report both numbers.** Any change to the scorer must say what it did to coverage *and* to the headline accuracy. The claim in `FINDINGS.md` is that the unscoreable pile is not hiding a bias, and the evidence for that is fixes which move coverage while the headline stays put. A change that moves coverage by four answers and the headline by five points is telling us something important — but only if you report it.

**Do not try to reconstruct the held-out set.** 136 questions are deliberately unpublished, with their shape and hash pre-registered in `holdout-manifest.json`. A CI guard fails the build if the answers are ever committed. See `CANARY.md`.

**No published number without a committed script behind it.** `verify/check_claims.py` enforces this against the live pages, the preprint and the dataset card. A number that cannot be reproduced must go in `verify/allowlist.json` with a written reason — "it is correct" is not a reason. If it is correct and derivable, make it a figure in `verify/figures.py` instead.

## The search arm is a panel, not a before-and-after

`aeo/` runs on a fortnightly cadence. Runs live one file per date under `aeo/runs/` and are **never rewritten**; `aeo/trend.py` differences our reach against control brands measured by the same prompts in the same call.

Two things to know before touching it:

- **Resume is scoped to a single run.** It used to be seeded from one shared file, which would have made every later run exit `0 calls, $0.00` while reporting September's numbers as October's. Do not widen it back.
- **The differential is withheld** when a run's model set changed or a provider stopped searching. A warning printed above a quotable number is how the wrong number gets quoted.

Adding a model costs roughly $3–5 of your own API credit for 25 prompts. `GC_MAX_SPEND` stops a run that overshoots.

## Before you open a PR

```bash
python3 verify/check_claims.py --offline
python3 verify/figures.py --check-fresh
```

CI runs those plus the licence drift check and the held-out guard.

## Commit messages

Say what changed and why it was wrong before. The subject is a sentence, not a label.

## Questions

Comment on the issue you want to work on — including to say you are stuck, or that something in the instructions does not reproduce. That is useful information, not a silly question.

Security issues go to **security@greencalculus.com**, not to an issue.

## Related

[gwp-basis-check](https://github.com/greencalculus/gwp-basis-check) — a linter for the neighbouring problem: whether the software people already use cites the right IPCC report for a warming potential.
