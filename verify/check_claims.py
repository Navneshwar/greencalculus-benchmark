#!/usr/bin/env python3
"""Refuse to let an unreproducible number sit in published prose.

Extracts every numeric claim from the published study pages, the preprint and
the dataset card, and asks one question of each: does a committed script
produce this number? Anything that does not must be listed in allowlist.json
with a written reason. Anything else fails the build.

  python3 verify/check_claims.py            # live pages over HTTP
  python3 verify/check_claims.py --offline  # skip the network, check local files
"""
import argparse, html, json, os, re, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import figures as figures_mod

SURFACES = [
    ("guide:accuracy", "https://greencalculus.com/guides/ai-emission-factors-accuracy/"),
    ("guide:licences", "https://greencalculus.com/guides/emission-factor-licences/"),
    ("guide:by-category", "https://greencalculus.com/guides/ai-emission-factor-reliability-by-category/"),
    ("guide:recommendations", "https://greencalculus.com/guides/ai-recommended-carbon-data-providers/"),
]
LOCAL_SURFACES = [
    ("paper", os.path.join(ROOT, "paper", "main.tex")),
    ("dataset-card", os.path.join(ROOT, "hf", "README.md")),
    ("findings", os.path.join(ROOT, "FINDINGS.md")),
    # The repo front page carries the same headline tables as FINDINGS.md. It was
    # not checked, so a scorer change could leave it stating a number no script
    # produces while the gate still printed PASS.
    ("repo-readme", os.path.join(ROOT, "README.md")),
]

# Surfaces that exist only over HTTP. --offline cannot check these, and saying so
# matters: the docstring claims "the published study pages", and a PASS that
# quietly skipped four of them is the kind of green that hides a stale headline.
OFFLINE_BLIND = [name for name, _ in SURFACES]

# A claim is a percentage, a correlation, or a thousands-separated count.
CLAIM_RE = re.compile(
    r"(?:r\s*=\s*(?P<r>[−-]?\d*\.\d+))"
    r"|(?P<pct>\d{1,3}(?:\.\d+)?)\s?%"
    r"|(?P<big>\b\d{1,3}(?:[,{]?,?\d{3})+\b)"
)


# Page furniture whose numbers belong to OTHER documents. The source matrix
# prints bibliographic metadata about every source we cite — journal page
# numbers, EU grant numbers, archive snapshot ids, and figures quoted from the
# cited work itself. The related-content cards print one-line summaries of other
# pages. None of it is a claim this page makes about our data, and treating it as
# one made the gate fail on "38,700 farms" from a Poore & Nemecek card.
#
# Allowlisting those numbers would have been the wrong fix: it would also wave
# through the next genuinely wrong number that happens to land inside a widget.
# Scope the gate to the article's own prose instead.
FURNITURE = ("gc-srcmx", "gc-related-card", "gc-related-grid")


def drop_subtrees(text, classes=FURNITURE):
    """Remove each element whose class marks it as furniture, with its children.

    Depth-counted rather than regex-matched to the closing tag: these contain
    nested divs, and a non-greedy `.*?</div>` would cut at the first inner close
    and leave most of the subtree behind.

    Returns (text, dropped_count) — main() prints the count, because a filter
    that silently stops matching turns a red gate green, which is worse than a
    red gate.
    """
    dropped = 0
    pattern = re.compile(
        r"<(?P<tag>div|section|aside|ul|ol|li|table|nav)\b[^>]*\bclass=\"[^\"]*\b(?:"
        + "|".join(re.escape(c) for c in classes) + r")\b[^\"]*\"[^>]*>", re.I)
    while True:
        m = pattern.search(text)
        if not m:
            return text, dropped
        tag = m.group("tag")
        scan = re.compile(rf"<(/?){tag}\b[^>]*?(/?)>", re.I)
        depth, end = 1, m.end()
        for t in scan.finditer(text, m.end()):
            if t.group(2) == "/":            # self-closing, no depth change
                continue
            depth += -1 if t.group(1) else 1
            if depth == 0:
                end = t.end()
                break
        else:
            end = len(text)                  # unbalanced: drop to the end
        text = text[:m.start()] + " " + text[end:]
        dropped += 1


def strip_markup(text, kind):
    if kind == "tex":
        # Order matters, and getting it wrong silently blinds the gate to the
        # whole preprint. A percentage in TeX is written `45.7\%`; stripping
        # comments with a bare `%.*` treats that escape as a comment start and
        # deletes the rest of the LINE -- every later figure in a table row, and
        # the tail of the abstract, vanish before they are ever matched. Only an
        # UNescaped % opens a comment, so require that the % is not preceded by
        # a backslash, and unescape afterwards.
        text = re.sub(r"(?<!\\)%.*", "", text)         # TeX comments
        text = text.replace(r"\%", "%").replace("{,}", ",")
        return text, 0
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)  # engineering summaries
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text, dropped = drop_subtrees(text)
    present = sum(1 for c in FURNITURE if c in text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text), (dropped, present)


