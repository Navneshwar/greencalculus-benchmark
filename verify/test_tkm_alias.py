#!/usr/bin/env python3
"""Issue #18: `tkm` is tonne-kilometres, and freight answers were unscoreable without it.

Freight factors are published per tonne-kilometre and models abbreviate that
`tkm`. `_clean` folded `kilometres` to `km` but knew nothing about `tkm`, so the
numerator parsed and the denominator did not, and four correct freight answers
were dropped as unscoreable rather than scored.

The alias is one entry in `_clean`'s fold list, which makes the risk clear: the
folds are substring rewrites applied in order, so the tests below pin both that
`tkm` resolves AND that it does not damage a plain `km` denominator or a unit
that merely contains those letters.

  python3 verify/test_tkm_alias.py
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import score
import units

TRUTH = "kg CO2e per tonne-km"


def test_tkm_reconciles_against_a_tonne_km_truth():
    for spelling in ("kg CO2e/tkm", "kg CO2e per tkm", "kgCO2e/tkm"):
        got, note = units.reconcile(1.0, spelling, TRUTH)
        assert got == 1.0, (spelling, got, note)


def test_it_works_in_both_directions():
    """A tkm TRUTH must accept a spelled-out answer, not only the reverse."""
    got, _ = units.reconcile(0.1, "kg CO2e per tonne km", "kg CO2e/tkm")
    assert got == 0.1, got


def test_the_existing_spellings_still_work():
    for spelling in ("kg CO2e/t-km", "kg CO2e per tonne-km", "kg CO2e per tonne km"):
        got, _ = units.reconcile(1.0, spelling, TRUTH)
        assert got == 1.0, (spelling, got)


def test_scale_is_carried_through():
    got, _ = units.reconcile(1000.0, "g CO2e per tkm", TRUTH)
    assert abs(got - 1.0) < 1e-9, got


def test_a_plain_km_denominator_is_a_known_open_hole():
    """`per km` DOES still reconcile with a tonne-km truth. That is not this fix.

    Both parse to den_dim "length" (the denominator scan finds `km` in LENGTH
    before it reaches `tonne` in MASS), so reconcile compares equal dimensions
    and never looks at the token sets. It is wrong -- 0.17 kg/km and 0.107
    kg/tonne-km are different quantities -- and it predates this alias: see the
    denominator-basis issue. Zero answers in the committed corpus are affected
    (no tonne-km truth received a per-km answer), so this pins the CURRENT
    behaviour rather than asserting the fix, and will need updating when the
    basis guard lands.
    """
    got, _ = units.reconcile(0.17, "kg CO2e per km", TRUTH)
    assert got == 0.17, (
        "per km no longer reconciles with a tonne-km truth -- the basis guard has "
        "landed, so update this test to assert the refusal")


def test_a_unit_that_merely_contains_the_letters_is_untouched():
    """`_clean` folds are substring rewrites, so a word boundary matters."""
    assert units.parse_unit("kg CO2e per atkm") != units.parse_unit("kg CO2e per tonne km")


def test_the_four_corpus_answers_now_score():
    """The freight answers this alias exists for, end to end."""
    import json
    import compare
    uniq = compare.question_order()
    qmap = {q["id"]: q for q in uniq}
    legacy = os.path.join(ROOT, "results", "runs_opus5_full.json")
    if not os.path.exists(legacy):
        print("skip test_the_four_corpus_answers_now_score: no committed Claude run")
        return
    answers = {r["id"]: r["answer"] for r in json.load(open(legacy))}
    for qid in ("freight.air.tonne_km", "freight.rail.tonne_km",
                "freight.road_hgv.tonne_km", "freight_detailed.rail.eu.diesel.cars"):
        q = qmap.get(qid)
        if q is None or qid not in answers:
            continue
        got, unit, _ = score.best_value(answers[qid], q["truth"]["unit"])
        assert got is not None, f"{qid} is still unscoreable (unit {unit!r})"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all tkm-alias tests passed")
