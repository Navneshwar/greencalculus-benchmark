#!/usr/bin/env python3
"""Issue #35: a rate per square metre is not a rate per nothing.

`kWh per m2 per year` and `kWh/yr` are different quantities. The scorer was
reconciling them, so five Claude answers giving a whole-building annual total
were scored against a per-square-metre truth -- one of them 20,500 against 102.1.

The cause was that area had no dimension table. A per-m2 denominator degraded to
the catch-all `other:m2` and was compared as a string, which put it in front of
the containment rule, and {year} is a subset of {m2, year}. Giving area a table
is the whole fix: the existing den_dim comparison then refuses the pair.

Two things these tests deliberately pin, because the obvious fixes break them:

  - A guard keyed on a hand-written list of "dimension words" would work, and
    would be a second list to maintain that fails silently and open. The table
    is the authority instead.
  - A guard comparing every recognised unit in the denominator refuses
    `kgCO2e/km T&D loss` against `kg CO2e per km`, because `T&D` tokenises to a
    bare `t` and `t` is tonnes. Two correct answers died that way in a draft.

  python3 verify/test_denominator_basis.py
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import score
import units

M2 = "kWh per m2 per year"


def test_a_bare_annual_rate_is_not_a_per_m2_intensity():
    got, why = units.reconcile(20500, "kWh/yr", M2)
    assert got is None, f"kWh/yr reconciled with {M2!r} as {got}"
    assert why and "area" in why, why


def test_a_qualifier_still_reconciles():
    """`per dwelling per year` vs `per yr` is the same basis stated at length."""
    got, _ = units.reconcile(12500, "kWh/yr", "kWh per dwelling per year")
    assert got == 12500, got


def test_two_different_qualified_bases_stay_refused():
    got, _ = units.reconcile(11531, "kWh per dwelling per year", M2)
    assert got is None, got


def test_area_units_convert_among_themselves():
    """Area was previously a set of unrelated `other:` strings."""
    got, _ = units.reconcile(1.0, "kg CO2e per hectare", "kg CO2e per m2")
    assert abs(got - 1e-4) < 1e-12, got
    got, _ = units.reconcile(1.0, "kg CO2e per m2", "kg CO2e per hectare")
    assert abs(got - 1e4) < 1e-6, got
    assert units.reconcile(1.0, "kg CO2e per sqm", "kg CO2e per m2")[0] == 1.0


def test_prose_after_the_unit_does_not_invent_a_dimension():
    """`T&D` cleans to a bare `t`, and `t` is tonnes. These must still score."""
    for unit in ("kgCO2e/km T&D loss for an MPV PHEV",
                 "kgCO2e/kWh for UK electricity T&D losses"):
        truth = "kg CO2e per km" if "/km" in unit else "kg CO2e per kWh"
        got, _ = units.reconcile(0.0017, unit, truth)
        assert got == 0.0017, (unit, got)


def test_an_abbreviated_tonne_still_matches_a_spelled_one():
    got, _ = units.reconcile(0.79, "kg CH4/t EO", "kg CH4 per tonne ethylene oxide")
    assert got == 0.79, got


def test_the_module_s_original_design_case_is_untouched():
    v, note = units.reconcile(63, "kgCO2/GJ", "0.0172 tonne C per GJ".split(maxsplit=1)[1])
    assert v is not None and note, (v, note)
    assert abs(v - 0.0171818) < 1e-6, v


def test_a_bare_per_km_against_a_tonne_km_truth_is_a_KNOWN_OPEN_HOLE():
    """Still reconciles. Same class as this fix, different route -- see issue #35.

    Both sides report den_dim "length": the denominator scan stops at `km` before
    reaching `tonne`, so the dimension comparison sees a match. Deciding it safely
    needs the unit expression separated from trailing prose, which the `T&D` case
    above shows is not simply "every recognised token". No answer in the corpus is
    affected. Pinned so the day it changes, this test says so.
    """
    got, _ = units.reconcile(0.17, "kg CO2e per km", "kg CO2e per tonne-km")
    assert got == 0.17, (
        "per km no longer reconciles with a tonne-km truth -- if that was "
        "deliberate, update this test and issue #35")


def test_the_ten_corpus_answers_are_now_unscoreable():
    import json
    import compare
    uniq = compare.question_order()
    qmap = {q["id"]: q for q in uniq}
    legacy = os.path.join(ROOT, "results", "runs_opus5_full.json")
    if not os.path.exists(legacy):
        print("skip test_the_ten_corpus_answers_are_now_unscoreable: no committed run")
        return
    answers = {r["id"]: r["answer"] for r in json.load(open(legacy))}
    hit = 0
    for qid, q in qmap.items():
        if not qid.startswith("building_energy.gbr.floorband."):
            continue
        if q["truth"]["unit"] != M2 or qid not in answers:
            continue
        got, _, _ = score.best_value(answers[qid], M2)
        assert got is None, f"{qid} still scores {got} against a per-m2 truth"
        hit += 1
    assert hit == 5, f"expected 5 Claude floorband answers, checked {hit}"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all denominator-basis tests passed")