# Years, DOI paths and standard numbers are identifiers, not claims about data.
NOT_A_CLAIM = re.compile(r"(?:doi\.org|zenodo|ISO|IEC|EN|BS|PAS|GHG Protocol|seed)\s*[/:]?\s*[\d./\s-]*$", re.I)


def is_identifier(value, before):
    if re.fullmatch(r"(19|20)\d{2}", value):          # a year
        return True
    if NOT_A_CLAIM.search(before[-24:]):               # DOI or standard number
        return True
    if re.search(r"[/@.=]\s*$", before[-2:]):         # inside a URL or version
        return True
    return False


def claims_in(text):
    found = set()
    for m in CLAIM_RE.finditer(text):
        raw = m.group("big")
        if raw is not None and is_identifier(raw.replace(",", ""), text[:m.start()]):
            continue
        if m.group("r") is not None:
            found.add(("r", m.group("r").replace("−", "-")))
        elif m.group("pct") is not None:
            found.add(("pct", m.group("pct")))
        else:
            found.add(("count", raw.replace(",", "")))
    return found


def reproduces(kind, raw, figs):
    """True if some committed figure prints exactly this, at its own precision."""
    value = float(raw)
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    for key, fig in figs.items():
        if fig is None or isinstance(fig, bool):
            continue
        if kind == "r" and not key.startswith("corpus_size.r"):
            continue
        if kind == "pct" and not isinstance(fig, (int, float)):
            continue
        try:
            if round(float(fig), decimals) == value:
                return key
        except (TypeError, ValueError):
            continue
    return None


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "gc-claims-gate"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--list-unmatched", action="store_true")
    args = ap.parse_args()

    figs = figures_mod.build()
    with open(os.path.join(HERE, "allowlist.json")) as fh:
        allow = json.load(fh)

    surfaces = list(LOCAL_SURFACES)
    if not args.offline:
        surfaces = SURFACES + surfaces

    failures, checked, allowed = [], 0, 0
    blind = []
    for name, src in surfaces:
        if src.startswith("http"):
            text, furniture = strip_markup(fetch(src), "html")
            dropped, leftover = furniture
            note = f"  [{dropped} furniture subtree(s) dropped]" if dropped else ""
            if leftover:
                # The class survived the drop, so the markup changed shape and the
                # filter no longer reaches it. Say so loudly: a filter that stops
                # matching turns a red gate green.
                blind.append(f"{name}: furniture class still present after dropping "
                             f"{dropped} subtree(s) — the filter may have gone blind")
                note += "  ** LEFTOVER **"
            if note:
                print(f"  {name:24} {note.strip()}")
        else:
            if not os.path.exists(src):
                print(f"  SKIP {name}: {src} absent")
                continue
            raw = open(src, encoding="utf-8").read()
            text, _ = strip_markup(raw, "tex" if src.endswith(".tex") else "md")

        unmatched = []
        for kind, raw_value in sorted(claims_in(text)):
            checked += 1
            key = reproduces(kind, raw_value, figs)
            if key:
                continue
            token = f"{raw_value}%" if kind == "pct" else (
                f"r={raw_value}" if kind == "r" else raw_value)
            if token in allow.get(name, {}) or token in allow.get("*", {}):
                allowed += 1
                continue
            unmatched.append(token)
        status = "ok" if not unmatched else f"{len(unmatched)} UNEXPLAINED"
        print(f"  {name:24} {status}")
        if unmatched:
            print(f"      {', '.join(unmatched)}")
            failures.append((name, unmatched))

    for b in blind:
        print(f"\n  ! {b}")
    print(f"\n{checked} numeric claims checked · {allowed} explained by allowlist "
          f"· {len(figs)} figures recomputed from committed data")

    if failures:
        print("\nFAIL: a number is published that no committed script produces and")
        print("      no allowlist entry explains. Either make it reproducible or")
        print("      justify it in verify/allowlist.json. Do not edit it away.")
        return 1
    if args.offline:
        # Never let --offline print the unqualified claim. The live pages carry the
        # headline tables too, and a scorer change leaves them stale in exactly the
        # same way -- a green --offline run is not evidence they were checked.
        print("\nPASS (offline): every number on the surfaces checked above either")
        print("      reproduces from committed data or carries a written justification.")
        print("      NOT checked, because they exist only over HTTP: "
              + ", ".join(OFFLINE_BLIND) + ".")
        print("      Run without --offline before publishing a number.")
        return 0
    print("\nPASS: every published number either reproduces from committed data")
    print("      or carries a written justification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
