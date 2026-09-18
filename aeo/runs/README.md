# Run files

One file per run, `search-YYYY-MM-DD.jsonl`, never rewritten.

The 14 September run is not in here — it lives at `../search_answers.jsonl`,
where it was published, and four scripts plus a guide point at it by name.
`trend.py` picks it up as the panel's first point.

## Why one file per run

`run_search.py` resumes by skipping `(model, prompt)` pairs it has already
answered. Until this directory existed that skip list was seeded from one shared
file, so the second run would have found all 125 pairs present, skipped every
one, and exited `0 calls, ~$0.00` — reporting September's numbers as October's.
A cadence that cannot tell "nothing moved" from "nothing ran" measures nothing.

Resume within a run still works, and still matters: the spend ceiling stops a run
part-way and you restart it onto the same file.

```bash
python3 aeo/run_search.py --run 2026-10-06              # all five models
python3 aeo/run_search.py --run 2026-10-06 gpt-5.5      # one model onto the same file
python3 aeo/score_search.py runs/search-2026-10-06.jsonl
python3 aeo/trend.py
```
