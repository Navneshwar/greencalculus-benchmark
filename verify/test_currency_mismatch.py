#!/usr/bin/env python3
"""Two different currencies must never reconcile.

Every entry in units.CURRENCY carries a scale of 1.0 because the benchmark holds
no exchange rates -- an FX rate is a price on a date, not a unit conversion. That
made EUR and USD interchangeable: a model answering "85.00 EUR per tonne CO2e"
scored 85 against a USD/tCO2e truth, wrong by whatever the rate happened to be,
and counted as a confident answer rather than an unscoreable one.

Three answers in the committed corpus were being scored this way, all
gemini-3.6-flash, all in carbon_pricing.*.

  python3 verify/test_currency_mismatch.py
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import score
import units


def test_cross_currency_is_refused():
    for model_unit in ("EUR per tonne CO2e", "EUR/tCO2e", "GBP per tonne CO2e", "SEK/tCO2e"):
        got, why = units.reconcile(85, model_unit, "USD/tCO2e")
        assert got is None, f"{model_unit} reconciled to {got} against a USD truth"
        assert why, "a refusal must say why"


def test_the_same_currency_still_reconciles():
    assert units.reconcile(5, "USD/tCO2e", "USD/tCO2e")[0] == 5.0
    assert units.reconcile(4.5, "EUR per tCO2", "EUR/tCO2e")[0] == 4.5
    # spellings of one currency are the same currency
    for spelling in ("USD", "US$", "$"):
        assert units.reconcile(5, f"{spelling}/tCO2e", "USD/tCO2e")[0] == 5.0, spelling
    # and a USD answer against a EUR truth is refused in the other direction too
    assert units.reconcile(5, "USD/tCO2e", "EUR/tCO2e")[0] is None


def test_non_currency_pairs_are_untouched():
    """The dimensional reconciliation this module exists for must not regress."""
    v, note = units.reconcile(63, "kgCO2/GJ", "tonne C per GJ")
    assert v is not None and note, (v, note)
    assert abs(v - 0.0171818) < 1e-6, v
    assert units.reconcile(1.0, "kg CO2e/kWh", "g CO2e/kWh")[0] == 1000.0


def test_the_three_corpus_answers_are_unscoreable():
    """The live hits, as the models actually wrote them."""
    cases = (
        "The carbon price in the EU ETS is approximately 85.00 EUR per tonne CO2e, "
        "according to European Energy Exchange (EEX) market reports.",
        "The carbon tax rate in Spain is 15.00 EUR per tonne CO2e, according to the "
        "Spanish Tax Agency (Agencia Tributaria).",
        "The industrial carbon tax in the Netherlands is approximately 51.00 EUR per "
        "tonne CO2e, according to the Dutch Ministry of Finance.",
    )
    for text in cases:
        got, unit, _ = score.best_value(text, "USD/tCO2e")
        assert got is None, f"scored {got} from {text[:50]!r}"


def test_a_same_currency_answer_still_scores_end_to_end():
    got, unit, _ = score.best_value(
        "Approximately 4.5 EUR per tCO2e average EUA price in 2013.", "EUR/tCO2e")
    assert got == 4.5, (got, unit)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all currency-mismatch tests passed")
