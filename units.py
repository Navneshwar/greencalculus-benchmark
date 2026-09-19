"""Unit reconciliation for benchmark scoring.

A model answering "63 kgCO2/GJ" against a truth of "0.0172 tonne C per GJ" is
exactly right; a naive comparison calls it a 366,179% error. This module makes
the comparison dimensional instead of numeric.

Design rule: when a unit cannot be reconciled, say so. An unreconcilable pair is
reported as UNSCOREABLE, never silently counted as a wrong answer — a scorer
that guesses is the same failure the benchmark exists to measure.
"""
import re

# multiplier to the base unit of each dimension
MASS = {  # base: kg
    "mg": 1e-6, "milligram": 1e-6, "g": 1e-3, "gram": 1e-3, "gramme": 1e-3,
    "kg": 1.0, "kilogram": 1.0, "kilogramme": 1.0,
    "t": 1000.0, "tonne": 1000.0, "ton": 1000.0, "tonnes": 1000.0, "mt": 1000.0,
    "metric ton": 1000.0, "metric tonne": 1000.0, "tco2e": 1000.0, "tco2": 1000.0,
    "kt": 1e6, "gg": 1e6, "tg": 1e9,
}
ENERGY = {"wh": 1e-3, "kwh": 1.0, "mwh": 1e3, "gwh": 1e6, "twh": 1e9,
          "j": 2.7778e-7, "kj": 2.7778e-4, "mj": 0.2778, "gj": 277.78, "tj": 277_780.0,
          "btu": 2.931e-4, "mmbtu": 293.07, "therm": 29.3071}
VOLUME = {"ml": 1e-3, "l": 1.0, "litre": 1.0, "liter": 1.0, "m3": 1000.0,
          "gallon": 3.78541, "gal": 3.78541}
LENGTH = {"m": 1e-3, "km": 1.0, "mile": 1.60934, "mi": 1.60934}
# base: m2. Area had no table, so a per-square-metre denominator degraded to the
# catch-all "other:m2" and was compared as a STRING. That is what let a bare
# `per yr` answer match a `kWh per m2 per year` truth: both became "other:*", the
# containment rule saw {year} as a subset of {m2, year}, and a whole-building
# annual total was scored as a per-square-metre intensity. Area is a dimension,
# so giving it a table is enough -- the den_dim comparison then refuses the pair
# on its own, with no new rule and no list of exception words to maintain.
# 19 truth units are per-m2, 5 per-hectare, 1 per-acre.
AREA = {"m2": 1.0, "sqm": 1.0, "ft2": 0.092903, "sqft": 0.092903,
        "ha": 1e4, "hectare": 1e4, "acre": 4046.86}
DIMENSIONLESS = {"fraction": 1.0, "ratio": 1.0, "dimensionless": 1.0, "%": 0.01,
                 "percent": 0.01, "pct": 0.01}
CURRENCY = {"usd": 1.0, "us$": 1.0, "$": 1.0, "eur": 1.0, "gbp": 1.0, "sek": None}

# Which currency each spelling IS. Every scale above is 1.0 because we hold no
# exchange rates and will not: an FX rate is a price on a date, not a unit
# conversion. That made two DIFFERENT currencies reconcile at 1:1, so a model
# answering "85.00 EUR per tonne CO2e" scored 85 against a USD/tCO2e truth --
# the same class of error as #23, and wrong by whatever the rate happens to be.
# `sek: None` was already refusing this way by having no scale at all; the rest
# were reconciling by accident. reconcile() now refuses on a mismatch instead.
CURRENCY_FAMILY = {"usd": "usd", "us$": "usd", "$": "usd",
                   "eur": "eur", "gbp": "gbp", "sek": "sek"}

# carbon-species conversion: 1 kg C == 44/12 kg CO2
C_TO_CO2 = 44.0 / 12.0

_ALIAS = [(r"co2e|co2eq\w*|co2-e|co₂e|co2 eq\w*|carbon dioxide equivalent", "co2e"),
          (r"\bco2\b|co₂", "co2"),
          (r"\bch4\b|methane", "ch4"), (r"\bn2o\b", "n2o"), (r"\bsf6\b", "sf6"),
          (r"\bcarbon\b(?! dioxide)|\bc\b(?!o)", "c")]


SUP = {"⁰":"0","¹":"1","²":"2","³":"3","⁴":"4","⁵":"5","⁶":"6","⁷":"7","⁸":"8","⁹":"9","⁻":"-"}
SUB = {"₀":"0","₁":"1","₂":"2","₃":"3","₄":"4","₅":"5","₆":"6","₇":"7","₈":"8","₉":"9"}


