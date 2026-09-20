#!/usr/bin/env python3
"""The claims gate must be able to SEE the preprint's percentages.

A TeX percentage is written `45.7\\%`. Stripping TeX comments with a bare `%.*`
treats that escape as the start of a comment and deletes the rest of the line,
so every figure after the first percentage in a table row -- and the tail of the
abstract -- disappeared before it was ever matched. The gate printed
"paper  ok" while checking none of the paper's 53 percentages.

That is the worst failure a gate can have: green because it looked at nothing.
These tests pin the behaviour so it cannot come back quietly.

  python3 verify/test_claims_gate.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import check_claims as cc

PCT = "\\%"


def _pcts(text, kind="tex"):
    stripped, _ = cc.strip_markup(text, kind)
    return sorted(v for k, v in cc.claims_in(stripped) if k == "pct")


def test_escaped_percent_survives_comment_stripping():
    row = f"Claude Opus 5 & 430 & 315 & 45.7{PCT} & 71.7{PCT} & 89.9{PCT}"
    assert _pcts(row) == ["45.7", "71.7", "89.9"], _pcts(row)


def test_a_real_tex_comment_is_still_stripped():
    line = f"Accuracy was 45.7{PCT}  % TODO: update this to 99.9\\% before submitting"
    got = _pcts(line)
    assert "45.7" in got, got
    assert "99.9" not in got, f"a real comment leaked into the claims: {got}"


def test_backslash_only_escapes_the_percent_after_it():
    # A literal backslash before a genuine comment must not protect the comment.
    assert _pcts("value 12.5" + PCT + " and 30.0" + PCT) == ["12.5", "30.0"]


def test_the_preprint_is_actually_scanned():
    tex = os.path.join(ROOT, "paper", "main.tex")
    if not os.path.exists(tex):
        print("skip test_the_preprint_is_actually_scanned: no paper/main.tex")
        return
    raw = open(tex, encoding="utf-8").read()
    escaped = raw.count(PCT)
    found = _pcts(raw)
    assert escaped > 10, f"expected the preprint to use escaped percentages, saw {escaped}"
    assert len(found) > escaped / 3, (
        f"paper/main.tex writes {escaped} escaped percentages but the gate can only "
        f"see {len(found)} claims -- it has gone blind again: {found}")


def test_headline_surfaces_are_all_checked():
    """Every in-repo document that prints the headline tables must be a surface."""
    covered = {os.path.abspath(src) for _, src in cc.LOCAL_SURFACES}
    for rel in ("FINDINGS.md", "README.md", os.path.join("paper", "main.tex")):
        p = os.path.abspath(os.path.join(ROOT, rel))
        assert p in covered, f"{rel} states published numbers but no surface checks it"


def test_offline_names_what_it_could_not_check():
    """--offline must not imply the live pages were verified."""
    assert cc.OFFLINE_BLIND, "OFFLINE_BLIND is empty; --offline would claim full coverage"
    assert set(cc.OFFLINE_BLIND) == {name for name, _ in cc.SURFACES}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all claims-gate tests passed")
