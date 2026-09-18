# AI recommendation study (AEO arm)

Which carbon data providers do frontier AI models recommend when nobody prompts
them with a name? Run 10 September 2026.

Published write-up: <https://greencalculus.com/guides/ai-recommended-carbon-data-providers/>
Archived with a DOI: <https://doi.org/10.5281/zenodo.22692277> (concept DOI, always latest)

## The conflict, stated first

GreenCalculus sells emission factor data. We compete with several of the
companies measured here. We wrote the prompts, wrote the brand-detection
patterns, ran the scoring — and finished last, with **0 mentions out of 125**.

That is why everything is in this directory: the prompts, the alias patterns,
the raw text of every answer and the scorer. If you think a prompt is loaded or
a competitor's aliases are too narrow, change them and re-run it.

## What was measured

25 prompts across six buyer intents, put to five models with **no tools and no
web access**, so each answer reflects what the model believes rather than what
it can retrieve. Every model got every prompt: 125 answers.

Models: `claude-opus-5`, `gpt-5.5`, `gemini-3.1-pro-preview`,
`gemini-3.6-flash`, `grok-4.6`.

No prompt names GreenCalculus. A prompt that named us would have measured our
prompt-writing, not our visibility.

## Headline result

| Vendor | Answers naming it | Reach | Named first |
|---|---|---|---|
| Climatiq | 86 | 69% | 54 |
| ecoinvent | 85 | 68% | 29 |
| EXIOBASE | 73 | 58% | 17 |
| Electricity Maps | 53 | 42% | 7 |
| Carbon Interface | 47 | 38% | 0 |
| … | | | |
| **GreenCalculus** | **0** | **0%** | **0** |

23 of the 25 tracked vendors were named at least once. GreenCalculus and Cozero
are the two that never were.

Public datasets outrank every vendor: DEFRA 83%, US EPA 83%, ADEME 54%,
IPCC 48%.

## The direct probe

`direct_probe.py` asks each model about GreenCalculus itself — a different
question from whether it recommends us. Three prompts, escalating in how much
they presuppose:

1. "What is GreenCalculus? … If you do not know, say so plainly."
2. "Does a company called GreenCalculus publish emission factor data?"
3. "How does GreenCalculus compare to Climatiq for emission factor data?"

Given permission to decline, **all four models that answered declined**. Asked
to compare — the way a real user asks — **two of the four invented a company
profile**, including a market position, a source list and a comparison table.
Claude Opus 5 and Grok 4.6 declined both times.

GPT-5.5 was rate-limited during this arm and is absent from it. It answered all
25 recommendation prompts.

This is unusually clean ground truth for a hallucination test: we know exactly
what the company being described is, because it is ours.

## Files

| File | What it is |
|---|---|
| `prompts.py` | The 25 prompts, grouped by intent |
| `brands.py` | Regex aliases per brand; vendors and public datasets tracked separately |
| `run.py`, `run2.py` | Runners. Resume from `answers.jsonl`; one JSON line per (model, prompt) |
| `direct_probe.py` | The three direct questions about GreenCalculus |
| `answers.jsonl` | Raw text of all 125 answers, verbatim |
| `direct_probe.jsonl` | Raw text of the direct-probe answers |
| `score.py` | Counting and reporting |
| `results.json` | The summary table |

## Reproducing

```bash
export ANTHROPIC_API_KEY=… OPENAI_API_KEY=… GEMINI_API_KEY=… XAI_API_KEY=…
python3 run.py            # resumes; skips (model, prompt) pairs already in answers.jsonl
python3 score.py          # prints the tables
python3 direct_probe.py   # the direct arm
```

Answers are appended, never overwritten, and `score.py` de-duplicates on
(model, prompt) so a partial re-run cannot double-count.

## Limits

- 25 prompts is a small sample. One prompt is 4 points of reach. Read the gap
  between Climatiq and ecoinvent as noise; the gap between the top three and
  everyone else is real.
- 25 vendors tracked. A provider outside `brands.py` reads as absent even if a
  model named it. Additions welcome.
- Being *named* is not being *recommended* — a mention anywhere in the answer
  counts, including a dismissal. This overstates endorsement uniformly.
- Point-in-time for 10 September 2026, model versions as listed.
- **Point-in-time, and that is why it now repeats.** The search-off arm above is
  10 September 2026. The search-enabled arm runs on a cadence — see below.


## The search-enabled arm is a panel

Everything above was produced with web access **off**: it measures what a model
believes, which moves on training cycles and which no amount of work in 2026 can
shift. The search-enabled arm asks the same 25 prompts with web access **on**,
and that one does respond to work, in weeks.

It runs **every two weeks**, and it is read as a panel rather than a
before-and-after.

### Why not one baseline and one re-run

That was the plan until 18 September. It had a baseline on 14 September, a
re-run afterwards, and a freeze on publishing anything in between so the two
would stay comparable. Three things were wrong with it:

- **No control group.** A model-version change between the two runs is
  indistinguishable from a launch that worked.
- **Underpowered.** 25 prompts. One prompt is 4 points of reach. Nothing short of
  roughly a doubling is separable from noise, and the limits section above
  already says to read the Climatiq/ecoinvent gap as noise.
- **The freeze cost more than the measurement was worth.** At $14–23 a run, the
  instrument is far too cheap to be worth not shipping for.

### What replaced it

**A cadence.** Runs every two weeks, one file per run under `runs/`, never
rewritten. Missing a run leaves a gap in a series; it does not invalidate one.

**Controls.** Climatiq, ecoinvent, EXIOBASE, DEFRA and EPA are named by the same
prompts in the same call, so anything that moves the whole web moves them too and
cancels in the difference. They were already in `brands.py`; the control arm cost
nothing and is the single biggest thing the old design was missing.

**Annotations.** `timeline.tsv` records what shipped and when. `trend.py` prints
those between the runs they fall between, so a movement can be read against what
preceded it — including when it followed nothing.

```bash
python3 aeo/run_search.py --run 2026-10-06     # ~$14-23, five models, honours GC_MAX_SPEND
python3 aeo/trend.py                           # the panel
python3 aeo/trend.py --csv                     # one row per run x brand
```

### How to read it honestly

- **The differential, not our line.** Our reach rising while every control rises
  is the web changing, not us.
- **The noise floor is printed every run.** One prompt is 4 points. Smaller than
  that is nothing, however much it looks like a trend.
- **`trend.py` withholds the differential** when a run's model set changed or a
  provider stopped searching, because a reach percentage computed over a
  different instrument is not comparable to the one before it.
- **Read-but-not-cited is the leading indicator.** It moves before naming does:
  the crawler reaches a page weeks before the prose starts crediting it. Rising
  there while naming stays flat is a writing problem, not a discovery problem.
