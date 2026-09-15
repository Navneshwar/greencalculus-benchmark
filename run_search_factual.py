#!/usr/bin/env python3
"""The THIRD condition: the same 90 factual questions, with web search instead of
the GreenCalculus tools.

The repo already answers two of the three questions a reader will ask:

  no tools        results/raw_*/ and runs_opus5_full.json   37.1% / 50.0%
  GC tools        results/tools_*.jsonl                     98.7% / 100.0%
  web search      <- this file                              ?

Without this arm the paired result has an obvious unanswered objection — "web
search would have fixed it too, you just didn't try" — and that objection lands
on the strongest claim in the study. Either answer is worth having. If search
closes the gap, the honest finding is that the retrieval mechanism matters less
than we say; if it does not, the paired result stops being arguable.

Design rules, and they are the whole point:

1. THE SAME 90 QUESTIONS, read from the tool arm's own output rather than
   re-derived from a seed. A sample that drifts makes the three arms
   incomparable and nobody would notice.
2. THE SAME PROMPT, varying only the retrieval mechanism. The tool arm says
   "use the tools rather than answering from memory"; this says "use web search
   rather than answering from memory". Every other word is identical.
3. SCORED BY THE ROOT score.py, never a re-implementation — same rule the
   HuggingFace build follows.

Caveat to carry into any write-up: OpenAI's built-in web_search is only on the
Responses API, while run_tools.py drives the same model through chat/completions.
The endpoint differs between this arm and the tool arm for gpt-5.5. It does not
differ for claude-opus-5.

  python3 run_search_factual.py                      # both models
  python3 run_search_factual.py claude-opus-5        # one
"""
import json, os, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
PAIRED_SRC = ROOT / "results" / "tools_claude-opus-5.jsonl"
URL_RE = re.compile(r'https?://[^\s\)\]"<>]+')

# Duplicated from aeo/run_search.py on purpose. aeo/score.py SHADOWS the root
# score.py, so putting aeo/ on sys.path to share a constant would silently swap
# the scorer underneath this file. A five-line table is the cheaper risk.
RATES = {
    "claude-opus-5": (5.00, 25.00, 0.010),
    "gpt-5.5":       (5.00, 30.00, 0.010),
}
MAX_SPEND = float(os.environ.get("GC_MAX_SPEND", "25"))
MAX_CALLS = int(os.environ.get("GC_MAX_CALLS", "220"))
SPENT, CALLS = [0.0], [0]

SYS = ("You answer questions about greenhouse-gas emission factors. You have access to "
       "web search. Use it to look up the actual value rather than answering from memory. "
       "Reply with one line only, in the form: [<id>] <value> <unit> — <source>. "
       "If you genuinely cannot find it, say so.")


def post(url, payload, headers, timeout=600):
    r = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                               headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def paired_questions():
    """The 90, in the order the tool arm asked them."""
    qs = {q["id"]: q for q in json.load(open(ROOT / "questions.json"))["questions"]}
    out, seen = [], set()
    for line in PAIRED_SRC.open():
        if not line.strip():
            continue
        qid = json.loads(line)["id"]
        if qid in seen or qid not in qs:
            continue
        seen.add(qid); out.append(qs[qid])
    return out


def ask_claude(model, qid, question):
    d = post("https://api.anthropic.com/v1/messages",
             {"model": model, "max_tokens": 16000, "system": SYS,
              "tools": [{"type": os.environ.get("GC_WEB_SEARCH_TYPE", "web_search_20250305"),
                         "name": "web_search", "max_uses": 8}],
              "messages": [{"role": "user", "content": f"[{qid}] {question}"}]},
             {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    blocks = d["content"]
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    n = sum(1 for b in blocks if b.get("type") == "server_tool_use")
    urls = []
    for b in blocks:
        if b.get("type") == "web_search_tool_result":
            c = b.get("content")
            if isinstance(c, list):                      # an error returns an OBJECT, not a list
                urls += [r["url"] for r in c if isinstance(r, dict) and r.get("url")]
    u = d.get("usage") or {}
    return text.strip(), n, urls, {"input": u.get("input_tokens"), "output": u.get("output_tokens")}


def ask_gpt(model, qid, question):
    d = post("https://api.openai.com/v1/responses",
             {"model": model, "instructions": SYS, "input": f"[{qid}] {question}",
              "tools": [{"type": "web_search"}], "max_output_tokens": 16000},
             {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
    out = d.get("output", [])
    text = "".join(c.get("text", "") for o in out if o.get("type") == "message"
                   for c in (o.get("content") or []) if c.get("type") in ("output_text", "text"))
    n = sum(1 for o in out if o.get("type") == "web_search_call")
    urls = URL_RE.findall(json.dumps(out))
    u = d.get("usage") or {}
    return text.strip(), n, urls, {"input": u.get("input_tokens"), "output": u.get("output_tokens")}


def ask(model, qid, question):
    if model.startswith("claude"):
        return ask_claude(model, qid, question)
    if model.startswith("gpt"):
        return ask_gpt(model, qid, question)
    raise ValueError(f"no web-search route for {model}")


def price(model, usage, n):
    pin, pout, srate = RATES.get(model, (0, 0, 0))
    return ((usage.get("input") or 0) / 1e6 * pin
            + (usage.get("output") or 0) / 1e6 * pout
            + srate * n)


def main():
    models = sys.argv[1:] or ["claude-opus-5", "gpt-5.5"]
    questions = paired_questions()
    print(f"{len(questions)} paired questions, {len(models)} models, "
          f"ceiling ${MAX_SPEND:.2f} / {MAX_CALLS} calls\n")
    t0 = time.time()
    for model in models:
        out = ROOT / "results" / f"search_factual_{model}.jsonl"
        done = set()
        if out.exists():
            done = {json.loads(l)["id"] for l in out.open() if l.strip()}
        with out.open("a") as fh:
            for q in questions:
                if q["id"] in done:
                    continue
                text = None
                for attempt in range(3):
                    try:
                        text, n, urls, usage = ask(model, q["id"], q["question"]); break
                    except Exception as e:
                        print(f"  {model:16} retry {attempt+1}: {str(e)[:70]}", flush=True)
                        time.sleep(20)
                if text is None:
                    print(f"  {model:16} FAILED {q['id'][:44]}", flush=True); continue
                cost = price(model, usage, n)
                SPENT[0] += cost; CALLS[0] += 1
                fh.write(json.dumps({
                    "id": q["id"], "question": q["question"], "answer": text,
                    "searched": n > 0, "n_searches": n,
                    "cited_urls": sorted(set(urls))[:40], "usage": usage, "est_cost": round(cost, 4),
                }) + "\n")
                fh.flush()
                print(f"  {model:16} {q['id'][:40]:40} {n:>2}s ${cost:.3f} "
                      f"running ${SPENT[0]:.2f}", flush=True)
                if SPENT[0] > MAX_SPEND or CALLS[0] > MAX_CALLS:
                    print(f"\nSTOPPING: ${SPENT[0]:.2f} / {CALLS[0]} calls exceeds the ceiling. "
                          f"Rerun to resume — finished answers are on disk.", flush=True)
                    return
    print(f"\ndone in {time.time()-t0:.0f}s, {CALLS[0]} calls, ~${SPENT[0]:.2f}")


if __name__ == "__main__":
    main()
