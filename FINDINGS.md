# How wrong are LLMs about emission factors?

467 questions from the GreenCalculus corpus (data version 2026.187), covering 45
sections and 75 publishers. Five models, identical questions, identical wording,
batches of 30, **no tools and no lookups**. Run 2026-09-10.

## Two rankings, in opposite orders

**When it answers, is it right?**

| Model | Scoreable | Within 10% | Within 50% | Off by >50% |
|---|---:|---:|---:|---:|
| Gemini 3.1 Pro | 46 | **65.2%** | 80.4% | 19.6% |
| Grok 4.6 | 66 | 62.1% | 86.4% | 13.6% |
| GPT-5.5 | 256 | 58.2% | 85.2% | 14.8% |
| Claude Opus 5 | 315 | 45.7% | 77.5% | 22.5% |
| Gemini 3.6 Flash | 315 | 41.9% | 78.1% | 21.9% |

**Of all 467 asked, how many did it get right?**

| Model | Answered | Refused | Correct | Correct of all 467 |
|---|---:|---:|---:|---:|
| GPT-5.5 | 326 | 141 | 149 | **31.9%** |
| Claude Opus 5 | 430 | 37 | 144 | 30.8% |
| Gemini 3.6 Flash | 404 | 63 | 132 | 28.3% |
| Grok 4.6 | 144 | 323 | 41 | 8.8% |
| Gemini 3.1 Pro | 77 | **390** | 30 | 6.4% |

Quote either table alone and you have misled someone. The best model by one
measure is the worst by the other.

## The finding: the more a model talks, the less each statement is worth

Sort by how often a model answers, and the danger metric sorts with it —
Spearman ρ = 0.80 across the five. Two of the four adjacent pairs still invert,
and at n = 5 that is suggestive, not significant:

| Model | Answered | **Right source, wrong number** |
|---|---:|---:|
| Grok 4.6 | 144 | 31.6% |
| Gemini 3.1 Pro | 77 | 35.3% |
| GPT-5.5 | 326 | 41.0% |
| Claude Opus 5 | 430 | 54.1% |
| Gemini 3.6 Flash | 404 | 58.8% |

This is not a story about which vendor is smartest. It is about **calibration** —
whether a model knows where its knowledge ends. Gemini 3.1 Pro refused 390 of 467
questions and was right two-thirds of the time when it spoke. Claude Opus 5
refused 37 and was right 46% of the time.

For carbon accounting that trade is not neutral. A refusal costs you a lookup.
A confident wrong number costs you a misstated disclosure.

## The controlled comparison

The clearest evidence needs no cross-vendor argument, because it is one vendor
and one knowledge base at two tiers:

| Google model | Answered | Within 10% | Right source, wrong number |
|---|---:|---:|---:|
| Gemini 3.1 **Pro** | 77 / 467 | 65.2% | 35.3% |
| Gemini 3.6 **Flash** | 404 / 467 | 41.9% | 58.8% |

Same company, same training corpus. The fast tier answers five times as many
questions and is right on far fewer of them, and when it cites the correct
publisher it is wrong about the number more often than not.

**This matters because the fast tier is the one that gets deployed.** Nobody puts
a slow reasoning model behind a bulk emissions pipeline. The model most likely to
be sitting in a production carbon feature is the one that fabricates most.

## Does connecting GreenCalculus fix it?

Same questions, same models, one difference: the model can call two keyless
GreenCalculus endpoints — `search_factors` and `lookup_factor` — the same pair an
MCP client gets. **It is not handed the answer.** It has to decide to search,
pick the right factor from the results, and read the value off it, so a failure
here is a real integration failure.

90 questions, stratified across sections, scored **paired** — the same question
ids with and without tools, so nothing hinges on sampling.

| | Without tools | With GreenCalculus |
|---|---|---|
| **Claude Opus 5** — answered | 86 / 90 | 89 / 90 |
| within 10% (of scoreable) | 37.1% | **98.7%** |
| off by >50% | 25.8% | **1.3%** |
| correct, of all 90 | 25.6% | **86.7%** |
| **GPT-5.5** — answered | 62 / 90 | 87 / 90 |
| within 10% (of scoreable) | 50.0% | **100.0%** |
| off by >50% | 19.6% | **0.0%** |
| correct, of all 90 | 25.6% | **87.8%** |

Both models gain about **61 percentage points**. GPT-5.5 gets every scoreable
answer right.

Two details that matter more than the headline:

- **It costs 1.0-1.6 tool calls per question.** The models search once, find the
  factor, read the value. No thrashing, no retry loops.
- **Coverage improves alongside accuracy.** GPT-5.5 answered 62 of 90 unaided and
  87 with tools — the lookup converted 25 refusals into correct answers. Accuracy
  and coverage usually trade against each other; here they move together, because
  the constraint was never reasoning, it was not having the number.

The residual gap to 100% is not model error: it is questions where the answer's
unit and the corpus unit cannot be mechanically reconciled (a model saying
"2.78 Tg CH4" against a truth of "Tg CH4 per ppb" — same figure, no denominator
given), plus one case where Claude looked up a neighbouring key and said so.