def _clean(u):
    u = (u or "").lower().strip()
    # Some models write "kg CH4 head-1 yr-1" with Unicode superscripts, and
    # "N2O" with subscripts. Both mean the same as the spelled-out forms; not
    # normalising them would score a model down for its typography.
    for k, v in SUB.items():
        u = u.replace(k, v)
    u = re.sub(r"([a-z0-9]+)\s*⁻\s*[¹1]", r"per \1", u)
    for k, v in SUP.items():
        u = u.replace(k, v)
    u = u.replace("−", "-").replace("·", " ").replace("/", " per ")
    # "room.night", "passenger.km", "vehicle.km" join two words with a dot
    u = re.sub(r"(?<=[a-z])[.\-](?=[a-z])", " ", u)
    u = u.strip(" .;:-")                       # a trailing full stop is not part of the unit
    for a, b in (("hectares", "ha"), ("hectare", "ha"), ("years", "year"), ("yr", "year"),
                 ("hrs", "hour"), ("hr", "hour"), ("tonnes", "tonne"), ("litres", "litre"),
                 ("kilometres", "km"), ("kilometers", "km"), ("tkm", "tonne km"), ("miles", "mile"),
                 ("nights", "night"), ("rooms", "room"), ("items", "item"), ("days", "day")):
        u = re.sub(rf"\b{a}\b", b, u)
    u = re.sub(r"\(.*?\)", " ", u)
    u = re.sub(r"[^a-z0-9%$ .\-]+", " ", u)
    # "kgco2e" / "tco2" / "gsf6" arrive glued; split the mass prefix off the species
    u = re.sub(r"\b(mg|kg|g|t|tonne|tonnes|kt|gg|tg)(co2eq|co2e|co2|ch4|n2o|sf6|c)\b", r"\1 \2", u)
    return re.sub(r"\s+", " ", u).strip()


def _species(u):
    for pat, name in _ALIAS:
        if re.search(pat, u):
            return name
    return None


def _scale(tok, table):
    tok = tok.strip()
    return table.get(tok)


def parse_unit(u):
    """-> dict(num_scale, species, den_dim, den_scale) or None if unparseable."""
    u = _clean(u)
    if not u:
        return None
    for k, v in DIMENSIONLESS.items():
        if u == k or u.startswith(k + " "):
            return {"num_scale": v, "species": None, "den_dim": None,
                    "num_currency": None, "den_scale": 1.0}
    num, den = (u.split(" per ", 1) + [""])[:2] if " per " in u else (u, "")
    sp = _species(num)
    num_scale = None
    # leading mass/currency token
    num_currency = None
    m = re.match(r"([a-z$%]+(?:\s+ton(?:ne)?)?)", num)
    if m:
        tok = m.group(1)
        for table in (MASS, CURRENCY, ENERGY, VOLUME):
            if tok in table:
                num_scale = table[tok]
                if table is CURRENCY:
                    num_currency = CURRENCY_FAMILY.get(tok)
                break
    if num_scale is None:
        for tok in num.split():
            for table in (MASS, ENERGY, VOLUME, CURRENCY):
                if tok in table:
                    num_scale = table[tok]
                    if table is CURRENCY:
                        num_currency = CURRENCY_FAMILY.get(tok)
                    break
            if num_scale is not None:
                break
    if num_scale is None:
        return None
    den_dim = den_scale = None
    if den:
        for name, table in (("energy", ENERGY), ("volume", VOLUME), ("area", AREA),
                            ("length", LENGTH), ("mass", MASS)):
            for tok in den.split():
                if tok in table:
                    den_dim, den_scale = name, table[tok]
                    break
            if den_dim:
                break
        if den_dim is None:
            den_dim, den_scale = ("other:" + den.split()[0] if den.split() else "other"), 1.0
    stop = {"of", "per", "the", "a", "good", "product", "basis", "input", "output"}
    return {"num_scale": num_scale, "species": sp, "den_dim": den_dim,
            "num_currency": num_currency,
            "den_scale": den_scale if den_scale is not None else 1.0,
            "den_tokens": {t for t in den.split() if t not in stop}}


def reconcile(value, model_unit, truth_unit):
    """Convert `value` from model_unit into truth_unit.

    Returns (converted_value, note) or (None, reason) when the pair cannot be
    reconciled — the caller must treat that as UNSCOREABLE, not as wrong.
    """
    a, b = parse_unit(model_unit), parse_unit(truth_unit)
    if a is None or b is None:
        return None, "unit not parseable"
    if a["num_scale"] is None or b["num_scale"] is None:
        return None, "unknown numerator unit"
    # Two different currencies are not a unit conversion. Refuse rather than
    # apply the 1.0 that sits in CURRENCY for want of an exchange rate.
    # .get, not [...]: parse_unit returns from more than one place, and a new
    # return path that forgets the key should not crash the whole scorer.
    ca, cb = a.get("num_currency"), b.get("num_currency")
    if ca and cb and ca != cb:
        return None, f"currency mismatch ({ca} vs {cb}); no exchange rate is assumed"
    # denominators must be the same dimension
    da, db = a["den_dim"], b["den_dim"]
    if da != db:
        both_other = isinstance(da, str) and isinstance(db, str) and \
            da.startswith("other") and db.startswith("other")
        # One token set must CONTAIN the other. "per year" vs "per person per
        # year" is the same basis stated at different length; "per dwelling per
        # year" vs "per m2 per year" is two different quantities that merely
        # share the word "year", and must not reconcile.
        if both_other and a["den_tokens"] and b["den_tokens"] and (
                a["den_tokens"] <= b["den_tokens"] or b["den_tokens"] <= a["den_tokens"]):
            pass
        elif da is None and db is None:
            pass
        else:
            return None, f"denominator mismatch ({da} vs {db})"
    note = None
    v = value * a["num_scale"] / b["num_scale"]
    v = v * (a["den_scale"] / b["den_scale"]) ** -1 if a["den_scale"] and b["den_scale"] else v
    # carbon species: C vs CO2/CO2e
    sa, sb = a["species"], b["species"]
    if sa == "c" and sb in ("co2", "co2e"):
        v, note = v * C_TO_CO2, "converted kg C -> kg CO2 (x44/12)"
    elif sb == "c" and sa in ("co2", "co2e"):
        v, note = v / C_TO_CO2, "converted kg CO2 -> kg C (x12/44)"
    return v, note