## The dangerous combination

| Model | Named a source | Named the *right* source |
|---|---:|---:|
| GPT-5.5 | 53.7% | 94.0% |
| Gemini 3.6 Flash | 71.7% | 91.9% |
| Claude Opus 5 | 71.7% | 89.9% |
| Gemini 3.1 Pro | 12.0% | 83.9% |
| Grok 4.6 | 21.6% | 82.2% |

Every model attributes *well* — around 90% name the publisher the number really
comes from. And for the talkative ones, the majority of those correctly-attributed
answers still carry a wrong number.

That is the failure mode worth naming. A wrong figure with no source gets caught,
because nobody can cite it. A wrong figure under the right publisher's name looks
exactly like diligence, and goes into the report.

## It knows the famous numbers and invents the rest

Claude Opus 5 by section, where at least 8 questions were scoreable:

| | Section | Within 10% |
|---|---|---:|
| Best | fuels | 92% |
| | fuel_properties | 91% |
| | mobile_combustion | 83% |
| Worst | cbam | 18% |
| | ev_charging | 17% |
| | ngfs_scenarios | 9% |
| | food_pcf | 8% |

Diesel per gallon is in every textbook. A CBAM country default, an NGFS scenario
cell, an AGRIBALYSE product line — jurisdiction-specific or recently published —
is fabricated in the same confident tone.

## One clean case

> **R-290 (propane), per kg leaked.** Claude Opus 5: *"3 kgCO2e per kg leaked —
> GWP100 = 3 under IPCC AR5. This is the value DEFRA publishes."*
> Truth: **0.02**, IPCC AR6 WGI Ch 7 Table 7.SM.7.

150x too high, credited to a publisher that does not publish it, no hedge. AR6
revised short-lived hydrocarbon GWPs down by two orders of magnitude.

## Is the scorer trustworthy?

It was wrong six times, and each is recorded because on a benchmark the
corrections matter more than the headline.

1. **It compared numbers, not quantities.** The first version reported 35.6% and
   scored a *correct* answer of 63 kgCO2/GJ against a truth of 0.0172 tonne C/GJ
   (the same number, x44/12) as a 366,179% error. [`units.py`](./units.py) now
   reconciles mass/energy/volume/length, percent-vs-fraction and C<->CO2 both ways.
2. **It penalised a model for typography.** Grok writes `head-1 yr-1` and `N2O`
   with Unicode superscripts and subscripts; these were being stripped, so its
   units failed to parse.
3. **It discarded a whole batch on formatting.** Gemini numbered one batch
   `1. [id]` instead of `[id]` and the parser silently skipped all 30 answers.
4. **An empty response is not a refusal.** Reasoning models spend output tokens
   on internal reasoning before any visible text; too small a token budget returns
   HTTP 200 with *nothing* in it, which is indistinguishable from a refusal.
   Since this study turns on refusal rates, that would have inverted a model's
   result. All budgets raised to 32,000 tokens, and every refusal reported here
   was verified to be words ("I don't know this factor"), not an empty reply.

5. **It swallowed the source into the unit.** `0.0277 kg CO2e per passenger.km
   — ADEME Base Carbone 2026 (element 43255)` had the whole citation read as part
   of the unit, so a correct answer was unscoreable. Extraction now stops at the
   first separator.
6. **A trailing full stop broke the match**, and `hectare`/`ha`, `year`/`yr` were
   treated as different units. Both folded.

Every one of these six was found before the number was published, and four of
them were *understating* the result rather than flattering it. The rankings did
not change through any of the revisions — which is the strongest evidence that
they are real.

Two independent checks that the headline is real:

- **Against hand adjudication.** Automated 46.9% vs a hand read of ~47% on the
  same 45 pilot answers.
- **Against scorer coverage.** Closing successive gaps moved unscoreable from 137
  to 110 while the headline moved 46.7% -> 45.7%. If the unscoreable pile had
  hidden a bias, converting a fifth of it would have shifted the result.

Unreconcilable units are reported **UNSCOREABLE** and leave the denominator,
never counted wrong — mostly currency (a SEK answer against a USD truth) and
prose units like "calendar year".

## Caveats, stated plainly

- One run per model, no temperature sweep, no repeats. A floor-setting
  measurement, not a leaderboard.
- Gemini 3.1 Pro and Grok 4.6 answered so few questions that their accuracy rests
  on 49 and 84 scoreable answers respectively. Treat those percentages as
  indicative; the refusal counts are the solid part.
- 30 questions share a context window, so answers within a batch are not fully
  independent.
- Questions come only from factors we may republish, so the answer key can ship.
  That favours well-documented public sources — if anything it makes the task
  easier than reality.
- Model versions and run date are stated because these numbers will move.

## Reproduce

```bash
python3 build_questions.py            # regenerate questions.json
python3 run_model.py --model gpt-5.5  # ask a model (needs that provider's key)
python3 compare.py                    # score every run in results/
```

Every model's raw output is committed verbatim under [`results/`](./results),
one file per batch. The prompt is in [`prompts/`](./prompts).
